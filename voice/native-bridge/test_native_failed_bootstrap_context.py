"""Offline failed-start context and sentence release, without a model or audio."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conversation_repair import NATURAL_CONVERSATION_PROMPT
from local_llm_socket import model_messages
from native_backend import BackendEvent
from native_duplex import NativeDuplex
from servicenow_voice_context import build_servicenow_voice_context
from test_native_duplex import FakeCall
from test_native_duplex_claim_release import SentenceModel


class FailedBootstrapContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_start_keeps_original_intake_and_guards_unproven_requirements(self):
        original = 'Der Laptop ist für Mara Testfeld.'
        correction = 'Ich meinte die Verbindung aus unserem bisherigen Gespräch.'
        requirement = 'Bitte nennen Sie mir noch den vollständigen Namen.'
        for phase in ('pending', 'failed', 'ready'):
            with self.subTest(phase=phase):
                call = FakeCall()
                lane = NativeDuplex(call)
                lane._bootstrap_state = phase
                lane._backend_unavailable = phase == 'failed'
                lane._bootstrap_failure_reason = 'servicenow_startup_not_ready'
                call.dialog.conversation_ended = phase == 'failed'
                turn = (0, correction, 2, 'b' * 32, 0)
                lane._observe_raw(original)
                lane._observe_raw(correction)
                lane._pending.extend(((0, original, 1, 'a' * 32, 0), turn))
                if phase == 'ready':
                    request_id = 'c' * 32
                    call.dialog.business_request_id = request_id
                    call.dialog.input_control = BackendEvent(1, request_id, 'InputText', requirement,
                        'owned-input', call.dialog.backend_owner)
                    call.dialog.input_boundary = dict(source='servicenow_input_control',
                        controlType='InputText', businessRequestId=request_id, label=requirement)
                    lane.question_context = lambda: (requirement, 'servicenow_input_control', True)
                try:
                    key, snapshot, observation = lane._dialogue_snapshot(turn, lane.epoch)
                    seed = NATURAL_CONVERSATION_PROMPT + '\n' + build_servicenow_voice_context().system_prompt_fragment
                    messages = model_messages(seed, json.dumps(snapshot), correction)
                    self.assertIn('Bei einer sprachlich unklaren Namensnennung oder Äußerung frage kurz '
                        'nur zu dem unklaren Teil nach.', messages[0]['content'])
                    self.assertIn('Bewahre ursprüngliche Formulierungen und spätere Korrekturen als '
                        'Gesprächsinhalt und erfinde keine kanonische Namensform.', messages[0]['content'])
                    self.assertEqual(json.loads(messages[2]['content'])['raw_inputs'], [original, correction])
                    self.assertEqual(messages[-1]['content'], correction)
                    self.assertNotIn(original, messages[0]['content'] + messages[1]['content'])
                    policy = messages[1]['content']
                    if phase == 'pending':
                        self.assertIn('Die native Verbindung ist noch nicht bereit', policy)
                        self.assertNotIn('Der Start des vorhandenen ServiceNow-Dialogs ist fehlgeschlagen.', policy)
                    elif phase == 'failed':
                        self.assertIn('Der Start des vorhandenen ServiceNow-Dialogs ist fehlgeschlagen.', policy)
                        self.assertIn('2 Originaleingaben warten noch auf Übermittlung.', policy)
                        self.assertNotIn('Die native Verbindung ist noch nicht bereit', policy)
                        model = SentenceModel([])
                        lane.conversation = model
                        cases = (
                            (requirement, 'skipped_claim'),
                            ('Ein Eintrittsdatum kann den Beginn einer Beschäftigung beschreiben.', 'enqueued'),
                        )
                        for text, expected in cases:
                            candidate = SimpleNamespace(text=text, identity=model.identity)
                            self.assertEqual(lane._release_conversation_sentence(candidate, turn, lane.epoch,
                                observation, snapshot, skip_unsupported_claim=True), expected)
                    else:
                        model = SentenceModel([])
                        lane.conversation = model
                        candidate = SimpleNamespace(text=requirement, identity=model.identity)
                        self.assertEqual(lane._release_conversation_sentence(candidate, turn, lane.epoch,
                            observation, snapshot, skip_unsupported_claim=True), 'enqueued')
                    self.assertEqual([item[1] for item in lane._pending], [original, correction])
                    self.assertEqual(call.dialog.calls, [])
                finally:
                    call.closed = True
                    await lane.close()


if __name__ == '__main__':
    unittest.main()
