"""Optional answer failure must not become a recurring backend-wait script."""
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


if __name__ == '__main__':
    unittest.main()
