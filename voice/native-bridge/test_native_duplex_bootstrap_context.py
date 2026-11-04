"""Offline bootstrap context races: actual observation updates, fake model/media."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_bridge import Dialog
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


FIRST = 'Ich kann Sie bei der Vorbereitung unterstützen.'
SECOND = 'Wir können die nächsten Angaben gemeinsam klären.'


class HeldConversation:
    sentence_streaming = True
    output_epoch = 1

    def __init__(self):
        self.started, self.release, self.first_sent, self.second_release = (asyncio.Event() for _ in range(4))
        self.identity = SimpleNamespace(server_session_id='offline-session')
        self.inputs, self.two_sentences = [], False

    async def invalidate(self, epoch, reason):
        self.output_epoch = epoch

    async def respond(self, raw, snapshot, key, *, on_sentence):
        self.inputs.append((raw, snapshot, key))
        self.started.set()
        await self.release.wait()
        try:
            await on_sentence(SimpleNamespace(text=FIRST, identity=self.identity))
            self.first_sent.set()
            if self.two_sentences:
                await self.second_release.wait()
                await on_sentence(SimpleNamespace(text=SECOND, identity=self.identity))
        except ValueError:
            # Match the real Pipecat sentence sink's callback-failure contract.
            return SimpleNamespace(text='', failure='output_callback_failed', identity=self.identity)
        return SimpleNamespace(text=FIRST, failure=None, identity=self.identity)

    def is_current(self, identity):
        return identity is self.identity

    async def close(self):
        pass


class BootstrapContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call, self.model = FakeCall(), HeldConversation()
        self.call.dialog.conversation_ended = False
        async def factory(*args):
            self.model.output_epoch = args[-1]
            return self.model
        self.lane = NativeDuplex(self.call, conversation_factory=factory)
        self.bootstrap_release = asyncio.Event()
        async def opening():
            await self.bootstrap_release.wait()
            return []
        self.opening = asyncio.create_task(opening())
        self.running = asyncio.create_task(self.lane.run(bootstrap_task=self.opening))

    async def asyncTearDown(self):
        self.call.closed = True
        self.running.cancel()
        self.opening.cancel()
        await asyncio.gather(self.running, self.opening, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(.5):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.002)

    async def start_local(self):
        self.call.feed('Welche Unterstützung bieten Sie hier?')
        await asyncio.wait_for(self.model.started.wait(), .5)

    def progress(self, revision=1):
        Dialog.observe_state(self.call.dialog, dict(processing=dict(
            source='servicenow_processing', agentCompletionKnown=False,
            revision=revision, messages=['Vorbereitung läuft.'], ageSeconds=0)))

    async def finish_model(self):
        self.model.release.set()
        await self.until(lambda: not self.lane._local_busy)

    async def test_loader_update_while_candidate_pending_still_reaches_tts_without_business_dispatch(self):
        await self.start_local()
        before = self.call.dialog.observation_revision
        self.progress()
        self.assertGreater(self.call.dialog.observation_revision, before)
        await self.finish_model()
        await self.until(lambda: FIRST in self.call.spoken)
        self.assertEqual(len(self.model.inputs), 1)
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual([turn[1] for turn in self.lane._pending], [self.model.inputs[0][0]])
        self.assertFalse(any(fact['source_event'] == 'servicenow_processing_presentation'
                             for fact in self.model.inputs[0][1]['public_findings']))

    async def test_loader_update_after_queueing_still_reaches_tts(self):
        await self.start_local()
        self.call.vad_active = True
        await self.finish_model()
        self.assertTrue(self.lane._outputs)
        self.progress()
        self.call.vad_active = False
        await self.until(lambda: FIRST in self.call.spoken)

    async def test_loader_update_between_pcm_chunks_keeps_the_bound_speech(self):
        second_chunk = asyncio.Event()
        async def speech(text):
            self.call.spoken.append(text)
            yield bytes(480)
            await second_chunk.wait()
            yield bytes(480)
        self.call.speech.synthesize = speech
        await self.start_local()
        self.model.release.set()
        await self.until(lambda: self.call.playback.accepted_samples == 240)
        self.progress()
        second_chunk.set()
        await self.until(lambda: not self.call.synthesis_active)
        self.assertEqual(self.call.playback.accepted_samples, 480)
        self.assertTrue(self.lane._speech['complete'])

    async def reject_change(self, mutate):
        await self.start_local()
        mutate()
        await self.finish_model()
        await self.until(lambda: not self.lane.output_pending and not self.call.synthesis_active)
        self.assertNotIn(FIRST, self.call.spoken)
        self.assertFalse(self.lane._outputs)
        self.assertEqual(len(self.model.inputs), 1)

    async def test_new_public_reply_rejects_pending_candidate(self):
        await self.reject_change(lambda: Dialog.record_public_reply(self.call.dialog, 'Neue fachliche Rückmeldung.'))

    async def test_current_question_change_without_revision_increment_rejects_candidate(self):
        await self.reject_change(lambda: setattr(self.call.dialog, 'current_question', 'Neue Frage?'))

    async def test_hidden_native_input_control_change_rejects_candidate(self):
        await self.reject_change(lambda: setattr(self.call.dialog, 'input_boundary', dict(
            source='servicenow_input_control', controlType='InputText',
            businessRequestId='new-native-control', label='Neue Eingabe?')))

    async def test_mutating_an_existing_control_label_cannot_change_the_frozen_binding(self):
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId='initial-control', label='Erste Eingabe?')
        await self.reject_change(lambda: self.call.dialog.input_boundary.update(label='Andere Eingabe?'))

    async def test_public_change_after_queueing_rejects_speech_before_tts(self):
        await self.start_local()
        self.call.vad_active = True
        await self.finish_model()
        self.assertTrue(self.lane._outputs)
        Dialog.record_public_reply(self.call.dialog, 'Neue fachliche Rückmeldung.')
        self.call.vad_active = False
        await self.until(lambda: not self.lane.output_pending and not self.call.synthesis_active)
        self.assertNotIn(FIRST, self.call.spoken)

    async def test_native_control_change_between_pcm_chunks_stops_stale_audio(self):
        second_chunk = asyncio.Event()
        async def speech(text):
            yield bytes(480)
            await second_chunk.wait()
            yield bytes(480)
        self.call.speech.synthesize = speech
        await self.start_local()
        self.model.release.set()
        await self.until(lambda: self.call.playback.accepted_samples == 240)
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId='new-control', label='Andere Angabe?')
        second_chunk.set()
        await self.until(lambda: not self.call.synthesis_active)
        self.assertEqual(self.call.playback.accepted_samples, 240)
        self.assertFalse(self.lane._speech['complete'])

    async def test_caller_context_change_rejects_candidate(self):
        def mutate():
            self.lane.context_revision += 1
            self.lane._observe_raw('Eine zusätzliche Angabe.')
        await self.reject_change(mutate)

    async def test_new_exposed_greeting_question_rejects_candidate(self):
        def mutate():
            state = self.lane.begin_greeting('Welche Angabe möchten Sie verwenden?')
            self.call.playback.put(bytes(480), self.call.playback.generation)
            self.call.playback.read(480)
            self.lane.finish_greeting(state, complete=True)
        await self.reject_change(mutate)

    async def test_bootstrap_readiness_without_revision_increment_rejects_old_candidate(self):
        await self.start_local()
        self.bootstrap_release.set()
        await self.until(lambda: not self.lane.bootstrap_pending)
        await self.finish_model()
        await self.until(lambda: not self.lane.output_pending and not self.call.synthesis_active)
        self.assertNotIn(FIRST, self.call.spoken)

    async def test_processing_fact_exposed_after_bootstrap_retains_strict_invalidation(self):
        self.bootstrap_release.set()
        await self.until(lambda: not self.lane.bootstrap_pending)
        self.progress()
        await self.start_local()
        self.assertTrue(any(fact['source_event'] == 'servicenow_processing_presentation'
                            for fact in self.model.inputs[0][1]['public_findings']))
        self.progress(2)
        await self.finish_model()
        await self.until(lambda: not self.lane.output_pending and not self.call.synthesis_active)
        self.assertNotIn(FIRST, self.call.spoken)

    async def test_own_completed_history_between_streamed_sentences_does_not_self_invalidate(self):
        self.model.two_sentences = True
        await self.start_local()
        self.model.release.set()
        await self.until(lambda: FIRST in self.call.spoken and not self.call.synthesis_active)
        self.call.playback.read(len(self.call.playback.data))
        self.lane._update_speech_cursor()
        self.assertTrue(self.lane._spoken_history)
        self.progress()
        self.model.second_release.set()
        await self.until(lambda: SECOND in self.call.spoken)
        self.assertEqual(len(self.model.inputs), 1)

    async def test_discard_diagnostics_are_bounded_fixed_codes_without_private_text(self):
        await self.start_local()
        turn = self.lane._pending[0]
        _, snapshot, observation = self.lane._dialogue_snapshot(turn, self.lane.epoch)
        self.call.dialog.current_question = 'private-marker-not-for-diagnostics?'
        candidate = SimpleNamespace(text='private-marker-not-for-diagnostics', identity=self.model.identity)
        with self.assertLogs('native-voice', level='INFO') as captured:
            for _ in range(20):
                self.assertFalse(self.lane._admit_conversation(candidate, turn, self.lane.epoch,
                                                              observation, snapshot))
        self.assertEqual(len(captured.output), 8)
        self.assertTrue(all('stage=discarded reason=context_changed' in line for line in captured.output))
        self.assertNotIn('private-marker', '\n'.join(captured.output))


if __name__ == '__main__':
    unittest.main()
