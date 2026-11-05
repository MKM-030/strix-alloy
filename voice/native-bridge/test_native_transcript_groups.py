"""Actual Native speech queues stream audio, then publish completed text groups."""
import asyncio
import inspect
import time
from types import SimpleNamespace
import unittest

from native_duplex import NativeDuplex
from native_backend import BackendEvent
from transcript_groups import TranscriptGroups
from test_native_duplex import FakeCall


class SentenceModel:
    sentence_streaming = True
    output_epoch = 1

    def __init__(self, sentences, *, finish=None):
        self.sentences, self.finish = sentences, finish
        self.identity = SimpleNamespace(server_session_id='offline-group-source',
                                        socket_instance='offline-group-socket')
        self.inputs = []
        self.alive = True

    def is_current(self, identity):
        return self.alive and identity is self.identity

    is_source_current = is_current

    async def close(self):
        self.alive = False

    async def invalidate(self, epoch, reason):
        self.output_epoch = epoch

    async def respond(self, raw, snapshot, key, *, on_sentence=None):
        self.inputs.append(raw)
        for text in self.sentences:
            await on_sentence(SimpleNamespace(text=text, identity=self.identity))
        if self.finish is not None:
            await self.finish.wait()
        return SimpleNamespace(text=' '.join(self.sentences), failure=None, identity=self.identity)


class NativeTranscriptGroupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.lane = NativeDuplex(self.call)
        self.tasks = []
        self.turn = (0, 'Welche Angaben fehlen noch?', 1, 'grouped-original', time.monotonic())

    async def asyncTearDown(self):
        self.call.closed = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.lane.close()

    def start(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task

    def speaker(self):
        self.start(self.lane._speak_loop())
        self.start(self.lane._update_loop())

    async def until(self, predicate):
        async with asyncio.timeout(1):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.005)

    def texts(self):
        return [text for role, text in self.call.events if role == 'assistant']

    async def generate(self, model):
        self.lane.conversation = model
        self.lane._observe_raw(self.turn[1])
        await self.lane._general_help(self.turn, self.lane.epoch)

    async def test_audio_starts_before_response_eos_but_two_sentences_form_one_transcript(self):
        end = asyncio.Event()
        sentences = ['Wir können die Angaben gemeinsam klären.', 'Wann ist das Eintrittsdatum?']
        model = SentenceModel(sentences, finish=end)
        generating = self.start(self.generate(model))
        self.speaker()
        await self.until(lambda: self.call.playback.accepted_samples > 0)
        self.assertFalse(generating.done())
        self.assertEqual(self.texts(), [], 'Transcript text must wait for actual completed response parts')
        end.set()
        await generating
        await self.until(lambda: self.texts() == [' '.join(sentences)])
        self.assertEqual(self.call.spoken, sentences)
        self.assertEqual(model.inputs, [self.turn[1]])
        self.assertEqual(self.call.dialog.calls, [])

    async def test_skipped_storage_claim_never_enters_the_group(self):
        unsafe = 'Danke, ich habe Ihre Angaben notiert.'
        safe = 'Wann ist das Eintrittsdatum?'
        await self.generate(SentenceModel([unsafe, safe]))
        self.speaker()
        await self.until(lambda: bool(self.texts()))
        self.assertEqual(self.call.spoken, [safe])
        self.assertEqual(self.texts(), [safe])

    async def test_interrupted_later_sentence_publishes_only_the_completed_first_sentence(self):
        first, second = 'Wir können die Angaben gemeinsam klären.', 'Wann ist das Eintrittsdatum?'
        partial = asyncio.Event()
        async def synthesize(text):
            self.call.spoken.append(text)
            yield b'\x01\x00' * 240
            if text == second:
                partial.set()
                await asyncio.Event().wait()
        self.call.speech.synthesize = synthesize
        await self.generate(SentenceModel([first, second]))
        self.speaker()
        await self.until(partial.is_set)
        self.lane.interrupt()
        await self.until(lambda: bool(self.texts()))
        self.assertEqual(self.texts(), [first])
        self.assertEqual(self.call.spoken, [first, second])

    async def test_soft_completion_change_keeps_active_tail_and_only_its_completed_text(self):
        first, second = 'Wir können die Angaben gemeinsam klären.', 'Wann ist das Eintrittsdatum?'
        release = asyncio.Event()
        first_pcm = asyncio.Event()
        end = asyncio.Event()
        async def synthesize(text):
            self.call.spoken.append(text)
            yield b'\x01\x00' * 240
            first_pcm.set()
            await release.wait()
            yield b'\x02\x00' * 240
        self.call.speech.synthesize = synthesize
        generating = self.start(self.generate(SentenceModel([first, second], finish=end)))
        self.speaker()
        await self.until(first_pcm.is_set)
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            businessRequestId='c' * 32, controlType='InputText', label='Welche Lieferadresse gilt?')
        self.call.dialog.observation_revision += 1
        end.set()
        await generating
        release.set()
        await self.until(lambda: bool(self.texts()))
        self.assertEqual(self.call.spoken, [first])
        self.assertEqual(self.call.playback.emitted_samples, 480)
        self.assertEqual(self.texts(), [first])

    async def test_source_closure_before_actual_read_publishes_no_unheard_group(self):
        model = SentenceModel(['Wir können die Angaben gemeinsam klären.'])
        await self.generate(model)
        self.speaker()
        await self.until(lambda: self.call.playback.accepted_samples > 0)
        self.assertEqual(self.call.playback.emitted_samples, 0)
        model.alive = False
        self.call.playback.read(len(self.call.playback.data))
        self.lane._update_speech_cursor()
        self.assertEqual(self.call.playback.emitted_samples, 0)
        self.assertEqual(self.texts(), [])

    async def test_real_backend_handoff_flushes_completed_local_prefix_first(self):
        first, second = 'Wir können die Angaben gemeinsam klären.', 'Wann ist das Eintrittsdatum?'
        release = asyncio.Event()
        async def synthesize(text):
            self.call.spoken.append(text)
            yield bytes(480)
            if text == first:
                await release.wait()
        self.call.speech.synthesize = synthesize
        await self.generate(SentenceModel([first, second]))
        self.speaker()
        await self.until(lambda: self.call.playback.accepted_samples > 0)
        self.call.vad_active = True
        release.set()
        await self.until(lambda: self.lane._speech.get('history_recorded'))
        self.assertEqual(self.texts(), [])
        self.call.dialog.business_request_id = 'b' * 32
        result = 'ServiceNow hat die Angaben zur Prüfung übernommen.'
        self.assertTrue(self.lane._admit_backend_event(BackendEvent(70, 'b' * 32, 'OutputText',
            result, '', self.call.dialog.backend_owner), self.turn))
        self.call.dialog.observation_revision += 1
        self.call.vad_active = False
        await self.until(lambda: result in self.texts())
        self.assertEqual(self.texts(), [first, result])
        self.assertEqual(self.call.spoken, [first, result])

    async def test_transcript_overflow_does_not_interrupt_audio_or_add_a_fallback(self):
        self.lane._transcripts = TranscriptGroups(max_chars=15)
        sentences = ['Wir können die Angaben gemeinsam klären.', 'Wann ist das Eintrittsdatum?']
        with self.assertLogs('native-voice', level='INFO') as logs:
            await self.generate(SentenceModel(sentences))
        self.assertIn('stage=bounded_overflow', '\n'.join(logs.output))
        self.speaker()
        await self.until(lambda: len(self.call.spoken) == 2 and self.call.playback.emitted_samples > 0)
        self.assertEqual(self.call.spoken, sentences)
        self.assertFalse(self.lane._model_failed)
        self.assertEqual(self.texts(), [])

    async def test_genuine_boolean_is_an_assistant_transcript_with_typed_stop_metadata(self):
        event = BackendEvent(7, 'a' * 32, 'Boolean', 'Soll ich das bestellen?',
                             'control-7', self.call.dialog.backend_owner)
        self.call.dialog.input_control = event
        self.call.dialog.input_boundary = dict(source='servicenow_input_control', controlType='Boolean',
            businessRequestId=event.business_request_id, label=event.text)
        typed = []
        def transcript(turn, role, text, *, started_at=None, control_type=None):
            typed.append((turn, role, text, control_type))
        self.call.transcript = transcript
        self.lane._sync_native_control()
        self.speaker()
        await self.until(lambda: self.call.playback.accepted_samples > 0)
        self.assertEqual(typed, [(None, 'assistant', event.text, 'Boolean')])


class DelayedTranscriptLatencyTests(unittest.TestCase):
    def test_grouped_event_keeps_the_first_pcm_latency_instead_of_text_flush_time(self):
        from native_bridge import NativeCall
        self.assertIn('started_at', inspect.signature(NativeCall.transcript).parameters,
                      'Delayed transcript groups need the original first-PCM timestamp')
        call = NativeCall.__new__(NativeCall)
        events = []
        call.emit = lambda kind, value: events.append((kind, value))
        call.transcript((0, '', 7, 'original-turn', 10.0), 'assistant', 'Ein vollständiger Absatz.',
                        started_at=11.25)
        self.assertEqual(events[0][0], 'transcript')
        self.assertEqual(events[0][1]['latency_ms'], 1250)
        self.assertEqual(events[0][1]['caller_turn_id'], 'original-turn')

    def test_genuine_control_metadata_does_not_fabricate_a_caller_turn(self):
        from native_bridge import NativeCall
        self.assertIn('control_type', inspect.signature(NativeCall.transcript).parameters,
                      'A validated native control needs typed transcript metadata')
        call = NativeCall.__new__(NativeCall)
        events = []
        call.emit = lambda kind, value: events.append((kind, value))
        call.transcript(None, 'assistant', 'Soll ich das bestellen?', control_type='Boolean')
        data = events[0][1]
        self.assertEqual((data['role'], data['source'], data['control_type']),
                         ('assistant', 'servicenow_input_control', 'Boolean'))
        self.assertEqual(data['caller_turn_id'], '')
        self.assertEqual(data['turn_num'], 0)


if __name__ == '__main__':
    unittest.main()
