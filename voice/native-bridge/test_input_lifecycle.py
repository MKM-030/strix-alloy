"""Terminal input lifecycle tests using actual source and aiohttp routes.

RTC/PyAV are deliberately substituted here; these tests do not validate RTP,
browser media, real inference or ServiceNow. Existing transport tests own RTP.
"""
import ast
import asyncio
from array import array
import importlib.util
import json
import logging
from pathlib import Path
import time
import types
import unittest
import uuid

from aiohttp import ClientSession, ClientTimeout, WSMsgType, WSServerHandshakeError, web

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('input_lifecycle_core', ROOT / 'core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class Peer:
    instances = []
    def __init__(self, configuration):
        self.handlers = {}
        self.connectionState = 'connected'
        self.iceConnectionState = 'completed'
        self.instances.append(self)
    def on(self, event, handler): self.handlers[event] = handler
    def addTrack(self, track): pass
    async def close(self): self.connectionState = self.iceConnectionState = 'closed'


class Resampler:
    def __init__(self, **kwargs): pass
    def resample(self, frame): return [frame]


class Frame:
    def __init__(self, loud=True): self.samples = array('h', [3000 if loud else 0] * 320)
    def to_ndarray(self): return self.samples


class Microphone:
    kind = 'audio'
    readyState = 'live'
    def __init__(self): self.frames = asyncio.Queue()
    def feed(self, loud=20, quiet=0):
        for _ in range(loud): self.frames.put_nowait(Frame())
        for _ in range(quiet): self.frames.put_nowait(Frame(False))
    def end(self): self.frames.put_nowait(None)
    async def recv(self):
        frame = await self.frames.get()
        if frame is None:
            self.readyState = 'ended'
            raise RuntimeError('synthetic microphone failure with forbidden secret')
        return frame


class Speech:
    def __init__(self):
        self.recognized = []
        self.transcribing = asyncio.Event()
        self.hold_asr = False
        self.release_asr = asyncio.Event()
        self.asr_cancelled = asyncio.Event()
        self.asr_cancel_delay = 0
    async def transcribe(self, pcm):
        self.transcribing.set()
        if self.hold_asr:
            try:
                await self.release_asr.wait()
            except asyncio.CancelledError:
                self.asr_cancelled.set()
                if self.asr_cancel_delay:
                    await asyncio.sleep(self.asr_cancel_delay)
                raise
        self.recognized.append(pcm)
        return 'synthetic input'
    async def synthesize(self, text):
        yield bytes(960)


class Dialog:
    metadata = {}
    def __init__(self):
        self.opened = asyncio.Event()
        self.turn_started = asyncio.Event()
        self.release_turn = asyncio.Event()
        self.turn_finished = asyncio.Event()
        self.hold_turn = False
        self.fail_turn = False
        self.deliver_before_release = False
        self.received = []
        self.cancelled = False
        self.close_count = 0
        self.close_started = asyncio.Event()
        self.hold_close = False
        self.release_close = asyncio.Event()
    async def open(self):
        self.opened.set()
        return []
    async def turn(self, text, on_reply=None):
        self.received.append(text)
        self.turn_started.set()
        try:
            if self.deliver_before_release and on_reply:
                await on_reply('synthetic reply')
            if self.hold_turn:
                await self.release_turn.wait()
            if self.fail_turn:
                raise RuntimeError('synthetic backend failure')
            if not self.deliver_before_release and on_reply:
                await on_reply('synthetic reply')
            self.turn_finished.set()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
    async def close(self):
        self.close_count += 1
        self.close_started.set()
        if self.hold_close:
            await self.release_close.wait()


namespace = dict(asyncio=asyncio, time=time, uuid=uuid, json=json,
    LOG=logging.getLogger('native-voice'), AudioResampler=Resampler,
    RTCPeerConnection=Peer, RTCConfiguration=lambda **kwargs:kwargs,
    SpeakerTrack=lambda playback:object(), EndpointGate=core.EndpointGate,
    PlaybackBuffer=core.PlaybackBuffer, local_auth=core.local_auth,
    authorized_agents=core.authorized_agents, ClientSession=ClientSession,
    ClientTimeout=ClientTimeout, WSMsgType=WSMsgType, web=web,
    HTTP_KEY=web.AppKey('http', ClientSession))
source = ast.parse((ROOT / 'native_bridge.py').read_text())
selected = [node for node in source.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {'NativeCall', 'authorize', 'create_app'}]
exec(compile(ast.Module(body=selected, type_ignores=[]), '<actual-native-source>', 'exec'), namespace)
NativeCall, create_app = namespace['NativeCall'], namespace['create_app']


def configuration():
    return types.SimpleNamespace(vad_threshold=450, vad_silence_ms=1200,
        instance_name='unit-test', voice_service_id='unit-test', auth_mode='deny',
        instance_url='https://unit-test.service-now.com',
        development_token='synthetic-loopback-only-credential-for-test',
        max_call_seconds=30, greeting='')


async def until(predicate, message='condition did not become true', timeout=1):
    try:
        async with asyncio.timeout(timeout):
            while not predicate(): await asyncio.sleep(.005)
    except TimeoutError:
        raise AssertionError(message) from None


class InputLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.speech, self.dialog = Speech(), Dialog()
        self.call = NativeCall(configuration(), self.speech, self.dialog)
        self.worker = self.call.spawn(self.call.process_turns())
        await self.dialog.opened.wait()
        self.microphone = Microphone()
        self.mic_task = self.call.peer.handlers['track'](self.microphone)

    async def asyncTearDown(self):
        self.dialog.release_turn.set()
        self.dialog.release_close.set()
        self.speech.release_asr.set()
        await self.call.close()

    def notices(self):
        return [message for message in self.call.pending_events
                if message['type'] == 'transcript' and message['data'].get('code') == 'INPUT_LOST']

    async def lose_microphone(self):
        self.microphone.end()
        await self.mic_task
        await until(lambda:bool(self.notices()), 'terminal microphone loss was silent')

    async def hold_first_turn(self):
        self.dialog.hold_turn = True
        await self.call.turns.put((0, b'\x01\x00' * 1000))
        await self.dialog.turn_started.wait()

    async def test_partial_utterance_is_not_submitted_and_terminal_loss_is_visible(self):
        self.microphone.feed(20)
        await self.lose_microphone()
        await until(self.worker.done, 'idle conversation worker did not settle')
        self.assertEqual(self.dialog.received, [])
        self.assertEqual(self.speech.recognized, [])
        self.assertEqual(len(self.notices()), 1)
        self.assertFalse(any(message['type'] == 'error' for message in self.call.pending_events))
        await self.call.close()
        self.assertEqual(self.call.turns._unfinished_tasks, 0)
        self.assertEqual(self.call.recognized_turns._unfinished_tasks, 0)

    async def test_terminal_close_waits_for_submitted_turn_without_cancellation(self):
        await self.hold_first_turn()
        await self.lose_microphone()
        closing = asyncio.create_task(self.call.close())
        await asyncio.sleep(.02)
        self.assertFalse(closing.done())
        self.assertFalse(self.dialog.cancelled)
        self.assertEqual(self.dialog.close_count, 0)
        self.dialog.release_turn.set()
        await asyncio.wait_for(closing, 1)
        self.assertTrue(self.dialog.turn_finished.is_set())
        self.assertFalse(self.dialog.cancelled)
        self.assertEqual(self.dialog.close_count, 1)

    async def test_full_playback_after_receiver_loss_does_not_block_turn_settlement(self):
        self.dialog.deliver_before_release = True
        self.dialog.hold_turn = True
        self.call.playback.put(bytes(60000), 0)
        await self.call.turns.put((0, b'\x01\x00' * 1000))
        await self.dialog.turn_started.wait()
        await self.lose_microphone()
        self.assertEqual(len(self.call.playback.data), 0)
        self.dialog.release_turn.set()
        await until(self.worker.done, 'lost speaker left delivery backpressure stuck')
        self.assertTrue(self.dialog.turn_finished.is_set())
        self.assertFalse(self.dialog.cancelled)

    async def test_live_second_receiver_prevents_terminal_loss(self):
        second = Microphone()
        second_task = self.call.peer.handlers['track'](second)
        self.microphone.end()
        await self.mic_task
        await asyncio.sleep(.3)
        self.assertEqual(self.notices(), [])
        self.assertFalse(self.worker.done())
        second.feed(20, 70)
        await until(lambda:len(self.dialog.received) == 1)
        self.assertFalse(second_task.done())

    async def test_replacement_during_grace_keeps_input_running(self):
        self.microphone.end()
        await self.mic_task
        await asyncio.sleep(.1)
        second = Microphone()
        self.call.peer.handlers['track'](second)
        await asyncio.sleep(.2)
        self.assertEqual(self.notices(), [])
        second.feed(20, 70)
        await until(lambda:len(self.dialog.received) == 1)

    async def test_replacement_after_terminal_commit_cannot_restart_input(self):
        await self.lose_microphone()
        second = Microphone()
        second.feed(20, 70)
        second.end()
        task = self.call.peer.handlers['track'](second)
        if task: await task
        await asyncio.sleep(.02)
        self.assertEqual(self.speech.recognized, [])
        self.assertEqual(self.dialog.received, [])
        self.assertEqual(len(self.notices()), 1)

    async def test_loss_cancels_local_asr_and_discards_unsent_queues(self):
        await self.hold_first_turn()
        self.speech.hold_asr = True
        self.speech.transcribing.clear()
        await self.call.turns.put((0, b'\x02\x00' * 1000))
        await self.speech.transcribing.wait()
        await self.call.turns.put((0, b'\x03\x00' * 1000))
        await self.call.recognized_turns.put((0, 'unsent', 2, 'synthetic-id', time.monotonic()))
        await self.lose_microphone()
        await until(self.speech.asr_cancelled.is_set)
        self.dialog.release_turn.set()
        await until(self.worker.done)
        await self.call.close()
        self.assertEqual(self.dialog.received, ['synthetic input'])
        self.assertEqual(self.call.turns._unfinished_tasks, 0)
        self.assertEqual(self.call.recognized_turns._unfinished_tasks, 0)

    async def test_normal_close_cancels_pending_local_asr_without_terminal_notice(self):
        self.speech.hold_asr = True
        await self.call.turns.put((0, b'\x01\x00' * 1000))
        await self.speech.transcribing.wait()
        await self.call.close()
        self.assertTrue(self.speech.asr_cancelled.is_set())
        self.assertEqual(self.notices(), [])
        self.assertTrue(self.mic_task.cancelled())

    async def test_queued_turn_cannot_submit_while_asr_cancellation_yields(self):
        self.speech.hold_asr = True
        self.speech.asr_cancel_delay = .05
        await self.call.turns.put((0, b'\x01\x00' * 1000))
        await self.speech.transcribing.wait()
        await self.lose_microphone()
        await self.speech.asr_cancelled.wait()
        await self.call.recognized_turns.put((0, 'unsent', 1, 'synthetic-id', time.monotonic()))
        await until(self.worker.done)
        self.assertEqual(self.dialog.received, [])
        await self.call.close()
        self.assertEqual(self.call.recognized_turns._unfinished_tasks, 0)

    async def test_two_receiver_failures_emit_only_one_terminal_notice(self):
        second = Microphone()
        second_task = self.call.peer.handlers['track'](second)
        self.microphone.end()
        second.end()
        await asyncio.gather(self.mic_task, second_task)
        await until(lambda:bool(self.notices()))
        self.assertEqual(len(self.notices()), 1)
        await until(self.worker.done)

    async def test_backend_failure_after_terminal_loss_still_finishes_cleanup(self):
        await self.hold_first_turn()
        self.dialog.fail_turn = True
        await self.lose_microphone()
        self.dialog.release_turn.set()
        await until(self.worker.done)
        await self.call.close()
        self.assertFalse(self.dialog.cancelled)
        self.assertEqual(self.dialog.close_count, 1)

    async def test_reply_delivery_failure_after_loss_cannot_abort_submitted_turn(self):
        await self.hold_first_turn()
        await self.lose_microphone()
        self.call.transcript = lambda *args: (_ for _ in ()).throw(RuntimeError('forbidden secret'))
        self.dialog.release_turn.set()
        await until(self.worker.done)
        self.assertTrue(self.dialog.turn_finished.is_set(),
                        'terminal output delivery aborted submitted-turn observation')
        self.assertFalse(self.dialog.cancelled)

    async def test_terminal_notice_survives_full_pending_event_buffer(self):
        self.call.pending_events[:] = [{'type':'metadata', 'data':{}} for _ in range(30)]
        await self.lose_microphone()
        self.assertEqual(len(self.notices()), 1)
        self.assertLessEqual(len(self.call.pending_events), 30)

    async def test_backend_failure_after_loss_does_not_refill_lost_speaker_buffer(self):
        await self.hold_first_turn()
        self.dialog.fail_turn = True
        await self.lose_microphone()
        async def oversized_failure_audio(text):
            yield bytes(60000)
            yield bytes(960)
        self.speech.synthesize = oversized_failure_audio
        self.dialog.release_turn.set()
        await until(self.worker.done, 'terminal backend failure waited on lost-speaker feedback')
        self.assertEqual(len(self.call.playback.data), 0)

    async def test_concurrent_close_waits_for_one_owned_cleanup(self):
        self.dialog.hold_close = True
        first = asyncio.create_task(self.call.close())
        await self.dialog.close_started.wait()
        second = asyncio.create_task(self.call.close())
        await asyncio.sleep(.02)
        self.assertFalse(first.done())
        self.assertFalse(second.done())
        self.dialog.release_close.set()
        await asyncio.wait_for(asyncio.gather(first, second), 1)
        self.assertEqual(self.dialog.close_count, 1)

    async def test_feedback_failure_does_not_prevent_input_cleanup(self):
        self.call.notice = lambda *args: (_ for _ in ()).throw(RuntimeError('forbidden secret'))
        self.microphone.end()
        await self.mic_task
        await until(self.worker.done, 'feedback send failure prevented worker settlement')
        await self.call.close()
        self.assertEqual(self.dialog.close_count, 1)

    async def test_microphone_failure_log_has_type_counters_and_no_exception_text(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            self.microphone.feed(20)
            self.microphone.end()
            await self.mic_task
        output = '\n'.join(logs.output)
        self.assertIn('stage=track_failed', output)
        self.assertIn('type=RuntimeError', output)
        self.assertIn('frames=20', output)
        self.assertIn('audio_ms=400', output)
        self.assertNotIn('forbidden secret', output)


class RouteLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dialog, self.speech, self.config = Dialog(), Speech(), configuration()
        self.app = create_app(self.config, speech_factory=lambda http:self.speech,
                              dialog_factory=lambda:self.dialog)
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.base = f'http://127.0.0.1:{port}'
        self.params = dict(instance_name=self.config.instance_name,
                           voice_service_id=self.config.voice_service_id,
                           auth_token=self.config.development_token)
        self.http = ClientSession()
        self.sockets = []
    async def asyncTearDown(self):
        self.dialog.release_turn.set()
        self.dialog.release_close.set()
        for socket in self.sockets: await socket.close()
        await self.http.close()
        await self.runner.cleanup()
    async def connect(self):
        socket = await self.http.ws_connect(self.base + '/webrtc/connect/agent_operator', params=self.params)
        self.sockets.append(socket)
        return socket
    async def sessions(self):
        async with self.http.get(self.base + '/health') as response:
            return (await response.json())['nativeSessions']
    async def released(self):
        try:
            async with asyncio.timeout(1):
                while await self.sessions(): await asyncio.sleep(.005)
        except TimeoutError:
            raise AssertionError('terminal idle microphone retained the sole session slot') from None
    async def end_receiver(self):
        track = Microphone()
        task = Peer.instances[-1].handlers['track'](track)
        track.feed(20)
        track.end()
        await task

    async def test_terminal_idle_loss_releases_slot_after_owned_cleanup(self):
        await self.connect()
        await self.end_receiver()
        await self.released()
        self.assertEqual(self.dialog.close_count, 1)
        await self.connect()
        self.assertEqual(await self.sessions(), 1)

    async def test_terminal_loss_waits_for_owned_reset_before_admitting_reconnect(self):
        self.dialog.hold_close = True
        await self.connect()
        await self.end_receiver()
        try:
            await asyncio.wait_for(self.dialog.close_started.wait(), 1)
        except TimeoutError:
            self.fail('terminal loss never began owned cleanup')
        self.assertEqual(await self.sessions(), 1)
        with self.assertRaises(WSServerHandshakeError) as denied:
            await self.connect()
        self.assertEqual(denied.exception.status, 503)
        self.dialog.release_close.set()
        await self.released()
        await self.connect()

    async def test_admission_logs_only_status_and_safe_identifiers(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            with self.assertRaises(WSServerHandshakeError) as denied:
                await self.http.ws_connect(self.base + '/webrtc/connect/agent_operator',
                    params={**self.params, 'auth_token':'invalid-forbidden-secret'})
            self.assertEqual(denied.exception.status, 401)
            await self.connect()
            with self.assertRaises(WSServerHandshakeError) as busy:
                await self.connect()
            self.assertEqual(busy.exception.status, 503)
        output = '\n'.join(logs.output)
        for status in ('status=401', 'status=101', 'status=503'):
            self.assertIn(status, output)
        self.assertIn('call=', output)
        self.assertNotIn('auth_token', output)
        self.assertNotIn(self.config.development_token, output)
        self.assertNotIn('invalid-forbidden-secret', output)
        self.assertNotIn(self.base, output)

    async def test_client_socket_close_after_terminal_loss_preserves_inflight_turn(self):
        self.dialog.hold_turn = True
        socket = await self.connect()
        call = Peer.instances[-1].handlers['datachannel'].__self__
        await call.turns.put((0, b'\x01\x00' * 1000))
        await self.dialog.turn_started.wait()
        await self.end_receiver()
        await until(lambda:any(message.get('data', {}).get('code') == 'INPUT_LOST'
                               for message in call.pending_events))
        await socket.close()
        await asyncio.sleep(.02)
        self.assertFalse(self.dialog.cancelled)
        self.assertEqual(self.dialog.close_count, 0)
        self.assertEqual(await self.sessions(), 1)
        self.dialog.release_turn.set()
        await self.released()
        self.assertTrue(self.dialog.turn_finished.is_set())
        self.assertEqual(self.dialog.close_count, 1)

    async def test_call_timeout_after_terminal_loss_preserves_inflight_turn(self):
        self.config.max_call_seconds = .4
        self.dialog.hold_turn = True
        await self.connect()
        call = Peer.instances[-1].handlers['datachannel'].__self__
        await call.turns.put((0, b'\x01\x00' * 1000))
        await self.dialog.turn_started.wait()
        await self.end_receiver()
        await until(lambda:any(message.get('data', {}).get('code') == 'INPUT_LOST'
                               for message in call.pending_events))
        await asyncio.sleep(.2)
        self.assertFalse(self.dialog.cancelled)
        self.assertEqual(self.dialog.close_count, 0)
        self.assertEqual(await self.sessions(), 1)
        self.dialog.release_turn.set()
        await self.released()
        self.assertTrue(self.dialog.turn_finished.is_set())

    async def test_cancelled_handler_retains_slot_until_owned_cleanup_finishes(self):
        self.dialog.hold_close = True
        socket = await self.connect()
        await socket.close()
        await self.dialog.close_started.wait()
        # This runner has one native route. Cancel only that test-owned handler,
        # never the independent shielded owned-cleanup task.
        handler_tasks = [task for task in asyncio.all_tasks()
                         if getattr(task.get_coro(), '__qualname__', '') == 'RequestHandler._handle_request']
        self.assertEqual(len(handler_tasks), 1)
        handler_tasks[0].cancel()
        await asyncio.gather(*handler_tasks, return_exceptions=True)
        self.assertEqual(await self.sessions(), 1,
                         'request cancellation released capacity before owned reset finished')
        self.dialog.release_close.set()
        await self.released()

    async def test_repeated_handler_cancellation_still_starts_owned_cleanup(self):
        await self.connect()
        await self.dialog.opened.wait()
        handler_tasks = [task for task in asyncio.all_tasks()
                         if getattr(task.get_coro(), '__qualname__', '') == 'RequestHandler._handle_request']
        self.assertEqual(len(handler_tasks), 1)
        handler = handler_tasks[0]
        handler.cancel()
        asyncio.get_running_loop().call_soon(handler.cancel)
        await asyncio.gather(handler, return_exceptions=True)
        await until(self.dialog.close_started.is_set,
                    'repeated cancellation bypassed owned cleanup startup')
        await self.released()


if __name__ == '__main__':
    unittest.main(verbosity=2)
