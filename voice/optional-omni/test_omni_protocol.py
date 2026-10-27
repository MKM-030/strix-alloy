"""Protocol-only fake WebSocket tests; no Omni process or ServiceNow endpoint."""
import asyncio
import importlib.util
from pathlib import Path
import struct
import unittest


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.incoming = asyncio.Queue()
        self.closed = False

    async def send_json(self, value):
        self.sent.append(value)

    async def receive_json(self):
        return await self.incoming.get()

    async def close(self):
        self.closed = True

    def feed(self, *events):
        for event in events:
            self.incoming.put_nowait(event)


class OmniProtocolTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name('omni_protocol.py')
        assert path.is_file(), 'optional protocol is not implemented'
        spec = importlib.util.spec_from_file_location('task6_omni_protocol', path)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    async def asyncSetUp(self):
        self.socket = FakeSocket()
        self.client = self.mod.TextSession(self.socket, handshake_seconds=.1, turn_seconds=.1)
        self.socket.feed({'type': 'session.ready', 'mode': 'text', 'session_id': 'synthetic-session'})
        await self.client.start('Synthetic isolated conversation only.')

    def complete(self, turn=1, generation=1, text='Synthetische Antwort'):
        self.socket.feed({'type': 'input.committed', 'turn_id': turn, 'text': True},
                         {'type': 'response.created', 'turn_id': turn, 'generation_id': generation},
                         {'type': 'response.text.delta', 'generation_id': generation, 'delta': 'partial'},
                         {'type': 'response.text.done', 'generation_id': generation, 'text': text},
                         {'type': 'metrics', 'turn_id': turn, 'generation_id': generation, 'cancelled': False})

    async def test_text_turn_binds_server_ids_to_local_request_and_uses_done(self):
        self.complete()
        result = await self.client.turn('local-request-1', 'Hallo')
        self.assertEqual(result, {'request_id': 'local-request-1', 'turn_id': 1, 'generation_id': 1,
                                  'text': 'Synthetische Antwort', 'cancelled': False})
        self.assertEqual(self.socket.sent, [
            {'type': 'session.start', 'mode': 'text', 'system_prompt': 'Synthetic isolated conversation only.', 'language': 'de'},
            {'type': 'input.text', 'text': 'Hallo'}])

    async def test_old_generation_chunks_and_metrics_cannot_complete_new_turn(self):
        self.complete()
        await self.client.turn('r1', 'eins')
        self.socket.feed({'type': 'response.text.done', 'generation_id': 1, 'text': 'STALE'},
                         {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': False})
        self.complete(2, 2, 'Frisch')
        result = await self.client.turn('r2', 'zwei')
        self.assertEqual(result['text'], 'Frisch')

    async def test_future_generation_or_wrong_turn_closes_socket(self):
        self.socket.feed({'type': 'input.committed', 'turn_id': 1, 'text': True},
                         {'type': 'response.created', 'turn_id': 2, 'generation_id': 1})
        with self.assertRaises(self.mod.ProtocolError):
            await self.client.turn('r1', 'eins')
        self.assertTrue(self.socket.closed)

    async def test_cancel_before_generation_suppresses_late_text_and_waits_for_metrics(self):
        task = asyncio.create_task(self.client.turn('r1', 'eins'))
        await asyncio.sleep(0)
        await self.client.cancel()
        self.socket.feed({'type': 'input.committed', 'turn_id': 1, 'text': True},
                         {'type': 'response.created', 'turn_id': 1, 'generation_id': 1},
                         {'type': 'response.text.delta', 'generation_id': 1, 'delta': 'NOT HEARD'},
                         {'type': 'response.cancelled', 'turn_id': 1, 'generation_id': 1, 'kept_text': 'emitted'},
                         {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': True})
        result = await task
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['text'], '')
        self.assertIn({'type': 'response.cancel'}, self.socket.sent)

    async def test_cancel_racing_done_still_suppresses_output(self):
        task = asyncio.create_task(self.client.turn('r1', 'eins'))
        await asyncio.sleep(0)
        await self.client.cancel()
        self.complete()
        result = await task
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['text'], '')

    async def test_update_appends_context_once_and_never_fabricates_turn(self):
        await self.client.update_context('Synthetic trusted state change.')
        self.assertEqual(self.socket.sent[-1], {'type': 'session.update', 'system_prompt_patch': 'Synthetic trusted state change.'})
        self.assertFalse(any(event['type'] == 'input.text' for event in self.socket.sent))

    async def test_context_update_waits_for_active_turn(self):
        turn = asyncio.create_task(self.client.turn('r1', 'eins'))
        await asyncio.sleep(0)
        update = asyncio.create_task(self.client.update_context('next context'))
        await asyncio.sleep(0)
        self.assertFalse(update.done())
        self.complete()
        await turn
        await update
        self.assertEqual(self.socket.sent[-1]['type'], 'session.update')

    async def test_timeout_closes_failed_socket_and_prevents_reuse(self):
        with self.assertRaises(self.mod.ProtocolError):
            await self.client.turn('r1', 'eins')
        self.assertTrue(self.socket.closed)
        with self.assertRaises(self.mod.ProtocolError):
            await self.client.turn('r2', 'zwei')

    async def test_metrics_without_done_cannot_make_up_answer(self):
        self.socket.feed({'type': 'input.committed', 'turn_id': 1, 'text': True},
                         {'type': 'response.created', 'turn_id': 1, 'generation_id': 1},
                         {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': False})
        with self.assertRaises(self.mod.ProtocolError):
            await self.client.turn('r1', 'eins')

    async def test_server_error_does_not_leak_remote_text(self):
        self.socket.feed({'type': 'error', 'code': 'ENGINE_FAILED', 'message': 'PRIVATE-REMOTE-TEXT'})
        with self.assertRaises(self.mod.ProtocolError) as error:
            await self.client.turn('r1', 'eins')
        self.assertNotIn('PRIVATE-REMOTE-TEXT', str(error.exception))

    async def test_playback_state_is_generation_bound_not_action_commit(self):
        self.complete()
        await self.client.turn('r1', 'eins')
        self.assertFalse(await self.client.playback_state(999, 100))
        self.assertTrue(await self.client.playback_state(1, 100))
        self.assertEqual(self.socket.sent[-1], {'type': 'playback.state', 'generation_id': 1, 'played_ms': 100})

    async def test_pcm16_framing_discards_wrong_generation(self):
        frame = b'OMNI' + struct.pack('<III', 7, 1, 4) + b'\0\0\1\0'
        self.assertIsNone(self.mod.decode_audio_frame(frame, generation_id=8))
        self.assertEqual(self.mod.decode_audio_frame(frame, generation_id=7), (1, b'\0\0\1\0'))
        with self.assertRaises(self.mod.ProtocolError):
            self.mod.decode_audio_frame(frame[:-1], generation_id=7)
        self.assertEqual(self.mod.pcm16_input(b'\0\0'), b'\0\0')
        with self.assertRaises(self.mod.ProtocolError):
            self.mod.pcm16_input(b'\0')

    async def test_stuck_close_cannot_extend_handshake_failure_indefinitely(self):
        class Stuck(FakeSocket):
            async def close(inner):
                await asyncio.Event().wait()
        client = self.mod.TextSession(Stuck(), handshake_seconds=.01)
        client.cleanup_seconds = .01
        async with asyncio.timeout(.2):
            with self.assertRaises(self.mod.ProtocolError):
                await client.start('synthetic')
        self.assertTrue(client.closed)

    async def test_stuck_close_releases_turn_and_queued_context(self):
        async def stuck():
            await asyncio.Event().wait()
        self.socket.close = stuck
        client = self.mod.TextSession(self.socket, turn_seconds=.01)
        client.cleanup_seconds = .01
        self.socket.feed({'type': 'session.ready', 'mode': 'text', 'session_id': 'synthetic'})
        await client.start('synthetic')
        async with asyncio.timeout(.2):
            turn = asyncio.create_task(client.turn('r1', 'eins'))
            await asyncio.sleep(0)
            update = asyncio.create_task(client.update_context('later'))
            with self.assertRaises(self.mod.ProtocolError):
                await turn
            with self.assertRaises(self.mod.ProtocolError):
                await update
        self.assertFalse(client.lock.locked())

    async def test_stuck_control_sends_and_close_have_deadlines(self):
        for operation in ('cancel', 'update_context', 'playback_state', 'close'):
            with self.subTest(operation=operation):
                socket = FakeSocket()
                client = self.mod.TextSession(socket)
                client.control_seconds = client.cleanup_seconds = .01
                socket.feed({'type': 'session.ready', 'mode': 'text', 'session_id': 'synthetic'})
                await client.start('synthetic')
                async def stuck(value):
                    await asyncio.Event().wait()
                socket.send_json = stuck
                client.active = operation == 'cancel'
                client.last_generation = 1
                args = {'cancel': (), 'update_context': ('state',), 'playback_state': (1, 1), 'close': ()}[operation]
                async with asyncio.timeout(.2):
                    with self.assertRaises(self.mod.ProtocolError):
                        await getattr(client, operation)(*args)
                self.assertTrue(client.closed)

    async def test_external_cancellation_propagates_even_when_close_stalls(self):
        async def stuck():
            await asyncio.Event().wait()
        self.socket.close = stuck
        client = self.mod.TextSession(self.socket)
        client.cleanup_seconds = .01
        self.socket.feed({'type': 'session.ready', 'mode': 'text', 'session_id': 'synthetic'})
        await client.start('synthetic')
        task = asyncio.create_task(client.turn('r1', 'eins'))
        await asyncio.sleep(0)
        task.cancel()
        async with asyncio.timeout(.2):
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(client.closed)
        self.assertFalse(client.lock.locked())

    async def test_cancellation_resistant_close_does_not_hold_caller(self):
        release = asyncio.Event()
        class Resistant(FakeSocket):
            async def close(inner):
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await release.wait()
        client = self.mod.TextSession(Resistant(), handshake_seconds=.01, cleanup_seconds=.01)
        try:
            async with asyncio.timeout(.2):
                with self.assertRaises(self.mod.ProtocolError):
                    await client.start('synthetic')
            self.assertTrue(client.closed)
        finally:
            release.set()
            await asyncio.sleep(0)


if __name__ == '__main__':
    unittest.main()
