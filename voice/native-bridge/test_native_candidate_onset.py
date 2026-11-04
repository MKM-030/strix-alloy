"""Real endpoint + Native microphone/ASR envelopes; synthetic PCM, no services."""
import asyncio
from array import array
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import EndpointGate
from native_backend import BackendEvent
from native_bridge import Config, NativeCall


class Peer:
    connectionState = 'connected'
    iceConnectionState = 'completed'
    def __init__(self, *args, **kwargs):pass
    def on(self, *args):pass
    def addTrack(self, *args):pass
    async def close(self):pass


class Denoiser:
    active = False
    fallback_reason = None
    pending_samples = 0
    def feed(self, pcm):return [pcm]
    def finish(self):return []
    def close(self):pass


class Frame:
    def __init__(self, voiced):self.pcm = array('h', [3000 if voiced else 0] * 320)
    def to_ndarray(self):return self.pcm


class Resampler:
    def __init__(self, **kwargs):pass
    def resample(self, frame):return [frame]


class Track:
    kind = 'audio'
    readyState = 'live'
    def __init__(self):self.frames = asyncio.Queue()
    def feed(self, count, voiced=True):
        for _ in range(count):self.frames.put_nowait(Frame(voiced))
    async def recv(self):return await self.frames.get()


class Speech:
    def __init__(self):self.received = []
    async def transcribe(self, pcm):self.received.append(bytes(pcm));return 'Ja'


async def until(predicate):
    async with asyncio.timeout(1):
        while not predicate():await asyncio.sleep(0)


class CandidateIdentityTests(unittest.TestCase):
    def test_candidate_identity_precedes_confirmation_without_changing_thresholds(self):
        pcm = array('h', [3000] * 320).tobytes()
        for onset_ms, frames in ((20,6),(100,6),(160,8)):
            with self.subTest(onset_ms=onset_ms):
                gate = EndpointGate(onset_ms=onset_ms, minimum_ms=120, silence_ms=120)
                self.assertEqual(getattr(gate, 'candidate_id', None), 0,
                                 'EndpointGate must expose a candidate identity before VAD confirmation')
                self.assertEqual(gate.feed(bytes(640),voiced=False),(False,None))
                self.assertEqual(gate.candidate_id,0)
                starts=[]
                for index in range(frames):
                    began,_=gate.feed(pcm,voiced=True);starts.append(began)
                    self.assertEqual(gate.candidate_id,1)
                    self.assertEqual(began,index==frames-1)
                captured=gate.finish()
                self.assertIn(pcm*frames,captured)
                self.assertEqual(gate.candidate_id,1)
                self.assertFalse(gate.feed(pcm,voiced=True)[0])
                self.assertEqual(gate.candidate_id,2)


class NativeCandidateOnsetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.processed=0;self.gates=[]
        def gate_factory(*args,**kwargs):
            gate=EndpointGate(*args,**kwargs);self.gates.append(gate)
            original=gate.feed
            def feed(*args,**kwargs):
                value=original(*args,**kwargs);self.processed+=1;return value
            gate.feed=feed;return gate
        for name,value in (('RTCPeerConnection',Peer),('StreamingPCM16Denoiser',Denoiser),
                           ('AudioResampler',Resampler),('EndpointGate',gate_factory)):
            active=patch('native_bridge.'+name,value);active.start();self.addCleanup(active.stop)
        self.speech=Speech();self.owner=object()
        event=BackendEvent(7,'a'*32,'Boolean','Alle Angaben vorhanden. Soll ich bestellen?',
                           'control-7',self.owner)
        self.dialog=SimpleNamespace(metadata={},backend_owner=self.owner,input_control=event,
            input_boundary=dict(source='servicenow_input_control',controlType='Boolean',
                                businessRequestId='a'*32,label=event.text))
        self.call=NativeCall(Config(conversation_ws_url='ws://127.0.0.1:9',vad_silence_ms=200),
                             self.speech,self.dialog)
        self.lane=self.call.duplex;self.lane._sync_native_control()
        self.start_question()
        self.track=Track()
        self.worker=asyncio.create_task(self.call.microphone(self.track))
        self.asr=asyncio.create_task(self.call.recognize_turns())
        await until(lambda:bool(self.gates))

    async def asyncTearDown(self):
        self.call.closed=True
        for task in (self.worker,self.asr):task.cancel()
        await asyncio.gather(self.worker,self.asr,return_exceptions=True)
        await self.lane.close();await self.call.peer.close()

    def start_question(self):
        item=self.lane._outputs.popleft();state=self.lane._begin_speech(item)
        self.call.playback.put(bytes(480),self.call.playback.generation)
        self.lane._finish_speech(state,complete=True)

    def drain_question(self):self.call.playback.read(len(self.call.playback.data))

    async def feed(self,count,voiced=True):
        target=self.processed+count;self.track.feed(count,voiced)
        await until(lambda:self.processed>=target)

    async def finish_turn(self,remaining_voice=5):
        await self.feed(remaining_voice);await self.feed(10,False)
        turn=await asyncio.wait_for(self.call.recognized_turns.get(),1)
        self.call.recognized_turns.task_done()
        return turn

    async def assert_held(self,turn):
        self.assertFalse(turn.duplex_onset[0][2],
                         'VAD confirmation upgraded speech that began before complete question emission')
        await self.lane._accept(turn)
        self.assertEqual(list(self.lane._pending),[])
        self.assertEqual(self.lane._control_gate.held[-1].turn,turn)

    async def test_precompletion_candidate_stays_unheard_through_vad_and_asr(self):
        await self.feed(1)
        self.assertFalse(self.call.vad_active)
        self.drain_question()
        turn=await self.finish_turn()
        await self.assert_held(turn)
        pcm=array('h',[3000]*320).tobytes()
        self.assertEqual(self.speech.received,[pcm*6+bytes(640)*10])

    async def test_genuinely_new_postcompletion_candidate_keeps_complete_binding(self):
        self.drain_question()
        turn=await self.finish_turn(6)
        self.assertTrue(turn.duplex_onset[0][2])
        await self.lane._accept(turn)
        self.assertEqual([item[1] for item in self.lane._pending],['Ja'])
        self.assertEqual(self.lane._control_gate.held,[])

    async def test_false_candidate_reset_rebinds_the_next_fresh_candidate(self):
        await self.feed(1);await self.feed(10,False)
        self.assertEqual(self.gates[0].run,0);self.assertTrue(self.call.turns.empty())
        self.drain_question()
        turn=await self.finish_turn(6)
        self.assertTrue(turn.duplex_onset[0][2]);self.assertEqual(len(self.speech.received),1)

    async def test_expired_candidate_rebinds_before_the_new_first_frame(self):
        await self.feed(1)
        self.gates[0].pending_deadline=-1  # Real feed() performs its DTX expiry/reset.
        self.drain_question()
        turn=await self.finish_turn(6)
        self.assertTrue(turn.duplex_onset[0][2]);self.assertEqual(len(self.speech.received),1)

    async def test_new_control_during_candidate_cannot_replace_its_original_binding(self):
        await self.feed(1)
        old_binding=self.lane._control_gate.binding
        self.call.playback.interrupt()
        self.dialog.input_control=BackendEvent(8,'a'*32,'Boolean','Neue Angaben. Soll ich bestellen?',
                                               'control-8',self.owner)
        self.lane._sync_native_control();self.start_question();self.drain_question()
        turn=await self.finish_turn()
        self.assertEqual(turn.duplex_onset[0][4],old_binding)
        await self.assert_held(turn)

    async def test_interrupted_and_replayed_prompt_cannot_upgrade_earlier_candidate(self):
        await self.feed(1)
        self.lane.interrupt();self.lane._reask_control(None)
        self.start_question();self.drain_question()
        turn=await self.finish_turn()
        await self.assert_held(turn)


if __name__=='__main__':unittest.main()
