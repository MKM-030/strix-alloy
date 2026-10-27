"""Offline regression for callback ownership of an already speaking reply."""
import asyncio
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


class CallbackOutputOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def check_callback(self, reply, *, stale=False, pending=0, replaces=False):
        call = FakeCall()
        lane = NativeDuplex(call)
        local_text = 'Wir können die Schreibweise gemeinsam klären.'
        local_started = asyncio.Event()
        local_release = asyncio.Event()
        prefix = b'\x01\x00' * 240

        async def synthesize(text):
            call.spoken.append(text)
            if text == local_text:
                local_started.set()
                yield prefix
                await local_release.wait()
            else:
                yield bytes(480)

        call.speech.synthesize = synthesize
        turn = (0, 'Bitte die Angaben prüfen.', 1, 'business-1', time.monotonic())
        business = asyncio.create_task(lane._business(turn))
        speaker = None
        try:
            await asyncio.wait_for(call.dialog.started.get(), 1)
            if stale:
                lane.task_revision += 1
            for number in range(pending):
                lane._pending.append((0, 'Neue Caller-Ergänzung.', number + 2,
                                      str(number + 2), time.monotonic()))
            # The local reply belongs to the newest caller state, while the
            # already submitted business request keeps its original revision.
            lane._enqueue(local_text, kind='conversation')
            speaker = asyncio.create_task(lane._speak_loop())
            await asyncio.wait_for(local_started.wait(), 1)
            local_task = lane._synthesis_task
            self.assertEqual(bytes(call.playback.data), prefix)

            call.dialog.release.put_nowait(reply)
            await asyncio.wait_for(business, 1)
            await asyncio.sleep(0)

            if replaces:
                async with asyncio.timeout(1):
                    while reply not in call.spoken:
                        await asyncio.sleep(0)
                self.assertTrue(local_task.cancelled())
                self.assertEqual(call.spoken, [local_text, reply])
                self.assertNotEqual(bytes(call.playback.data), prefix)
                self.assertEqual([event for event in call.events if event[0] == 'assistant'],
                                 [('assistant', reply)])
            else:
                self.assertFalse(local_task.done(),
                                 'A callback without an admitted replacement cancelled current speech')
                self.assertEqual(bytes(call.playback.data), prefix)
                self.assertEqual(call.spoken, [local_text])
                self.assertFalse(lane.output_pending)
                self.assertEqual([event for event in call.events if event[0] == 'assistant'], [])
        finally:
            call.closed = True
            local_release.set()
            for task in (business, speaker):
                if task is not None:
                    task.cancel()
            await asyncio.gather(*(task for task in (business, speaker) if task is not None),
                                 return_exceptions=True)
            await lane.close()

    async def test_stale_error_with_four_pending_inputs_keeps_current_speech(self):
        await self.check_callback('Zurzeit sind keine Service-Desk-Mitarbeiter verfügbar.',
                                  stale=True, pending=4)

    async def test_stale_reply_without_pending_inputs_keeps_current_speech(self):
        await self.check_callback('Bitte wählen Sie ein Gerät.', stale=True)

    async def test_pending_inputs_fence_reply_without_cancelling_current_speech(self):
        await self.check_callback('Bitte wählen Sie ein Gerät.', pending=1)

    async def test_suppressed_generic_processing_keeps_current_speech(self):
        await self.check_callback('Bitte warten Sie einen Moment.')

    async def test_empty_callback_keeps_current_speech(self):
        await self.check_callback('')

    async def test_current_concrete_reply_replaces_local_speech(self):
        await self.check_callback('Bitte wählen Sie ein Gerät.', replaces=True)

    async def test_current_error_reply_replaces_local_speech(self):
        await self.check_callback('Zurzeit sind keine Service-Desk-Mitarbeiter verfügbar.',
                                  replaces=True)


if __name__ == '__main__':
    unittest.main()
