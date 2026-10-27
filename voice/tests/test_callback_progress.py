import unittest
from callback_progress import CallbackProgress


def event(request='r1', message='Die Anfrage wird geprüft.', **extra):
    return {'requestId': request, 'streamState': 'INPROGRESS', 'body': [{
        'uiType': 'ActionMsg', 'actionType': 'DynamicLoader',
        'progressMessages': [{'message': message, 'status': 'COMPLETED', **extra}]}]}


class CallbackProgressTests(unittest.TestCase):
    def setUp(self):
        self.progress = CallbackProgress()
        self.progress.begin_request('r1')

    def observe(self, data, now=10):
        return self.progress.observe(data, now=now, clean_text=lambda s:s)

    def test_current_processing_is_visible_during_streaming_without_final_authority(self):
        self.assertTrue(self.observe(event()))
        value = self.progress.snapshot(now=11)
        self.assertEqual(value['messages'], ['Die Anfrage wird geprüft.'])
        self.assertFalse(value['agentCompletionKnown'])

    def test_old_request_and_new_request_do_not_leak_labels(self):
        self.assertFalse(self.observe(event(request='other')))
        self.assertTrue(self.observe(event()))
        self.progress.begin_request('r2')
        self.assertIsNone(self.progress.snapshot(now=11))
        self.assertFalse(self.observe(event()))

    def test_duplicate_and_expired_progress_do_not_repeat(self):
        self.assertTrue(self.observe(event()))
        self.assertFalse(self.observe(event(), now=12))
        self.assertIsNone(self.progress.snapshot(now=41))
        self.assertIsNone(self.progress.snapshot(now=9))

    def test_arbitrary_partial_or_internal_output_is_ignored(self):
        value = event()
        value['body'][0]['actionType'] = 'StreamChunk'
        self.assertFalse(self.observe(value))
        value = event(message={'Thought':'private'})
        self.assertFalse(self.observe(value))
        self.assertFalse(self.observe(event(message='x'*1501)))


if __name__ == '__main__':
    unittest.main()
