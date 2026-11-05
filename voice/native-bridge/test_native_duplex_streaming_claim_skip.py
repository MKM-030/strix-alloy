"""CPU-only safe-prefix drain after a later unsupported streamed claim.

The actual rejected continuation was not retained. These synthetic sentences
reproduce its observed guard/callback/lease mechanism, not its wording.
"""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall

FIRST = 'Ja, ich bin da.'
UNSUPPORTED = 'Der Laptop ist bestellt.'


class StreamingClaimSkipTests(unittest.IsolatedAsyncioTestCase):
    def lane(self):
        call = FakeCall()
        call.dialog.native_owner_id = 'a' * 32
        publisher = AsyncMock(return_value=True)
        lane = NativeDuplex(call, presentation_publisher=publisher)
        identity = SimpleNamespace(server_session_id='offline-session', socket_instance='offline-socket')
        conversation = SimpleNamespace(closed=False, sentence_streaming=True, output_epoch=lane.epoch)
        conversation.is_current = lambda candidate: candidate is identity and not conversation.closed
        conversation.is_source_current = conversation.is_current
        async def close():
            conversation.closed = True
        conversation.close = close
        lane.conversation = conversation
        turn = (0, 'Eine allgemeine Frage.', 1, 'b' * 32, 0)
        lane._observe_raw(turn[1])
        return call, lane, conversation, identity, turn, publisher

    async def test_later_unsupported_completion_preserves_started_safe_pcm_transcript_and_history_once(self):
        call, lane, conversation, identity, turn, publisher = self.lane()
        finished = asyncio.Event()
        original_finish = lane._finish_speech
        def finish(state, *, complete):
            original_finish(state, complete=complete)
            if state['kind'] == 'conversation':
                finished.set()
        lane._finish_speech = finish
        async def synthesize(text):
            call.spoken.append(text)
            yield b'\1\0' * 42240  # Actual Q1 queued-byte count, synthetic PCM only.
        call.speech.synthesize = synthesize
        partial = {}
        async def respond(text, snapshot, key, *, on_sentence):
            await on_sentence(SimpleNamespace(text=FIRST, identity=identity))
            await asyncio.wait_for(finished.wait(), .5)
            self.assertTrue(lane._speech['complete'])
            self.assertEqual(call.playback.accepted_samples, 42240)
            call.playback.read(9600)
            lane._update_speech_cursor()
            partial['emitted'] = call.playback.emitted_samples
            self.assertGreater(len(call.playback.data), 0)
            try:
                await on_sentence(SimpleNamespace(text=UNSUPPORTED, identity=identity))
            except ValueError:
                return SimpleNamespace(text='', identity=identity, failure='output_callback_failed')
            return SimpleNamespace(text=FIRST + ' ' + UNSUPPORTED, identity=identity, failure=None)
        conversation.respond = respond
        speaker = asyncio.create_task(lane._speak_loop())
        history = asyncio.create_task(lane._presentation_outbox.run(publisher))
        try:
            with self.assertLogs('native-voice', level='INFO') as captured:
                await lane._general_help(turn, lane.epoch)
                lane._update_speech_cursor()
                while call.playback.data:
                    call.playback.read(960)
                    lane._update_speech_cursor()
                await asyncio.wait_for(lane._presentation_outbox._queue.join(), .5)
            self.assertEqual(partial['emitted'], 4800)
            self.assertEqual(call.playback.emitted_samples, 42240)
            self.assertFalse(lane._speech['interrupted'])
            self.assertFalse(conversation.closed)
            self.assertIs(lane.conversation, conversation)
            self.assertFalse(lane._model_failed)
            self.assertEqual(call.spoken, [FIRST])
            publisher.assert_awaited_once()
            event = publisher.await_args.args[0]
            self.assertEqual(event['text'], FIRST)
            self.assertEqual((event['accepted_samples'], event['emitted_samples']), (42240, 42240))
            self.assertEqual(event['sequence'], 1)
            self.assertEqual([event[1] for event in call.events if event[0] == 'assistant'], [FIRST])
            logs = '\n'.join(captured.output)
            self.assertIn('reason=completion_ordered at=sentence', logs)
            self.assertNotIn('reason=candidate_callback_failed', logs)
            self.assertNotIn('stage=hard_lease_revoked', logs)
        finally:
            call.closed = True
            speaker.cancel()
            history.cancel()
            await asyncio.gather(speaker, history, return_exceptions=True)
            await lane.close()

    async def test_only_pure_unsupported_completion_is_skipped_and_nonstreaming_stays_rejected(self):
        for word in ('bestellt', 'abgeschlossen', 'genehmigt', 'freigegeben', 'erledigt', 'bestätigt'):
            with self.subTest(word=word):
                call, lane, _, identity, turn, publisher = self.lane()
                _, snapshot, observation = lane._dialogue_snapshot(turn, lane.epoch)
                candidate = SimpleNamespace(text='Der Vorgang ist ' + word + '.', identity=identity)
                self.assertEqual(lane._release_conversation_sentence(candidate, turn, lane.epoch, observation,
                    snapshot, skip_unsupported_claim=True), 'skipped_claim')
                self.assertFalse(lane._admit_conversation(candidate, turn, lane.epoch, observation, snapshot))
                self.assertEqual(list(lane._outputs), [])
                publisher.assert_not_called()

    async def test_completion_cannot_mask_later_hard_content_or_stale_identity(self):
        cases = ['Der Vorgang ist bestellt. https://example.invalid',
            'Der Vorgang ist bestellt. <tag>', 'Der Vorgang ist bestellt. ' + 'c' * 32,
            'Der Vorgang ist bestellt. Das kostet 749 Euro.',
            'Der Vorgang ist bestellt. test-call', 'Der Vorgang ist bestellt. analysis']
        for text in cases:
            with self.subTest(text=text):
                _, lane, _, identity, turn, _ = self.lane()
                _, snapshot, observation = lane._dialogue_snapshot(turn, lane.epoch)
                self.assertEqual(lane._release_conversation_sentence(SimpleNamespace(text=text, identity=identity),
                    turn, lane.epoch, observation, snapshot, skip_unsupported_claim=True), 'rejected')
                self.assertEqual(list(lane._outputs), [])
        _, lane, _, _, turn, _ = self.lane()
        _, snapshot, observation = lane._dialogue_snapshot(turn, lane.epoch)
        self.assertEqual(lane._release_conversation_sentence(SimpleNamespace(text=UNSUPPORTED, identity=None),
            turn, lane.epoch, observation, snapshot, skip_unsupported_claim=True), 'rejected')

    async def test_changed_context_epoch_or_active_native_control_never_becomes_a_skip(self):
        for change in ('context', 'epoch', 'control'):
            with self.subTest(change=change):
                call, lane, _, identity, turn, _ = self.lane()
                _, snapshot, observation = lane._dialogue_snapshot(turn, lane.epoch)
                epoch = lane.epoch
                if change == 'context':
                    call.dialog.observation_revision += 1
                    lane.task_revision += 1  # A substantive scope change, not display-only churn.
                elif change == 'epoch':
                    lane.epoch += 1
                else:
                    lane._control_gate.binding = object()
                self.assertEqual(lane._release_conversation_sentence(SimpleNamespace(text=UNSUPPORTED, identity=identity),
                    turn, epoch, observation, snapshot, skip_unsupported_claim=True), 'rejected')


if __name__ == '__main__':
    unittest.main()
