"""Offline real HTTP chunking and native incomplete-speech lifetime checks."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp import ClientPayloadError, ClientSession, web
from aiohttp.test_utils import TestServer
from native_backend import BackendEvent, ControlBinding
from native_bridge import Config, Speech
import native_duplex as duplex
from test_native_duplex import FakeCall


class TTSCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mode, self.requests = 'eos', []
        self.pcm = b'\x01\x00' * 240
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.transport = None
        app = web.Application()
        app.router.add_post('/speech', self.handle)
        self.server = TestServer(app)
        await self.server.start_server()
        self.http = ClientSession(trust_env=False)
        self.speech = Speech(self.http, Config(tts_url=str(self.server.make_url('/speech'))))
        self.call = FakeCall()
        self.call.speech = self.speech
        self.lane = duplex.NativeDuplex(self.call)
        self.tasks = []

    async def asyncTearDown(self):
        self.release.set()
        self.call.closed = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.lane.close()
        await self.http.close()
        await self.server.close()

    async def handle(self, request):
        payload = await request.json()
        self.requests.append(payload)
        self.transport = request.transport
        mode = self.mode if payload['input'] != 'Backend-Rückfrage?' else 'eos'
        response = web.StreamResponse()
        response.enable_chunked_encoding()
        await response.prepare(request)
        try:
            await response.write(self.pcm)
            self.entered.set()
            if mode == 'abort':
                # Model the server truth fix: non-EOS never writes a zero chunk.
                request.transport.close()
            elif mode == 'endless':
                while not self.release.is_set():
                    await response.write(self.pcm)
                    await asyncio.sleep(0)
            elif mode == 'stall':
                await self.release.wait()
            else:
                await response.write_eof()
        except (ConnectionError, asyncio.CancelledError):
            pass
        return response

    async def until(self, predicate, *, drain=True):
        async with asyncio.timeout(2):
            while not predicate():
                if drain:
                    self.call.playback.read(len(self.call.playback.data))
                    self.lane._update_speech_cursor()
                await asyncio.sleep(.002)

    def item(self, text='Lokaler Satz.'):
        self.lane._enqueue(text)
        item = self.lane._outputs.popleft()
        self.lane._begin_speech(item)
        return item

    async def direct(self):
        await self.lane._synthesize(self.item(), self.call.playback.generation)

    async def test_real_chunked_eos_preserves_complete_greeting_and_summary_audio(self):
        for samples in (174720, 293760):  # Saved normal 7.28 s greeting / 12.24 s summary.
            with self.subTest(samples=samples):
                self.pcm = b'\x01\x00' * samples
                item = self.item()
                task = asyncio.create_task(self.lane._synthesize(item, self.call.playback.generation))
                self.tasks.append(task)
                await self.until(task.done)
                await task
        self.assertEqual(self.call.playback.accepted_samples, 468480)
        self.assertEqual([p.get('max_new_tokens') for p in self.requests], [375, 375])

    async def test_server_abort_after_partial_pcm_is_failure_not_normal_eof_or_retry(self):
        self.mode = 'abort'
        with self.assertRaises(ClientPayloadError):
            async for _ in self.speech.synthesize('Lokaler Satz.'):
                pass
        self.assertEqual(len(self.requests), 1)

    async def test_endless_pcm_exceeds_thirty_seconds_without_becoming_success(self):
        retired = asyncio.Event()
        async def endless(text):
            try:
                for _ in range(32):
                    self.call.playback.read(len(self.call.playback.data))
                    yield b'\x01\x00' * 24000
            finally:
                retired.set()
        self.call.speech = SimpleNamespace(synthesize=endless)
        with self.assertRaisesRegex(RuntimeError, 'PCM duration limit'):
            await self.direct()
        self.assertTrue(retired.is_set())
        self.assertEqual(self.call.playback.accepted_samples, 720000)

    async def test_stalled_http_read_shares_one_absolute_deadline_and_closes_connection(self):
        self.mode = 'stall'
        with patch.object(duplex, 'TTS_SYNTHESIS_SECONDS', .08, create=True):
            task = asyncio.create_task(self.direct())
            self.tasks.append(task)
            done, _ = await asyncio.wait((task,), timeout=.5)
            self.assertIn(task, done, 'A stalled read escaped the absolute synthesis deadline')
            with self.assertRaises(TimeoutError):
                await task
        await self.until(lambda: self.transport.is_closing())

    async def test_endless_real_http_stream_is_closed_at_pcm_budget_without_retry(self):
        self.mode = 'endless'
        self.pcm = b'\x01\x00' * 24000
        task = asyncio.create_task(self.direct())
        self.tasks.append(task)
        try:
            await self.until(task.done)
        except TimeoutError:
            self.fail('The endless HTTP PCM stream escaped its delivery budget')
        with self.assertRaisesRegex(RuntimeError, 'PCM duration limit'):
            await task
        self.assertEqual(self.call.playback.accepted_samples, 720000)
        await self.until(lambda: self.transport.is_closing())
        self.assertEqual(len(self.requests), 1)

    async def test_playback_backpressure_is_inside_the_same_deadline(self):
        self.mode = 'stall'
        self.pcm = b'\x01\x00' * 96000
        with patch.object(duplex, 'TTS_SYNTHESIS_SECONDS', .08, create=True):
            task = asyncio.create_task(self.direct())
            self.tasks.append(task)
            done, _ = await asyncio.wait((task,), timeout=.5)
            self.assertIn(task, done, 'Playback backpressure escaped the synthesis deadline')
            with self.assertRaises(TimeoutError):
                await task
        await self.until(lambda: self.transport.is_closing(), drain=False)

    async def test_cancellation_explicitly_closes_the_owned_http_generator(self):
        self.mode = 'stall'
        task = asyncio.create_task(self.direct())
        self.tasks.append(task)
        await asyncio.wait_for(self.entered.wait(), 1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await self.until(lambda: self.transport.is_closing())
        self.assertEqual(len(self.requests), 1)

    async def test_source_revocation_before_pcm_explicitly_retires_generator(self):
        retired = asyncio.Event()
        async def stale(text):
            try:
                self.call.playback.interrupt()
                yield bytes(1440002)  # Revoked PCM must not trigger a new live-output failure.
            finally:
                retired.set()
        self.call.speech = SimpleNamespace(synthesize=stale)
        await self.direct()
        self.assertTrue(retired.is_set(), 'The owned generator was left open after a release guard rejected PCM')
        self.assertEqual(self.call.playback.accepted_samples, 0)

    async def test_incomplete_stream_never_publishes_full_local_transcript_and_backend_continues(self):
        self.mode = 'abort'
        owner = SimpleNamespace(is_current=lambda identity: True, close=self.noop)
        self.lane.conversation = owner
        turn = (0, 'Fakten', 1, 'a' * 32, 0)
        group = self.lane._transcripts.open(owner, turn)
        part = (group, owner, object())
        self.lane._transcripts.admit(group, owner, turn, part[2], 'Lokaler Satz.')
        self.lane._enqueue('Lokaler Satz.', turn, kind='conversation', transcript_part=part)
        self.lane._transcripts.finish(group, owner)
        speaker = asyncio.create_task(self.lane._speak_loop())
        business = asyncio.create_task(self.lane._business(turn))
        self.tasks += [speaker, business]
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Fakten')
        await self.until(lambda: self.lane._speech is not None and not self.call.synthesis_active)
        self.assertFalse(self.lane._speech['complete'])
        self.assertEqual(self.call.playback.data, b'')
        self.assertNotIn(('assistant', 'Lokaler Satz.'), self.call.events)
        self.assertFalse(business.done())
        self.call.dialog.release.put_nowait('Backend-Rückfrage?')
        await asyncio.wait_for(business, 1)
        await self.until(lambda: len(self.requests) == 2 and not self.call.synthesis_active)
        self.assertEqual(self.call.dialog.calls, ['Fakten'])
        self.assertTrue(self.lane._speech['complete'])
        self.assertEqual([p['input'] for p in self.requests], ['Lokaler Satz.', 'Backend-Rückfrage?'])

    async def noop(self):
        pass

    async def test_incomplete_native_control_is_never_marked_heard(self):
        self.mode = 'abort'
        event = BackendEvent(1, 'b' * 32, 'Boolean', 'Freigabe?', 'control', self.call.dialog.backend_owner)
        self.call.dialog.input_control = event
        binding = ControlBinding.from_event(event)
        self.lane._control_gate.observe(binding)
        self.lane._enqueue(event.text, kind='backend_control', control_binding=binding)
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        await self.until(lambda: self.lane._speech is not None and not self.call.synthesis_active)
        self.assertFalse(self.lane._speech['complete'])
        self.assertFalse(self.lane._control_gate.heard)
        self.assertFalse(self.lane._control_gate.dispatched)
        self.assertEqual(self.call.playback.data, b'')


if __name__ == '__main__':
    unittest.main()
