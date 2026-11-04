"""A rejected optional reply may not disable every later caller turn."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


class Conversation:
    sentence_streaming = True
    output_epoch = 1

    def __init__(self, failure=None, close_error=False):
        self.failure, self.close_error = failure, close_error
        self.inputs, self.close_count = [], 0
        self.close_gate = None
        self.identity = SimpleNamespace(server_session_id='owned-offline-session')

    async def invalidate(self, epoch, reason):
        self.output_epoch = epoch

    async def respond(self, raw, snapshot, key, *, on_sentence):
        self.inputs.append(raw)
        if self.failure == 'output_callback_failed':
            try:
                await on_sentence(SimpleNamespace(text='Die Bestellung ist nicht bestätigt.', identity=self.identity))
            except ValueError:
                return SimpleNamespace(text='', failure=self.failure, identity=self.identity)
            raise AssertionError('The existing completion claim guard must remain active')
        if self.failure is None:
            await on_sentence(SimpleNamespace(text='Wir können die Angaben gemeinsam klären.', identity=self.identity))
        return SimpleNamespace(text='', failure=self.failure, identity=self.identity)

    def is_current(self, identity):
        return identity is self.identity

    async def close(self):
        self.close_count += 1
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.close_error:
            raise RuntimeError('Synthetic close failure')


class ReplyRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.first = Conversation('output_callback_failed')
        self.second = Conversation()
        self.factories = []
        async def factory(url, call_id, epoch):
            model = (self.first, self.second)[len(self.factories)]
            self.factories.append(model)
            model.output_epoch = epoch
            return model
        self.lane = NativeDuplex(self.call, conversation_factory=factory)
        gate = asyncio.Event()
        async def opening():
            await gate.wait()
            return []
        self.opening = asyncio.create_task(opening())
        self.running = asyncio.create_task(self.lane.run(bootstrap_task=self.opening))

    async def asyncTearDown(self):
        self.call.closed = True
        self.running.cancel()
        self.opening.cancel()
        await asyncio.gather(self.running, self.opening, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(.5):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.002)

    async def first_reply(self):
        self.call.feed('Welche Unterstützung bieten Sie?', 1)
        await self.until(lambda: bool(self.first.inputs))
        await self.until(lambda: not self.lane._local_busy)

    async def test_rejected_reply_closes_only_its_owned_session_and_new_input_attempts_once(self):
        await self.first_reply()
        self.assertFalse(self.lane._model_failed)
        self.assertIsNone(self.lane.conversation)
        self.assertEqual(self.first.close_count, 1)
        self.assertEqual(len(self.factories), 1, 'The rejected original must not be retried')
        self.call.feed('Welche Angabe fehlt noch?', 2)
        await self.until(lambda: 'Wir können die Angaben gemeinsam klären.' in self.call.spoken)
        self.assertEqual(len(self.factories), 2)
        self.assertEqual(self.first.inputs, ['Welche Unterstützung bieten Sie?'])
        self.assertEqual(self.second.inputs, ['Welche Angabe fehlt noch?'])
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual([turn[1] for turn in self.lane._pending],
                         self.first.inputs + self.second.inputs)

    async def test_terminal_protocol_failure_remains_separate_and_is_not_retried(self):
        self.first.failure = 'unavailable'
        await self.first_reply()
        self.assertTrue(self.lane._model_failed)
        self.call.feed('Welche Angabe fehlt noch?', 2)
        await self.until(lambda: self.lane.pending_count == 2 and not self.lane._local_busy)
        self.assertEqual(len(self.factories), 1)
        self.assertEqual(self.second.inputs, [])

    async def test_new_input_during_owned_close_cannot_receive_the_old_turn_fallback(self):
        self.first.close_gate = asyncio.Event()
        transcripts = []
        def transcript(turn, role, text, *, started_at=None):
            transcripts.append((turn[3], role, text))
        self.call.transcript = transcript
        self.call.feed('Welche Unterstützung bieten Sie?', 1)
        await self.until(lambda: self.first.close_count == 1)
        self.call.feed('Welche Angabe fehlt noch?', 2)
        await self.until(lambda: self.lane.pending_count == 2)
        self.first.close_gate.set()
        await self.until(lambda: bool(self.second.inputs))
        await self.until(lambda: not self.lane._local_busy and not self.lane.output_pending
                         and not self.call.synthesis_active and any(turn == '2' for turn, _, _ in transcripts))
        self.assertTrue(any(turn == '2' for turn, _, _ in transcripts))
        self.assertFalse(any(turn == '1' for turn, _, _ in transcripts),
                         'Old fallback must not be rebound to a new caller epoch during close')

    async def test_failed_owned_close_cannot_silently_reuse_the_rejected_session(self):
        self.first.close_error = True
        await self.first_reply()
        self.assertIsNone(self.lane.conversation)
        self.assertTrue(self.lane._model_failed)
        self.assertEqual(self.first.close_count, 1)
        self.assertEqual(len(self.factories), 1)


if __name__ == '__main__':
    unittest.main()
