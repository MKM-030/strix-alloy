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

    def test_known_english_generic_advisory_uses_existing_german_generic(self):
        self.assertTrue(self.observe(event(message='Checking on remaining steps.')))
        value = self.progress.snapshot(now=11)
        self.assertEqual(value['messages'], ['Die Anfrage wird geprüft.'])
        self.assertEqual(value['source'], 'servicenow_processing')
        self.assertFalse(value['agentCompletionKnown'])

    def test_known_generic_case_space_and_single_terminal_punctuation_variants(self):
        for label in ('Checking on remaining steps', 'CHECKING ON REMAINING STEPS!',
                      '  Checking\t on  remaining steps ?  '):
            with self.subTest(label=label):
                self.progress.begin_request('r1')
                self.assertTrue(self.observe(event(message=label)))
                self.assertEqual(self.progress.snapshot(now=11)['messages'],
                                 ['Die Anfrage wird geprüft.'])

    def test_known_generic_replaces_previous_specific_advisory_and_dedupes(self):
        self.assertTrue(self.observe(event(message='Verfügbarkeit wird geprüft.'), now=10))
        self.assertTrue(self.observe(event(message='Checking on remaining steps.'), now=12))
        value = self.progress.snapshot(now=13)
        self.assertEqual(value['messages'], ['Die Anfrage wird geprüft.'])
        self.assertEqual(value['revision'], 2)
        self.assertEqual(value['ageSeconds'], 1)
        self.assertFalse(self.observe(event(message='CHECKING ON REMAINING STEPS'), now=14))
        self.assertEqual(self.progress.snapshot(now=15)['revision'], 2)
        self.assertIsNone(self.progress.snapshot(now=43))
        self.progress.begin_request('r2')
        self.assertIsNone(self.progress.snapshot(now=15))

    def test_projection_dedupes_equivalent_labels_within_current_snapshot(self):
        value = event(message='Checking on remaining steps.')
        value['body'][0]['progressMessages'] += [
            {'message': 'Die Anfrage wird geprüft.'},
            {'message': 'Checking on remaining steps'},
            {'message': 'Verfügbarkeit wird geprüft.'}]
        self.assertTrue(self.observe(value))
        self.assertEqual(self.progress.snapshot(now=11)['messages'],
                         ['Die Anfrage wird geprüft.', 'Verfügbarkeit wird geprüft.'])

    def test_other_concrete_or_near_match_labels_are_preserved(self):
        for label in ('Verfügbarkeit wird geprüft.', 'Checking laptop availability.',
                      'Checking on remaining steps for Berlin.',
                      'Not checking on remaining steps.', 'Checking. on remaining steps.',
                      'Checking on remaining steps..'):
            with self.subTest(label=label):
                self.progress.begin_request('r1')
                self.assertTrue(self.observe(event(message=label)))
                self.assertEqual(self.progress.snapshot(now=11)['messages'], [label])


if __name__ == '__main__':
    unittest.main()
