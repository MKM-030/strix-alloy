"""Optional answer failure must not become a recurring backend-wait script."""
import asyncio
import unittest
from native_backend import BackendEvent
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


class FailurePresentationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.lane = NativeDuplex(self.call)
        self.turn = (0, 'Eine aktuelle Frage.', 1, 'original', 0)
    async def asyncTearDown(self):
        await self.lane.close()

    async def test_statement_failure_is_neutral_and_preserves_original_fifo(self):
        original = (0, 'Ein Laptop für Mara Testfeld.', 1, 'original-statement', 0)
        self.lane._bootstrap_state = 'pending'
        await self.lane._accept(original)
        self.lane._enqueue_help_fallback(original, reason='controller_busy')
        self.assertEqual([item.text for item in self.lane._outputs],
                         ['Ich kann gerade keine verlässliche Antwort geben.'])
        self.assertEqual(list(self.lane._pending), [original])
        self.assertEqual(list(self.lane._raw), [original[1]])
        self.assertEqual(self.call.dialog.calls, [])

    async def test_repeated_same_failure_snapshot_has_one_truthful_short_message(self):
        self.lane._enqueue_help_fallback(self.turn)
        self.lane._enqueue_help_fallback((0, 'Noch eine Frage.', 2, 'second', 0))
        self.assertEqual(len(self.lane._outputs), 1)
        text = self.lane._outputs[0].text
        self.assertNotIn('warte', text.casefold())
        self.assertNotIn('angekommen', text.casefold())
        self.assertLessEqual(len(text), 120)

    async def test_failure_does_not_overlay_valid_speech_already_started_in_turn(self):
        self.lane._enqueue('Eine gültige dynamische Antwort.', self.turn, kind='local')
        item = self.lane._outputs.popleft()
        await self.lane._synthesize(item, self.call.playback.generation)
        self.lane._enqueue_help_fallback(self.turn)
        self.assertEqual(list(self.lane._outputs), [])

    async def test_genuine_native_question_or_information_takes_priority_over_fallback(self):
        self.call.dialog.business_request_id = 'a'*32
        event = BackendEvent(1, 'a'*32, 'OutputText', 'Eine echte Rückmeldung.', '', self.call.dialog.backend_owner)
        self.lane._admit_backend_event(event, self.turn)
        self.lane._enqueue_help_fallback(self.turn)
        self.assertEqual(list(self.lane._outputs), [])
        self.assertEqual(len(self.lane._backend_outputs), 1)

    async def test_cancelled_unspoken_failure_does_not_suppress_new_turn_feedback(self):
        self.lane._enqueue_help_fallback(self.turn)
        self.lane.interrupt()
        later = (self.call.playback.generation, 'Eine neue Frage.', 2, 'new-input', 0)
        self.lane._enqueue_help_fallback(later)
        self.assertEqual(len(self.lane._outputs), 1)

    async def test_new_native_information_cancels_delayed_fallback_before_first_pcm(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def synthesize(text):
            entered.set()
            await release.wait()
            yield bytes(480)
        self.call.speech.synthesize = synthesize
        self.lane._enqueue_help_fallback(self.turn)
        item = self.lane._outputs.popleft()
        self.lane._begin_speech(item)
        speech = asyncio.create_task(self.lane._synthesize(item, self.call.playback.generation))
        await entered.wait()
        self.call.dialog.business_request_id = 'a'*32
        self.lane._admit_backend_event(BackendEvent(1, 'a'*32, 'OutputText', 'Echte neue Rückmeldung.', '',
                                                   self.call.dialog.backend_owner), self.turn)
        release.set()
        await speech
        self.assertEqual(len(self.call.playback.data), 0)
        self.assertEqual(self.call.events, [])

    async def test_accepted_but_unemitted_failure_is_not_counted_as_heard(self):
        self.lane._enqueue_help_fallback(self.turn)
        item = self.lane._outputs.popleft()
        state = self.lane._begin_speech(item)
        await self.lane._synthesize(item, self.call.playback.generation)
        self.lane._finish_speech(state, complete=True)
        self.assertEqual(state['emitted_samples'], 0)
        self.lane.interrupt()
        self.lane._enqueue_help_fallback((self.call.playback.generation, 'Neue Frage.', 2, 'next', 0))
        self.assertEqual(len(self.lane._outputs), 1)

    async def test_actually_host_emitted_failure_is_deduplicated_on_later_turn(self):
        self.lane._enqueue_help_fallback(self.turn)
        item = self.lane._outputs.popleft()
        state = self.lane._begin_speech(item)
        await self.lane._synthesize(item, self.call.playback.generation)
        self.lane._finish_speech(state, complete=True)
        self.call.playback.read(len(self.call.playback.data))
        self.lane._update_speech_cursor()
        self.lane._enqueue_help_fallback((self.call.playback.generation, 'Neue Frage.', 2, 'next', 0))
        self.assertEqual(list(self.lane._outputs), [])


if __name__ == '__main__':
    unittest.main()
