"""Fixed-code rejection diagnostics; offline evidence, no policy change."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


class RejectionDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def lane(self):
        call = FakeCall()
        lane = NativeDuplex(call)
        identity = SimpleNamespace(server_session_id='offline-session', socket_instance='offline-socket')
        lane.conversation = SimpleNamespace(is_current=lambda candidate: candidate is identity)
        owned = lane.conversation
        async def close():
            owned.closed = True
        owned.close = close
        turn = (0, 'Eine Frage zum Onboarding.', 1, 'offline-request', 0)
        lane._observe_raw(turn[1])
        return call, lane, identity, turn

    async def test_each_existing_admission_guard_reports_only_its_fixed_reason(self):
        cases = (
            ('', 'empty_text'), ('x' * 1201, 'text_too_long'),
            ('Die Bestellung ist bestätigt.', 'completion_confirmed'),
            ('Die Bestellung ist nicht bestätigt.', 'completion_confirmed'),
            ('bestellt', 'completion_ordered'), ('abgeschlossen', 'completion_closed'),
            ('genehmigt', 'completion_approved'), ('freigegeben', 'completion_released'),
            ('erledigt', 'completion_done'), ('analysis', 'internal_control_word'),
            ('<tag>', 'markup'), ('https://example.invalid', 'external_url'),
            ('public-reply-1', 'internal_evidence_id'), ('a' * 32, 'opaque_identifier'),
            ('Das kostet 749 Euro.', 'unbound_number'),
            ('test-call ist eine interne Kennung.', 'identifier_in_text'),
        )
        for text, reason in cases:
            with self.subTest(reason=reason, negative='nicht' in text):
                call, lane, identity, turn = self.lane()
                _, snapshot, observation = lane._dialogue_snapshot(turn, lane.epoch)
                with self.assertLogs('native-voice', level='INFO') as captured:
                    self.assertFalse(lane._admit_conversation(SimpleNamespace(text=text, identity=identity),
                        turn, lane.epoch, observation, snapshot))
                self.assertEqual(len(captured.output), 1)
                self.assertIn('stage=discarded reason=' + reason + ' at=sentence', captured.output[0])
                self.assertEqual(list(lane._outputs), [])
                self.assertNotIn('749', captured.output[0])
                self.assertNotIn('https://', captured.output[0])

    async def test_identity_rejection_has_a_distinct_fixed_reason(self):
        call, lane, identity, turn = self.lane()
        _, snapshot, observation = lane._dialogue_snapshot(turn, lane.epoch)
        with self.assertLogs('native-voice', level='INFO') as captured:
            self.assertFalse(lane._admit_conversation(SimpleNamespace(text='Eine zulässige Antwort.', identity=None),
                turn, lane.epoch, observation, snapshot))
        self.assertIn('reason=identity_not_current at=sentence', captured.output[0])

    async def test_candidate_failures_use_a_closed_reason_map_without_echoing_failure_data(self):
        cases = (
            ('output_callback_failed', 'candidate_callback_failed'),
            ('unavailable', 'candidate_protocol_unavailable'),
            ('busy', 'candidate_busy'), ('invalid_input', 'candidate_invalid_input'),
            ('private-token-marker', 'candidate_failure_unknown'),
        )
        for failure, reason in cases:
            with self.subTest(reason=reason):
                call, lane, identity, turn = self.lane()
                async def respond(*args, **kwargs):
                    return SimpleNamespace(failure=failure, identity=identity, text='')
                lane.conversation.respond = respond
                lane.conversation.sentence_streaming = True
                lane.conversation.output_epoch = lane.epoch
                with self.assertLogs('native-voice', level='INFO') as captured:
                    await lane._general_help(turn, lane.epoch)
                self.assertTrue(any('reason=' + reason + ' at=completion' in line for line in captured.output))
                self.assertNotIn('private-token-marker', '\n'.join(captured.output))
                self.assertEqual(lane._model_failed, failure != 'output_callback_failed')

    async def test_synthetic_second_sentence_rejection_reproduces_partial_speech_and_per_reply_failure(self):
        # The actual discarded sentence was not retained. This demonstrates the
        # existing mechanism only, without asserting what that sentence contained.
        call, lane, identity, turn = self.lane()
        release_audio, first_pcm = asyncio.Event(), asyncio.Event()
        original_transcript = call.transcript
        def transcript(*args):
            original_transcript(*args)
            first_pcm.set()
        call.transcript = transcript
        async def speech(text):
            call.spoken.append(text)
            yield bytes(480)
            await release_audio.wait()
        call.speech.synthesize = speech
        attempts = []
        async def respond(*args, on_sentence):
            attempts.append(args[0])
            await on_sentence(SimpleNamespace(text='Ja, ich höre Sie gut.', identity=identity))
            await asyncio.wait_for(first_pcm.wait(), .5)
            try:
                await on_sentence(SimpleNamespace(text='Die Bestellung ist nicht bestätigt.', identity=identity))
            except ValueError:
                return SimpleNamespace(text='', failure='output_callback_failed', identity=identity)
            raise AssertionError('Existing completion-word guard must still reject the synthetic sentence')
        lane.conversation.respond = respond
        lane.conversation.sentence_streaming = True
        lane.conversation.output_epoch = lane.epoch
        speaker = asyncio.create_task(lane._speak_loop())
        try:
            with self.assertLogs('native-voice', level='INFO') as captured:
                await lane._general_help(turn, lane.epoch)
            self.assertTrue(first_pcm.is_set())
            self.assertEqual(attempts, [turn[1]])
            self.assertFalse(lane._model_failed)
            self.assertIsNone(lane.conversation)
            logs = '\n'.join(captured.output)
            self.assertIn('reason=completion_confirmed at=sentence', logs)
            self.assertIn('reason=candidate_callback_failed at=completion', logs)
            self.assertIn('stage=fallback reason=unavailable', logs)
            self.assertNotIn('Die Bestellung ist nicht bestätigt.', logs)
        finally:
            call.closed = True
            release_audio.set()
            speaker.cancel()
            await asyncio.gather(speaker, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
