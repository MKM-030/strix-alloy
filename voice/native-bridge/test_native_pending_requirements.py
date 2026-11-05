"""Recorded V5 wording through actual release and model-wire boundaries; no model/network."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_backend import BackendEvent
from native_duplex import NativeDuplex, _conversation_class
from conversation_repair import NATURAL_CONVERSATION_PROMPT
from servicenow_voice_context import build_servicenow_voice_context
from local_llm_socket import LocalTextSocket
from test_local_llm_fixed_routes import HTTP, DIRECT_CHAT, DIRECT_MODELS
from test_native_duplex import FakeCall
from test_native_duplex_claim_release import SentenceModel

RAW = ('Ich brauche ein Laptop für Marcel Käfge. Eintrittsdatum ist der 16. November 2026. '
       'Die Führungskraft ist Softwaremanager. Benutzername Sam. Lieferung nach Hamburg.')
EXCLUSION = 'Der Benutzername „Sam“ ist für den Prozess nicht relevant, da wir nur die vier genannten Daten benötigen.'
REQUIREMENT = 'Bitte nennen Sie mir noch den vollständigen Nachnamen der Führungskraft.'
SAFE = 'Sie haben einen Benutzernamen angegeben.'


class PendingRequirementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.lane = NativeDuplex(self.call)
        self.lane._request = 1
        self.lane._backend = asyncio.get_running_loop().create_future()
        self.call.dialog.business_request_id = 'a' * 32
        self.turn = (0, RAW, 2, 'b' * 32, 0)
        self.lane._observe_raw(RAW)
        self.model = SentenceModel([])
        self.lane.conversation = self.model

    async def asyncTearDown(self):
        self.call.closed = True
        await self.lane.close()

    def release(self, text, *, skip=True, binding=None):
        _, snapshot, observation = self.lane._dialogue_snapshot(self.turn, self.lane.epoch)
        candidate = SimpleNamespace(text=text, identity=self.model.identity)
        return self.lane._release_conversation_sentence(candidate, self.turn, self.lane.epoch,
            observation if binding is None else binding, snapshot, skip_unsupported_claim=skip)

    def native_question(self, text):
        dialog = self.call.dialog
        dialog.input_control = BackendEvent(1, dialog.business_request_id, 'InputText', text,
                                           'owned-control', dialog.backend_owner)
        dialog.input_boundary = dict(source='servicenow_input_control', controlType='InputText',
                                    businessRequestId=dialog.business_request_id, label=text)
        self.lane.question_context = lambda: (text, 'servicenow_input_control', True)

    async def test_recorded_identifier_exclusion_is_skipped(self):
        self.assertEqual(self.release(EXCLUSION), 'skipped_claim')

    async def test_recorded_unproven_required_field_is_skipped(self):
        self.assertEqual(self.release(REQUIREMENT), 'skipped_claim')

    async def test_nonstreaming_cannot_accept_recorded_requirement(self):
        self.assertEqual(self.release(REQUIREMENT, skip=False), 'rejected')

    async def test_quoted_wording_remains_conversation(self):
        for text in (EXCLUSION, REQUIREMENT):
            with self.subTest(text=text):
                self.assertEqual(self.release('Sie sagten: «' + text + '»'), 'enqueued')

    async def test_reported_wording_remains_conversation(self):
        self.assertEqual(self.release('Sie berichten, der Benutzername sei für den Prozess nicht relevant.'), 'enqueued')

    async def test_negation_does_not_become_a_requirement(self):
        self.assertEqual(self.release('Bitte nennen Sie mir nicht noch den vollständigen Nachnamen.'), 'enqueued')

    async def test_question_about_relevance_remains_open(self):
        self.assertEqual(self.release('Ist der Benutzername für den Prozess nicht relevant?'), 'enqueued')

    async def test_social_and_general_answers_remain_available(self):
        for text in ('Ja, ich höre Sie.', 'Ein Benutzername kann eine Person genauer zuordnen.', SAFE):
            self.assertEqual(self.release(text), 'enqueued')

    async def test_general_example_request_is_not_field_intake(self):
        self.assertEqual(self.release('Bitte nennen Sie mir noch ein Beispiel.'), 'enqueued')

    async def test_linguistic_clarification_remains_available(self):
        self.assertEqual(self.release('Bitte nennen Sie mir noch den vollständigen Satz.'), 'enqueued')

    async def test_generic_identity_request_has_no_person_or_usecase_dependency(self):
        self.assertEqual(self.release('Bitte nennen Sie mir noch den vollständigen Namen.'), 'skipped_claim')

    async def test_exact_owned_native_question_corroborates(self):
        for text in (EXCLUSION, REQUIREMENT):
            self.native_question(text)
            self.assertEqual(self.release(text), 'enqueued')

    async def test_corroboration_allows_only_full_sentence_normalization(self):
        self.native_question(REQUIREMENT.upper().replace(' ', '  '))
        self.assertEqual(self.release(REQUIREMENT), 'enqueued')

    async def test_corroboration_rejects_substring_inside_different_assertion(self):
        self.native_question('Es wäre falsch zu sagen: ' + REQUIREMENT)
        self.assertEqual(self.release(REQUIREMENT), 'skipped_claim')

    async def test_old_request_cannot_corroborate(self):
        self.native_question(REQUIREMENT)
        self.call.dialog.business_request_id = 'c' * 32
        self.assertEqual(self.release(REQUIREMENT), 'skipped_claim')

    async def test_foreign_event_owner_cannot_corroborate(self):
        self.native_question(REQUIREMENT)
        self.call.dialog.backend_owner = object()
        self.assertEqual(self.release(REQUIREMENT), 'skipped_claim')

    async def test_untyped_boundary_alone_cannot_corroborate(self):
        self.native_question(REQUIREMENT)
        self.call.dialog.input_control = None
        self.assertEqual(self.release(REQUIREMENT), 'skipped_claim')

    async def test_local_question_cannot_corroborate(self):
        self.native_question(REQUIREMENT)
        self.lane.question_context = lambda: (REQUIREMENT, 'local_clarification', True)
        self.assertEqual(self.release(REQUIREMENT), 'skipped_claim')

    async def test_processing_and_own_history_cannot_corroborate(self):
        self.call.dialog.processing = dict(source='servicenow_processing', agentCompletionKnown=False,
                                           revision=1, messages=[REQUIREMENT], ageSeconds=0)
        self.lane._spoken_history.append(dict(sequence=1, observed_at=1, text=REQUIREMENT))
        self.assertEqual(self.release(REQUIREMENT), 'skipped_claim')

    async def test_raw_correction_still_hard_rejects(self):
        binding = self.lane._dialogue_snapshot(self.turn, self.lane.epoch)[2]
        self.lane._observe_raw('Korrektur, nach Berlin.')
        self.assertEqual(self.release(REQUIREMENT, binding=binding), 'rejected')

    async def test_identity_change_still_hard_rejects(self):
        self.model.current = False
        self.assertEqual(self.release(REQUIREMENT), 'rejected')

    async def test_active_native_control_still_hard_rejects(self):
        self.lane._control_gate.binding = object()
        self.assertEqual(self.release(REQUIREMENT), 'rejected')

    async def test_epoch_change_still_hard_rejects(self):
        epoch = self.lane.epoch
        _, snapshot, observation = self.lane._dialogue_snapshot(self.turn, epoch)
        self.lane.epoch += 1
        candidate = SimpleNamespace(text=REQUIREMENT, identity=self.model.identity)
        self.assertEqual(self.lane._release_conversation_sentence(candidate, self.turn, epoch,
            observation, snapshot, skip_unsupported_claim=True), 'rejected')

    async def test_idle_dialogue_does_not_apply_pending_intake_policy(self):
        self.lane._backend.cancel()
        self.lane._backend = None
        self.assertEqual(self.release(REQUIREMENT), 'enqueued')

    async def test_stream_skips_both_recorded_sentences_and_retains_free_answer(self):
        self.model.sentences = [EXCLUSION, REQUIREMENT, SAFE]
        await self.lane._general_help(self.turn, self.lane.epoch)
        self.assertEqual([output.text for output in self.lane._outputs], [SAFE])
        self.assertEqual(self.model.inputs, [RAW])
        self.assertEqual(self.call.dialog.calls, [])

    async def test_actual_local_wire_keeps_config_and_state_dependent_policy(self):
        configured = 'Beantworte Fragen natürlich mit den konfigurierten Vorgaben.'
        self.call.call_settings = SimpleNamespace(language='de', session_parameters=lambda:
                                                  dict(prompt=dict(systemMessage=configured)))
        key, snapshot, _ = self.lane._dialogue_snapshot(self.turn, self.lane.epoch)
        _conversation_class()
        from omni_conversation import SEED_RULES, _snapshot
        seed = SEED_RULES + NATURAL_CONVERSATION_PROMPT + '\n' + build_servicenow_voice_context(self.call.call_settings).system_prompt_fragment
        http = HTTP(DIRECT_CHAT, DIRECT_MODELS)
        socket = LocalTextSocket(DIRECT_CHAT, 'C:/synthetic-unused-token', http=http)
        with patch('local_llm_socket._token', return_value='synthetic-fixture-token'):
            await socket.send_json(dict(type='session.start', mode='text', system_prompt=seed))
            await socket.send_json(dict(type='session.update', system_prompt_patch=_snapshot(snapshot, key)))
            await socket.send_json(dict(type='input.text', text=RAW))
            await socket._task
        messages = http.bodies[0]['messages']
        self.assertEqual([item['role'] for item in messages], ['system', 'system', 'user', 'user'])
        self.assertIn(configured, messages[0]['content'])
        encoded = json.loads(messages[2]['content'])
        self.assertEqual(encoded['raw_inputs'], [RAW])
        self.assertIn('keine parallele fachliche Datenerhebung', messages[1]['content'])
        self.assertIn('Relevanz', messages[1]['content'])
        await socket.close()

    async def test_pending_role_limit_is_state_dependent(self):
        context = build_servicenow_voice_context(known_state=dict(business_available=True, business_busy=False))
        self.assertFalse(any('keine parallele fachliche Datenerhebung' in rule for rule in context.capability_limits))


if __name__ == '__main__':
    unittest.main()
