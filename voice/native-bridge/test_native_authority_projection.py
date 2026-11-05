"""Real model-wire and sentence-release regressions using fake HTTP and recorded V7 text."""
import json
import unittest
from unittest.mock import patch

from local_llm_socket import LocalTextSocket
from native_backend import BackendEvent
from test_local_llm_fixed_routes import HTTP, DIRECT_CHAT, DIRECT_MODELS
import test_native_pending_requirements as pending_fixture

PRIOR = 'Wir können direkt mit der Bestellung des Laptops für den neuen Mitarbeiter beginnen.'
CLAIM = 'ServiceNow prüft nun die Daten und führt die Bestellung durch.'
SCOPE = dict(call_id='fixture-call', task_id='fixture-task', task_revision=2,
             context_revision=2, observation_revision=1)


def context():
    def fact(source, sequence, text):
        return dict(SCOPE, evidence_id='evidence-' + str(sequence), source_event=source,
                    sequence=sequence, observed_at=float(sequence), text=text, superseded=False)
    return dict(SCOPE, raw_inputs=['Hörst du mich?', 'Die Lieferung geht nach Hamburg.'],
        question='Wie lautet der Name?', capability_limits=['Beantworte die aktuelle Frage.'],
        public_findings=[fact('complete_emitted_assistant_speech', 1, PRIOR),
                         fact('servicenow_processing_presentation', 2, 'Die Eingabe wird verarbeitet.'),
                         fact('complete_public_va_reply', 3, 'Wie lautet der Name?')])


class WireProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def wire(self, encoded):
        http = HTTP(DIRECT_CHAT, DIRECT_MODELS)
        socket = LocalTextSocket(DIRECT_CHAT, 'C:/synthetic-token', http=http)
        with patch('local_llm_socket._token', return_value='synthetic-token') as token:
            await socket.send_json(dict(type='session.start', mode='text', system_prompt='Configured original seed.'))
            await socket.send_json(dict(type='session.update', system_prompt_patch=encoded))
            await socket.send_json(dict(type='input.text', text='Die Lieferung geht nach Hamburg.'))
            await socket._task
        await socket.close()
        return http, token.call_count

    async def test_actual_wire_separates_history_advisory_rules_and_native_findings(self):
        original = context()
        encoded = json.dumps(original, ensure_ascii=False)
        http, _ = await self.wire(encoded)
        messages = http.bodies[0]['messages']
        self.assertEqual([message['role'] for message in messages], ['system','system','user','user'])
        self.assertEqual(messages[0]['content'], 'Configured original seed.')
        self.assertIn(original['capability_limits'][0], messages[1]['content'])
        data = json.loads(messages[2]['content'])
        self.assertEqual(data['public_findings'], original['public_findings'][2:])
        self.assertEqual(data['conversation_history'], original['public_findings'][:1])
        self.assertEqual(data['advisory_observations'], original['public_findings'][1:2])
        self.assertEqual(data['raw_inputs'], original['raw_inputs'])
        self.assertNotIn('capability_limits', data)
        for key, value in SCOPE.items(): self.assertEqual(data[key], value)
        self.assertEqual(messages[-1]['content'], original['raw_inputs'][-1])
        self.assertNotIn(PRIOR, messages[0]['content'] + messages[1]['content'])
        self.assertEqual(json.loads(encoded), original)
        self.assertEqual(http.requests, [('GET',DIRECT_MODELS),('POST',DIRECT_CHAT)])

    async def test_invalid_context_never_reads_credentials_or_reaches_http(self):
        bad_values = ['not JSON', '[]', '{"call_id":"x","call_id":"y"}']
        for change in [dict(secret='forbidden'), dict(raw_inputs='wrong'),
                       dict(capability_limits='wrong'), dict(task_revision=True)]:
            bad_values.append(json.dumps(dict(context(), **change)))
        for field, value in [('source_event','unknown'), ('task_revision',999), ('superseded',True)]:
            altered = context(); altered['public_findings'][0][field] = value
            bad_values.append(json.dumps(altered))
        for encoded in bad_values:
            with self.subTest(encoded=encoded):
                http, tokens = await self.wire(encoded)
                self.assertEqual(http.requests, [])
                self.assertEqual(tokens, 0)


class CurrentActionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = pending_fixture.PendingRequirementTests.asyncSetUp
    asyncTearDown = pending_fixture.PendingRequirementTests.asyncTearDown
    release = pending_fixture.PendingRequirementTests.release
    native_question = pending_fixture.PendingRequirementTests.native_question

    def native_output(self, text):
        dialog = self.call.dialog
        event = BackendEvent(1, dialog.business_request_id, 'OutputText', text, '', dialog.backend_owner)
        self.assertTrue(self.lane._admit_backend_event(event, self.turn))

    async def test_recorded_v7_current_action_is_skipped_without_native_proof(self):
        self.assertEqual(self.release(CLAIM), 'skipped_claim')

    async def test_direct_present_and_committed_future_actions_require_proof(self):
        for text in ('ServiceNow speichert die Angaben.', 'Das System prüft nun die Daten.',
                     'ServiceNow wird die Daten prüfen.', 'ServiceNow wird die Bestellung durchführen.',
                     'ServiceNow führt die Bestellung durch.',
                     'ServiceNow prüft die Daten und führt die Bestellung nicht durch.'):
            with self.subTest(text=text): self.assertEqual(self.release(text), 'skipped_claim')

    async def test_not_only_and_general_comparison_do_not_hide_current_action(self):
        for text in ('ServiceNow prüft nicht nur die Daten.',
                     'ServiceNow prüft nun die Daten, wie üblicherweise.'):
            with self.subTest(text=text): self.assertEqual(self.release(text), 'skipped_claim')

    async def test_later_clause_cannot_qualify_earlier_action_or_hide_repeated_actor(self):
        for text in ('ServiceNow prüft nun die Daten und führt die Bestellung durch, wenn Sie zustimmen.',
                     'ServiceNow prüft die Daten nicht und das System führt nun die Bestellung durch.',
                     'ServiceNow prüft die Daten und das System führt üblicherweise Bestellungen durch.'):
            with self.subTest(text=text): self.assertEqual(self.release(text), 'skipped_claim')

    async def test_subordinate_negation_does_not_negate_the_main_action(self):
        for text in ('ServiceNow prüft nun die Daten, damit keine Fehler auftreten.',
                     'ServiceNow prüft nun die Daten, ob keine Fehler vorliegen.',
                     'ServiceNow prüft die Daten nicht manuell.'):
            with self.subTest(text=text): self.assertEqual(self.release(text), 'skipped_claim')

    async def test_actor_first_reported_attribution_remains_conversation(self):
        for text in ('ServiceNow prüft die Daten, sagen Sie.',
                     'ServiceNow prüft laut Ihrer Aussage nun die Daten.',
                     'ServiceNow wird die Daten prüfen, sagen Sie.'):
            with self.subTest(text=text): self.assertEqual(self.release(text), 'enqueued')

    async def test_main_predicate_negation_remains_admissible(self):
        for text in ('ServiceNow prüft die Daten nicht.', 'ServiceNow prüft keine Daten.',
                     'ServiceNow führt die Bestellung nicht durch.',
                     'ServiceNow wird die Daten nicht prüfen.'):
            with self.subTest(text=text): self.assertEqual(self.release(text), 'enqueued')

    async def test_comma_parenthesis_and_object_list_preserve_action_recognition(self):
        for text in ('ServiceNow führt die Bestellung, wie besprochen, durch.',
                     'ServiceNow wird Vorname, Nachname prüfen.'):
            with self.subTest(text=text): self.assertEqual(self.release(text), 'skipped_claim')

    async def test_questions_reports_quotes_negation_conditionals_and_general_explanations_pass(self):
        for text in ('Prüft ServiceNow nun die Daten?', 'Sie sagen, ServiceNow prüft nun die Daten.',
                     'Sie sagten: «' + CLAIM + '»', 'ServiceNow prüft die Daten nicht.',
                     'Wenn Sie freigeben, wird ServiceNow die Bestellung durchführen.',
                     'ServiceNow wird die Bestellung durchführen, wenn Sie freigeben.',
                     'ServiceNow kann Angaben prüfen.', 'ServiceNow prüft üblicherweise solche Angaben.',
                     'ServiceNow ist für die fachliche Bearbeitung zuständig.'):
            with self.subTest(text=text): self.assertEqual(self.release(text), 'enqueued')

    async def test_full_current_owned_output_corroborates(self):
        self.native_output(CLAIM.upper())
        self.assertEqual(self.release(CLAIM), 'enqueued')

    async def test_matching_old_request_output_cannot_corroborate(self):
        self.native_output(CLAIM)
        self.call.dialog.business_request_id = 'c' * 32
        self.assertEqual(self.release(CLAIM), 'skipped_claim')

    async def test_matching_foreign_owner_output_cannot_corroborate(self):
        self.native_output(CLAIM)
        self.call.dialog.backend_owner = object()
        self.assertEqual(self.release(CLAIM), 'skipped_claim')

    async def test_matching_inputtext_does_not_corroborate_an_action(self):
        self.native_question(CLAIM)
        self.assertEqual(self.release(CLAIM), 'skipped_claim')

    async def test_withheld_suppressed_or_retired_output_does_not_corroborate(self):
        self.native_output(CLAIM)
        record = next(iter(self.lane._backend_receipts.values()))
        for state in ('coalesced_control','suppressed_processing','interrupted','retired_by_call_close','unknown'):
            record['state'] = state
            with self.subTest(state=state): self.assertEqual(self.release(CLAIM), 'skipped_claim')

    async def test_substring_of_different_native_statement_is_not_proof(self):
        self.native_output('Es wäre falsch zu sagen: ' + CLAIM)
        self.assertEqual(self.release(CLAIM), 'skipped_claim')

    async def test_raw_history_and_processing_do_not_corroborate(self):
        self.lane._observe_raw(CLAIM)
        self.lane._spoken_history.append(dict(sequence=1, observed_at=1, text=CLAIM))
        self.call.dialog.processing = dict(source='servicenow_processing',agentCompletionKnown=False,
                                           revision=1,messages=[CLAIM],ageSeconds=0)
        self.assertEqual(self.release(CLAIM), 'skipped_claim')

    async def test_hard_identity_and_control_have_priority(self):
        self.model.current = False
        self.assertEqual(self.release(CLAIM), 'rejected')
        self.model.current = True
        self.lane._control_gate.binding = object()
        self.assertEqual(self.release(CLAIM), 'rejected')

    async def test_nonstreaming_rejects_without_claiming_admission(self):
        self.assertEqual(self.release(CLAIM, skip=False), 'rejected')

    async def test_stream_skips_claim_and_continues_without_another_model_request(self):
        safe = 'Sie haben einen Benutzernamen angegeben.'
        self.model.sentences = [CLAIM, safe]
        await self.lane._general_help(self.turn, self.lane.epoch)
        self.assertEqual([item.text for item in self.lane._outputs], [safe])
        self.assertEqual(len(self.model.inputs), 1)


if __name__ == '__main__': unittest.main()
