"""Pure Bridge control completion and bounded receipt retention checks."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings, Conversation


class BackendReceiptLimitsTests(unittest.TestCase):
    def session(self):
        session = Conversation(user_id='offline')
        session.started = session.busy = True
        session.requests.append('a' * 32)
        return session

    def test_partial_boolean_cannot_be_stamped_complete_or_open_input(self):
        bridge = Bridge(Settings(instance_url='https://fixture.example.test', user_id='offline'), 'offline', 'offline', 'offline')
        for marker in ('streaming', 'streamingStatus'):
            with self.subTest(marker=marker):
                session = self.session()
                bridge.consume(session, dict(requestId='a' * 32, body=[dict(
                    uiType='Boolean', label='Unfinished question?', **{marker:'INPROGRESS'})]))
                self.assertEqual(list(session.backend_events), [])
                self.assertIsNone(session.input_control_receipt)
                self.assertTrue(session.busy)

    def test_per_request_deduplication_remains_bounded_with_receipt_queue(self):
        session = self.session()
        for number in range(300):
            session.emit_backend_once('a' * 32, 'OutputText', f'Observed {number}.')
        self.assertLessEqual(len(session.backend_events), 200)
        self.assertLessEqual(len(session.backend_fingerprints), 256)


if __name__ == '__main__':
    unittest.main()
