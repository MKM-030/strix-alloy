"""Text grouping preserves actual completed speech without buffering audio."""
import unittest

try:
    from transcript_groups import TranscriptGroups
except ModuleNotFoundError:
    TranscriptGroups = None


class TranscriptGroupingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(TranscriptGroups, 'Completed local speech has no transcript group ledger')
        self.ledger = TranscriptGroups()
        self.owner, self.turn = object(), object()
        self.key = self.ledger.open(self.owner, self.turn)
        self.first, self.second = object(), object()

    def admit(self, part, text):
        return self.ledger.admit(self.key, self.owner, self.turn, part, text)

    def spoken(self, part, text, at):
        self.assertTrue(self.admit(part, text))
        self.assertTrue(self.ledger.started(self.key, self.owner, part, at))
        self.assertTrue(self.ledger.emitted(self.key, self.owner, part))

    def test_two_completed_sentences_publish_once_after_eos_with_original_first_pcm_time(self):
        self.spoken(self.first, 'Ich höre Sie gut.', 10.1)
        self.spoken(self.second, 'Welche Angaben möchten Sie ergänzen?', 11.8)
        self.assertEqual(self.ledger.take_ready(), [])
        self.ledger.finish(self.key, self.owner)
        result, = self.ledger.take_ready()
        self.assertEqual(result.text, 'Ich höre Sie gut. Welche Angaben möchten Sie ergänzen?')
        self.assertIs(result.turn, self.turn)
        self.assertIs(result.owner, self.owner)
        self.assertEqual(result.first_pcm_at, 10.1)
        self.assertEqual(result.reason, 'complete')
        self.assertEqual(self.ledger.take_ready(), [])
        self.ledger.finish(self.key, self.owner)
        self.assertFalse(self.admit(object(), 'A late duplicate.'))
        self.assertEqual(self.ledger.take_ready(), [])

    def test_eos_waits_for_complete_host_emission_not_synthesis_start(self):
        self.admit(self.first, 'Ein vollständiger Satz.')
        self.ledger.started(self.key, self.owner, self.first, 10.1)
        self.ledger.finish(self.key, self.owner)
        self.assertEqual(self.ledger.take_ready(), [])
        self.ledger.emitted(self.key, self.owner, self.first)
        self.assertEqual([x.text for x in self.ledger.take_ready()], ['Ein vollständiger Satz.'])

    def test_interrupted_first_sentence_publishes_no_inferred_word_prefix(self):
        self.admit(self.first, 'Meine Angaben warten noch auf die Rückmeldung des Systems.')
        self.ledger.started(self.key, self.owner, self.first, 10.1)
        self.ledger.interrupt(self.key, self.owner, 'caller_interruption')
        self.ledger.finish(self.key, self.owner)
        self.assertEqual(self.ledger.take_ready(), [])
        self.assertFalse(self.ledger.emitted(self.key, self.owner, self.first))

    def test_interrupted_second_sentence_keeps_only_the_completed_prefix(self):
        self.spoken(self.first, 'Ich höre Sie gut.', 10.1)
        self.admit(self.second, 'Bitte nennen Sie alle weiteren Angaben.')
        self.ledger.started(self.key, self.owner, self.second, 11.8)
        self.ledger.interrupt(self.key, self.owner, 'caller_interruption')
        result, = self.ledger.take_ready()
        self.assertEqual(result.text, 'Ich höre Sie gut.')
        self.assertEqual(result.reason, 'caller_interruption')

    def test_retired_queued_tail_waits_for_active_sentence_to_finish(self):
        self.assertTrue(callable(getattr(self.ledger, 'retire', None)),
                        'A dropped queued part must not prevent completed-prefix publication')
        self.admit(self.first, 'Der begonnene Satz läuft weiter.')
        self.ledger.started(self.key, self.owner, self.first, 10.1)
        self.admit(self.second, 'Die überholte nächste Frage?')
        self.assertTrue(self.ledger.retire(self.key, self.owner, self.second))
        self.ledger.finish(self.key, self.owner)
        self.assertEqual(self.ledger.take_ready(), [])
        self.assertFalse(self.ledger.started(self.key, self.owner, self.second, 11.8))
        self.ledger.emitted(self.key, self.owner, self.first)
        result, = self.ledger.take_ready()
        self.assertEqual(result.text, 'Der begonnene Satz läuft weiter.')
        self.assertEqual(result.reason, 'partial_response')

    def test_queue_replacement_retires_only_unstarted_parts_missing_from_live_outputs(self):
        self.assertTrue(callable(getattr(self.ledger, 'retain_pending', None)),
                        'Queue replacement must retire unspoken transcript parts without touching active speech')
        self.admit(self.first, 'Ein weiterhin aktiver Satz.')
        self.ledger.started(self.key, self.owner, self.first, 10.1)
        self.admit(self.second, 'Eine verworfene spätere Frage?')
        self.ledger.finish(self.key, self.owner)
        self.ledger.retain_pending({self.first})
        self.assertEqual(self.ledger.take_ready(), [])
        self.ledger.emitted(self.key, self.owner, self.first)
        self.assertEqual([x.text for x in self.ledger.take_ready()], ['Ein weiterhin aktiver Satz.'])
        self.assertFalse(self.ledger.started(self.key, self.owner, self.second, 11.8))

    def test_native_boundary_flushes_completed_local_prefix_before_native_text(self):
        self.spoken(self.first, 'Wir können die Angaben gemeinsam klären.', 10.1)
        self.admit(self.second, 'Eine überholte zusätzliche Frage?')
        self.ledger.before_native()
        local, = self.ledger.take_ready()
        events = [local.text, 'Echte ServiceNow-Rückfrage.']
        self.assertEqual(events, ['Wir können die Angaben gemeinsam klären.', 'Echte ServiceNow-Rückfrage.'])
        self.assertFalse(self.ledger.started(self.key, self.owner, self.second, 12.0))
        self.assertEqual(self.ledger.take_ready(), [])

    def test_wrong_source_owner_or_original_turn_cannot_change_the_group(self):
        self.admit(self.first, 'Ein zulässiger Satz.')
        self.assertFalse(self.ledger.admit(self.key, object(), self.turn, self.second, 'Fremder Satz.'))
        self.assertFalse(self.ledger.admit(self.key, self.owner, object(), self.second, 'Falscher Beitrag.'))
        self.assertFalse(self.ledger.started(self.key, object(), self.first, 10.1))
        self.assertFalse(self.ledger.emitted(self.key, self.owner, self.first))
        self.assertFalse(self.ledger.finish(self.key, object()))
        self.ledger.interrupt(self.key, self.owner, 'source_replaced')
        self.assertEqual(self.ledger.take_ready(), [])

    def test_close_retains_completed_text_and_retires_queued_unspoken_parts(self):
        self.spoken(self.first, 'Ein bereits gesprochener Satz.', 10.1)
        self.admit(self.second, 'Ein nie gesprochener Satz.')
        self.ledger.close()
        result, = self.ledger.take_ready()
        self.assertEqual(result.text, 'Ein bereits gesprochener Satz.')
        self.assertEqual(result.reason, 'call_closed')
        self.assertIsNone(self.ledger.open(object(), object()))
        self.assertFalse(self.ledger.admit(object(), object(), object(), object(), 'Zu spät.'))

    def test_overflow_is_explicit_and_never_fabricates_a_full_transcript(self):
        ledger = TranscriptGroups(max_parts=1, max_chars=30, max_bytes=60, max_groups=1)
        key = ledger.open(self.owner, self.turn)
        self.assertTrue(ledger.admit(key, self.owner, self.turn, self.first, 'Ein kurzer Satz.'))
        ledger.started(key, self.owner, self.first, 10.1)
        ledger.emitted(key, self.owner, self.first)
        with self.assertRaisesRegex(ValueError, 'transcript_group_overflow'):
            ledger.admit(key, self.owner, self.turn, self.second, 'Ein weiterer Satz.')
        prefix, = ledger.take_ready()
        self.assertEqual(prefix.text, 'Ein kurzer Satz.')
        self.assertEqual(prefix.reason, 'transcript_group_overflow')
        self.assertFalse(ledger.emitted(key, self.owner, self.second))
        for text in ('x' * 31, 'ä' * 31):
            bounded = TranscriptGroups(max_chars=30, max_bytes=60)
            key = bounded.open(self.owner, self.turn)
            with self.assertRaisesRegex(ValueError, 'transcript_group_overflow'):
                bounded.admit(key, self.owner, self.turn, object(), text)
            self.assertEqual(bounded.take_ready(), [])

    def test_utf8_size_and_simultaneous_response_limits_are_enforced(self):
        byte_bounded = TranscriptGroups(max_chars=100, max_bytes=30)
        key = byte_bounded.open(self.owner, self.turn)
        with self.assertRaisesRegex(ValueError, 'transcript_group_overflow'):
            byte_bounded.admit(key, self.owner, self.turn, self.first, 'ä' * 16)
        self.assertEqual(byte_bounded.take_ready(), [])
        group_bounded = TranscriptGroups(max_groups=1)
        key = group_bounded.open(self.owner, self.turn)
        group_bounded.admit(key, self.owner, self.turn, self.first, 'Ein gültiger Satz.')
        with self.assertRaisesRegex(ValueError, 'transcript_group_overflow'):
            group_bounded.open(self.owner, self.turn)
        group_bounded.started(key, self.owner, self.first, 10.1)
        group_bounded.emitted(key, self.owner, self.first)
        group_bounded.finish(key, self.owner)
        self.assertEqual([x.text for x in group_bounded.take_ready()], ['Ein gültiger Satz.'])

    def test_duplicate_parts_or_invalid_first_pcm_cannot_claim_completion(self):
        self.assertTrue(self.admit(self.first, 'Ein zulässiger Satz.'))
        self.assertFalse(self.admit(self.first, 'Ein anderer Satz.'))
        for at in (float('nan'), float('inf'), -1, True, '10'):
            self.assertFalse(self.ledger.started(self.key, self.owner, self.first, at))
        self.assertFalse(self.ledger.emitted(self.key, self.owner, self.first))
        self.ledger.finish(self.key, self.owner)
        self.assertEqual(self.ledger.take_ready(), [])

    def test_a_retired_response_cannot_reopen_after_257_later_responses(self):
        old_key = None
        old_part = None
        for index in range(258):
            key, part = self.ledger.open(self.owner, self.turn), object()
            if index == 0:
                old_key, old_part = key, part
            self.ledger.admit(key, self.owner, self.turn, part, 'Ein gesprochener Satz.')
            self.ledger.started(key, self.owner, part, 10.0 + index)
            self.ledger.emitted(key, self.owner, part)
            self.ledger.finish(key, self.owner)
            self.assertEqual(len(self.ledger.take_ready()), 1)
        self.assertFalse(self.ledger.admit(old_key, self.owner, self.turn, old_part,
                                          'Ein gesprochener Satz.'),
                         'Retired response keys must never silently reopen after a bounded window')


if __name__ == '__main__':
    unittest.main()
