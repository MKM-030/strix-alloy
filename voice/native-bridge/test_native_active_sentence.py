"""Already admitted PCM has hard source ownership, separate from queued freshness."""
import asyncio
from types import SimpleNamespace
import unittest

from native_duplex import NativeDuplex
from test_native_duplex import FakeCall

TEXT = 'Wir können die nächsten Angaben gemeinsam klären.'
PREFIX, TAIL = b'\x01\x00' * 240, b'\x02\x00' * 240


class Source:
    output_epoch = 1
    sentence_streaming = True
    def __init__(self):
        self.identity = object()
        self.scope_current = self.alive = True
    def is_current(self, identity):
        return identity is self.identity and self.scope_current and self.alive
    def is_source_current(self, identity):
        return identity is self.identity and self.alive
    async def close(self):
        self.alive = False


class ActiveSentenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call, self.source = FakeCall(), Source()
        self.lane = NativeDuplex(self.call)
        self.lane.conversation = self.source
        self.turn = (0, 'Welche Angaben fehlen?', 1, 'owned-input', 0)
        self.tasks = []
    async def asyncTearDown(self):
        self.call.closed = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.lane.close()

    def item(self):
        self.lane._observe_raw(self.turn[1])
        _, _, observation = self.lane._dialogue_snapshot(self.turn, self.lane.epoch)
        self.lane._enqueue(TEXT, self.turn, kind='conversation', observation=observation,
                           identity=self.source.identity)
        item = self.lane._outputs.popleft()
        self.lane._begin_speech(item)
        return item

    async def test_observation_and_presentation_scope_change_finish_started_sentence(self):
        item = self.item()
        async def synthesize(text):
            yield PREFIX
            self.call.dialog.observation_revision += 1
            self.source.scope_current = False
            yield TAIL
        self.call.speech.synthesize = synthesize
        await self.lane._synthesize(item, self.call.playback.generation)
        self.assertEqual(bytes(self.call.playback.data), PREFIX + TAIL)
        self.assertFalse(self.lane._valid(item), 'Queued freshness must remain strict')

    async def test_pending_fifo_advance_finishes_started_sentence(self):
        self.lane._pending.append(self.turn)
        item = self.item()
        async def synthesize(text):
            yield PREFIX
            self.lane._pending.popleft()
            self.lane._request += 1
            yield TAIL
        self.call.speech.synthesize = synthesize
        await self.lane._synthesize(item, self.call.playback.generation)
        self.assertEqual(bytes(self.call.playback.data), PREFIX + TAIL)

    async def test_hard_source_change_still_stops_tail(self):
        item = self.item()
        async def synthesize(text):
            yield PREFIX
            self.source.alive = False
            yield TAIL
        self.call.speech.synthesize = synthesize
        await self.lane._synthesize(item, self.call.playback.generation)
        self.assertEqual(bytes(self.call.playback.data), PREFIX)

    async def test_stale_scope_before_first_pcm_never_receives_a_lease(self):
        item = self.item()
        async def synthesize(text):
            self.call.dialog.observation_revision += 1
            self.source.scope_current = False
            yield PREFIX
        self.call.speech.synthesize = synthesize
        await self.lane._synthesize(item, self.call.playback.generation)
        self.assertEqual(bytes(self.call.playback.data), b'')
        self.assertIsNone(self.lane._speech['lease'])

    async def test_soft_completion_revocation_does_not_cut_first_pcm_sentence(self):
        first_pcm, release = asyncio.Event(), asyncio.Event()
        async def synthesize(text):
            self.call.spoken.append(text)
            yield PREFIX
            first_pcm.set()
            await release.wait()
            yield TAIL
        self.call.speech.synthesize = synthesize
        async def respond(raw, snapshot, key, *, on_sentence):
            await on_sentence(SimpleNamespace(text=TEXT, identity=self.source.identity))
            await first_pcm.wait()
            self.call.dialog.observation_revision += 1
            self.source.scope_current = False
            return SimpleNamespace(text=TEXT, identity=self.source.identity, failure=None)
        self.source.respond = respond
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        self.lane._observe_raw(self.turn[1])
        await self.lane._general_help(self.turn, self.lane.epoch)
        release.set()
        await asyncio.sleep(.02)
        self.assertEqual(bytes(self.call.playback.data), PREFIX + TAIL)
        self.assertEqual(self.call.spoken, [TEXT])

    async def test_hard_source_close_flushes_pcm_even_after_synthesis_finished(self):
        self.item()
        # Requeue under the same genuine model identity for the real speaker.
        self.lane._enqueue(TEXT, self.turn, kind='conversation', observation=0, identity=self.source.identity)
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        async with asyncio.timeout(1):
            while not self.call.spoken or self.call.synthesis_active:
                await asyncio.sleep(.002)
        self.assertGreater(len(self.call.playback.data), 0)
        self.source.alive = False
        self.lane._update_speech_cursor()
        self.assertEqual(len(self.call.playback.data), 0)
        self.assertTrue(self.lane._speech['interrupted'])


if __name__ == '__main__':
    unittest.main()
