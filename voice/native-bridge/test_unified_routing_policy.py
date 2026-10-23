"""Independent Task12 properties derived from the policy specification, no corpus."""
import asyncio
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

from business_tasks import Agent, Scope
from conversation_router import ConversationRouter, RoutingContext, Route, LoopbackConversationModel
from task_coordinator import TaskCoordinator
from task_store import TaskStore
from servicenow_executor import LegacyVAExecutor

AGENT = Agent('office', 'agent-office', 'revision-a',
    {k: True for k in ('new_task', 'continue_task', 'amend_task', 'cancel_task')},
    name='Büroservice', description='Unterstützt Büroausstattung und Arbeitsplatztechnik',
    supported_intents=('new_task', 'continue_task', 'amend_task'))


def context(question='Wie lautet Ihr Name?', prior=None):
    task = dict(task_id='work-11', scope_id='scope', state='awaiting_input',
        context_version=2, open_question=question or None, agent_alias='office',
        agent_id=AGENT.agent_id, registry_revision=AGENT.revision)
    if prior:
        task.update(previous_question=prior, previous_question_id='question-before',
            previous_question_version=1, previous_question_source='backend',
            previous_operation_id='operation-before', previous_operation_version=2,
            previous_operation_state='submitted', latest_operation_id='operation-before',
            latest_operation_version=2, latest_operation_state='submitted')
    return RoutingContext('scope', [task], question_task_id='work-11' if question else '',
        question_version=2 if question else None, question_id='question-now' if question else '',
        question_source='backend' if question else '', last_question=question,
        agents=[AGENT])


class SemanticModel:
    def __init__(self, intent, meaning, evidence, value='', domain='na', target='', held=False):
        self.intent, self.meaning, self.evidence = intent, meaning, evidence
        self.value, self.domain, self.target = value, domain, target
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.held, self.calls = held, 0

    async def classify(self, text, snapshot):
        self.calls += 1
        self.snapshot = snapshot
        self.entered.set()
        if self.held:
            await self.release.wait()
        candidate = next((c for c in snapshot.candidates if c.intent == self.intent
            and self.meaning in c.meanings and (not self.target or c.task_id == self.target)), None)
        return dict(candidate=candidate.ref if candidate else 'c999', meaning=self.meaning,
            domain=self.domain, evidence=self.evidence, value_evidence=self.value)


class UnifiedPolicyTest(unittest.IsolatedAsyncioTestCase):
    async def decide(self, model, text, ctx):
        router = ConversationRouter(model)
        self.assertTrue(callable(getattr(router, 'decide', None)), 'request-bound decision API missing')
        return await router.decide(text, ctx)

    async def test_whole_value_and_duplicate_literal_spans_have_same_binding(self):
        for text in ('Sie dürfen Greta Falk eintragen.', 'Greta Falk, ich wiederhole Greta Falk.'):
            for evidence, value in ((text, ''), ('Greta Falk', ''), (text, 'Greta Falk')):
                with self.subTest(text=text, evidence=evidence, value=value):
                    d = await self.decide(SemanticModel('continue_task', 'answer', evidence, value), text, context())
                    self.assertEqual(d.route, Route('continue_task', 'work-11'))

    async def test_type_contradiction_does_not_depend_on_optional_value_span(self):
        text = 'Sie dürfen Greta Falk eintragen.'
        outcomes = []
        for evidence, value in ((text, ''), ('Greta Falk', ''), (text, 'Greta Falk')):
            decision = await self.decide(SemanticModel('continue_task', 'answer', evidence, value),
                text, context('An welchem Datum?'))
            outcomes.append(decision.route.intent)
        self.assertEqual(len(set(outcomes)), 1)

    async def test_all_competing_targets_survive_model_data_and_large_context_fails_closed(self):
        ctx = context()
        for index in range(2, 9):
            ctx.tasks.append(dict(ctx.tasks[0], task_id=f'work-{index}2', open_question=None))
        model = SemanticModel('status_query', 'reference', 'Fortschritt')
        d = await self.decide(model, 'Zeige den Fortschritt.', ctx)
        self.assertEqual(d.route.intent, 'clarification')
        self.assertEqual(len(model.snapshot.model_data()['tasks']), 8)
        self.assertEqual(len([c for c in model.snapshot.candidates if c.intent == 'status_query']), 8)
        for task in ctx.tasks: task['previous_question'] = 'X' * 4000
        model = SemanticModel('status_query', 'reference', 'Fortschritt')
        d = await self.decide(model, 'Zeige den Fortschritt.', ctx)
        self.assertEqual(d.reason, 'context_budget')
        self.assertEqual(model.calls, 0)

    async def test_direct_loopback_classify_uses_same_snapshot_schema(self):
        from route_proposal import ProposalContract
        from routing_policy import policy_snapshot
        model = LoopbackConversationModel(None, 'http://127.0.0.1:9933/v1/chat/completions', 'synthetic', '')
        captured = []
        def request(payload):
            captured.append(json.loads(payload))
            return json.dumps({'choices': [{'message': {'content': json.dumps(dict(candidate='c0', meaning='unclear', domain='na', evidence='', value_evidence=''))}}]}).encode()
        model._request = request
        ctx = context()
        await model.classify('Unklar', ctx)
        self.assertEqual(captured[0]['response_format']['json_schema']['schema'], ProposalContract(policy_snapshot(ctx)).schema())
        self.assertEqual(captured[0]['max_tokens'], 128)

    async def test_full_schema_request_overflow_is_diagnosed_without_discarding_candidates(self):
        ctx = context()
        ctx.agents = [replace(AGENT, alias=f'office-{i}', agent_id=f'agent-{i}', name=f'Service {i}') for i in range(16)]
        for i in range(2, 9):
            ctx.tasks.append(dict(ctx.tasks[0], task_id=f'work-{i}2', open_question=None, objective='Aufgabenbeschreibung ' * 18))
        model = LoopbackConversationModel(None, 'http://127.0.0.1:9933/v1/chat/completions', 'synthetic', '')
        def request(payload): raise AssertionError('Oversized request must not reach transport')
        model._request = request
        decision = await self.decide(model, 'Bitte prüfe das Anliegen.', ctx)
        self.assertEqual(decision.route.intent, 'clarification')
        self.assertEqual(decision.reason, 'context_budget')

    async def test_independent_request_cannot_be_inferred_as_location_answer(self):
        ctx = context('An welchen Lieferort soll geliefert werden?')
        self.assertEqual((await ConversationRouter().route('Ich brauche eine neue Tastatur.', ctx)).intent, 'clarification')
        text = 'Außerdem möchte ich einen neuen Auftrag anlegen.'
        d = await self.decide(SemanticModel('continue_task', 'dialogue', text), text, ctx)
        self.assertEqual(d.route.intent, 'clarification')

    async def test_natural_date_words_are_not_proven_names(self):
        for answer in ('Morgen', 'Mittwoch', 'Übermorgen', 'Nächsten Donnerstag'):
            d = await self.decide(SemanticModel('continue_task', 'answer', answer), answer, context('An welchem Datum?'))
            self.assertEqual(d.route.intent, 'continue_task', answer)

    async def test_order_nouns_are_dialogue_but_independent_imperatives_are_requests(self):
        for text, expected in (
            ('Meine Bestellung wurde beschädigt geliefert.', 'continue_task'),
            ('Der Kauf wurde bereits bezahlt.', 'continue_task'),
            ('Die Buchung ist in der Übersicht nicht sichtbar.', 'continue_task'),
            ('Zusätzlich fehlt die Anleitung.', 'continue_task'),
            ('Bestelle einen Ersatzbildschirm.', 'clarification'),
            ('Bitte die Flugreise stoppen.', 'clarification'),
            ('Ich möchte außerdem einen Bildschirm bestellen.', 'clarification')):
            d = await self.decide(SemanticModel('continue_task', 'dialogue', text), text, context('Beschreiben Sie das Problem.'))
            self.assertEqual(d.route.intent, expected, text)

    async def test_new_request_negation_is_action_clause_scoped(self):
        ctx = RoutingContext('scope', [], agents=[AGENT])
        for payload, expected in (('Bestelle einen Bildschirm. Kein Zubehör.', 'new_task'),
                                  ('Bestelle einen Bildschirm; kein Zubehör.', 'new_task'),
                                  ('Bestelle keinen Bildschirm.', 'clarification'),
                                  ('Wenn möglich: Bestelle einen Bildschirm.', 'clarification')):
            text = 'Büroservice: ' + payload
            for evidence in (payload, payload.split('.')[0].split(';')[0]):
                d = await self.decide(SemanticModel('new_task', 'request', evidence, domain='suitable'), text, ctx)
                self.assertEqual(d.route.intent, expected, evidence)

    async def test_proposal_stage_is_request_bound_for_accepted_rejected_and_unclear(self):
        for intent, meaning, text, evidence, domain, expected in (
            ('new_task', 'request', 'Büroservice: Der Scanner streikt.', 'Der Scanner streikt.', 'suitable', 'new_task'),
            ('new_task', 'request', 'Büroservice: Der Scanner streikt.', 'Der Scanner streikt.', 'unsuitable', 'clarification'),
            ('clarification', 'unclear', 'Unbestimmtes Anliegen', '', 'na', 'clarification')):
            d = await self.decide(SemanticModel(intent, meaning, evidence, domain=domain), text, RoutingContext('scope', [], agents=[AGENT]))
            self.assertIsNotNone(getattr(d, 'proposal', None))
            self.assertEqual((d.proposal.status, d.proposal.intent, d.proposal.meaning, d.proposal.domain), ('decoded', intent, meaning, domain))
            self.assertEqual(d.route.intent, expected)
            with self.assertRaises(FrozenInstanceError): d.proposal.domain = 'changed'
        class InvalidModel:
            async def classify(self, *_): return {'private': 'caller content'}
        d = await self.decide(InvalidModel(), 'Unbestimmtes Anliegen?', context())
        self.assertEqual(d.proposal.status, 'schema_rejected')
        self.assertNotIn('caller content', repr(d.proposal))
        class TimedOutModel:
            async def classify(self, *_): raise TimeoutError('private data')
        d = await self.decide(TimedOutModel(), 'Unbestimmtes Anliegen?', context())
        self.assertEqual(d.proposal.status, 'timeout')

    async def test_no_lexical_echo_and_unknown_question_kind_are_not_semantic_vetoes(self):
        for question, answer, meaning in (
            ('Beschreiben Sie das Problem am Arbeitsplatz.', 'Nach dem Einschalten bleibt alles schwarz.', 'dialogue'),
            ('Welche Kennung steht oben?', 'Oben lese ich Gamma sieben.', 'answer'),
            ('An welchem Datum soll geliefert werden?', 'Am dritten Dezember.', 'answer'),
            ('Können Sie mir Ihren Namen nennen?', 'Mein Name ist Greta Falk.', 'answer')):
            with self.subTest(question=question):
                d = await self.decide(SemanticModel('continue_task', meaning, answer), answer, context(question))
                self.assertEqual(d.route.intent, 'continue_task')
        self.assertEqual((await ConversationRouter().route('Frei erfundene Antwort', context('Unbekannter Schritt?'))).intent, 'clarification')

    async def test_current_prior_distinct_reference_accepts_but_competing_question_clarifies(self):
        text = 'Korrigiere meine frühere Angabe auf Greta Falk.'
        for current, expected in (('An welchem Datum?', 'amend_task'), ('Wie lautet Ihr Name?', 'clarification')):
            d = await self.decide(SemanticModel('amend_task', 'correction', text, 'Greta Falk'),
                text, context(current, prior='Wie lautet Ihr Name?'))
            self.assertEqual(d.route.intent, expected)
        ctx = context('', prior='Wie lautet Ihr Name?')
        ctx.tasks[0]['latest_operation_id'] = 'another-operation'
        d = await self.decide(SemanticModel('amend_task', 'correction', text), text, ctx)
        self.assertEqual(d.route.intent, 'clarification')

    async def test_every_direct_cancel_class_reachable_and_negative_forms_closed(self):
        forms = ('Storniere work-11.', 'Brich bitte work-11 ab.', 'Bitte work-11 abbrechen.',
                 'Würdest du bitte work-11 stornieren?', 'Ich möchte work-11 stornieren.',
                 'Würden Sie bitte die Aufgabe abbrechen?')
        for text in forms:
            with self.subTest(text=text):
                d = await self.decide(None, text, context())
                self.assertEqual(d.route, Route('cancel_task', 'work-11'))
                for negative in ('Er sagte „' + text + '“', 'Wenn ich sage: ' + text,
                                 text.rstrip('.?') + ' nicht.'):
                    self.assertEqual((await self.decide(None, negative, context())).route.intent, 'clarification')

    async def test_negated_control_does_not_block_separate_answer_clause(self):
        text = 'Bitte nicht stornieren; als Namen nehmen Sie Greta Falk.'
        d = await self.decide(SemanticModel('continue_task', 'answer', 'Greta Falk'), text, context())
        self.assertEqual(d.route.intent, 'continue_task')

    async def test_focus_cannot_select_multiple_or_foreign_status_target(self):
        ctx = context()
        ctx.tasks.append(dict(ctx.tasks[0], task_id='work-22', open_question=None))
        for focus in ('work-11', 'work-22'):
            ctx.focus_task_id = focus
            for text in ('Status bitte.', 'Status von work-99 bitte.'):
                d = await self.decide(SemanticModel('status_query', 'reference', 'Status'), text, ctx)
                self.assertEqual(d.route.intent, 'clarification')
        self.assertEqual((await self.decide(None, 'Status von work-22 bitte.', ctx)).route, Route('status_query', 'work-22'))

    async def test_foreign_named_status_is_not_replaced_by_only_available_task(self):
        ctx = context()
        ctx.tasks[0]['objective'] = 'Scanner reparieren'
        for text in ('Status meiner Hotelbuchung bitte.', 'Wie ist der Stand der Flugreise?'):
            d = await self.decide(None, text, ctx)
            self.assertEqual(d.route.intent, 'clarification')

    async def test_semantic_status_paraphrase_has_semantic_reference_but_true_scope(self):
        ctx = context()
        ctx.tasks[0]['objective'] = 'Digitalisierungsgerät instand setzen'
        ctx.tasks.append(dict(ctx.tasks[0], task_id='work-22', objective='Lampen austauschen', open_question=None))
        text = 'Wie ist der Stand beim defekten Scanner?'
        model = SemanticModel('status_query', 'reference', 'defekten Scanner', target='work-11')
        d = await self.decide(model, text, ctx)
        self.assertEqual(d.route, Route('status_query', 'work-11'))
        self.assertEqual(d.reason, 'semantic_reference')
        self.assertEqual(model.calls, 1)
        for text, evidence in (('Wie ist der Stand?', 'Stand'),
                               ('Stand von work-99?', 'work-99'),
                               ('Stand der fremden Aufgabe?', 'fremden Aufgabe')):
            d = await self.decide(SemanticModel('status_query', 'reference', evidence, target='work-11'), text, ctx)
            self.assertEqual(d.route.intent, 'clarification')
        ctx.tasks.pop()
        model = SemanticModel('clarification', 'unclear', '')
        d = await self.decide(model, 'Status meiner Hotelbuchung bitte.', ctx)
        self.assertEqual(d.route.intent, 'clarification')
        self.assertEqual(model.calls, 1)

    async def test_domain_judgment_and_explicit_selection_are_separate(self):
        ctx = RoutingContext('scope', [], agents=[AGENT])
        text = 'Büroservice: Der Scanner zieht kein Papier ein.'
        for domain, expected in (('suitable', 'new_task'), ('unsuitable', 'clarification'), ('unclear', 'clarification')):
            d = await self.decide(SemanticModel('new_task', 'request', 'Der Scanner zieht kein Papier ein.', domain=domain), text, ctx)
            self.assertEqual(d.route.intent, expected)
        text = 'Ich erwähne Büroservice. Der Scanner zieht kein Papier ein.'
        d = await self.decide(SemanticModel('new_task', 'request', 'Der Scanner zieht kein Papier ein.', domain='suitable'), text, ctx)
        self.assertEqual(d.route.intent, 'clarification')

    async def test_grounded_help_exposes_actual_source_and_content_without_leakage(self):
        router = ConversationRouter()
        self.assertTrue(callable(getattr(router, 'decide', None)))
        ctx = context()
        repeated, explained, generic = await asyncio.gather(
            router.decide('Wiederhole die Frage.', ctx), router.decide('Was bedeutet die Frage?', ctx),
            router.decide('Unverständlich alles.', RoutingContext('scope', [])))
        self.assertEqual(repeated.disposition, 'grounded_repeat')
        self.assertEqual(explained.disposition, 'grounded_explanation')
        self.assertEqual(repeated.help_source.question_id, 'question-now')
        self.assertEqual(repeated.help_source.context_version, 2)
        self.assertIn(ctx.last_question, repeated.route.reply)
        self.assertIn('Vor- und Nachname', explained.route.reply)
        self.assertEqual(generic.disposition, 'clarification')
        self.assertIsNone(generic.help_source)
        self.assertEqual([f.name for f in fields(Route)], ['intent', 'task_id', 'agent_alias', 'reply'])
        self.assertEqual(Route('status_query', 'work-11', '', ''), Route('status_query', 'work-11'))

    async def test_definition_omitted_for_output_limit_is_repeat_not_explanation(self):
        question = 'Wie lautet Ihr Name?' + 'x' * (4000 - len('Wie lautet Ihr Name?'))
        decision = await self.decide(None, 'Was bedeutet die Frage?', context(question))
        self.assertEqual(decision.route.reply, question)
        self.assertEqual(decision.disposition, 'grounded_repeat')
        self.assertEqual(decision.help_source.definition_key, '')

    async def test_snapshot_is_deeply_immutable_and_held_model_uses_captured_state(self):
        ctx = context()
        model = SemanticModel('continue_task', 'answer', 'Greta Falk', held=True)
        router = ConversationRouter(model)
        self.assertTrue(callable(getattr(router, 'decide', None)))
        pending = asyncio.create_task(router.decide('Sie dürfen Greta Falk eintragen.', ctx))
        await model.entered.wait()
        ctx.tasks[0]['open_question'] = 'An welchem Datum?'
        ctx.last_question = 'An welchem Datum?'
        with self.assertRaises(TypeError): model.snapshot.tasks[0]['open_question'] = 'Mutiert'
        with self.assertRaises((FrozenInstanceError, AttributeError)): model.snapshot.last_question = 'Mutiert'
        model.release.set()
        self.assertEqual((await pending).route.intent, 'continue_task')
        self.assertEqual(model.snapshot.last_question, 'Wie lautet Ihr Name?')

    async def test_wire_schema_is_exact_and_cancel_never_model_candidate(self):
        from route_proposal import ProposalContract
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('routing_policy'), 'shared policy missing')
        import routing_policy
        snap = routing_policy.policy_snapshot(context())
        contract = ProposalContract(snap)
        schema = contract.schema()
        branches = schema['oneOf']
        for branch in branches:
            self.assertEqual(set(branch['properties']), {'candidate', 'meaning', 'domain', 'evidence', 'value_evidence'})
        cancel_refs = {c.ref for c in snap.candidates if c.intent == 'cancel_task'}
        self.assertFalse(cancel_refs.intersection(b['properties']['candidate']['const'] for b in branches))
        for value in ({'candidate': 'c0', 'meaning': 'unclear', 'domain': 'na', 'evidence': '', 'value_evidence': '', 'reply': 'done'},
                      {'candidate': next(iter(cancel_refs)), 'meaning': 'request', 'domain': 'na', 'evidence': 'Bitte', 'value_evidence': ''}):
            with self.assertRaises(ValueError): contract.decode(value)
        self.assertEqual(contract.decode(dict(candidate='c0', meaning='unclear', domain='na', evidence='', value_evidence='')).candidate, 'c0')


class UnifiedCoordinatorTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp.name) / 'tasks.db')
        self.events = []
        self.ready = asyncio.Event()
        self.calls = []
        test = self
        class Dialog:
            async def turn(self, text, on_reply=None, voice_context=None):
                test.calls.append(text)
                return []
            async def close(self): pass
        async def emit(event): self.events.append(event)
        self.coordinator = TaskCoordinator(self.store, ConversationRouter(), [AGENT],
            lambda _: LegacyVAExecutor(Dialog(), ready=self.ready))
        self.attachment = await self.coordinator.attach(Scope('scope', 'call', 1, 'instance', 'assistant'), emit)
        self.identifier = await self.attachment.note_question('Wie lautet Ihr Name?')

    async def asyncTearDown(self):
        await self.coordinator.shutdown(.5)
        self.store.close()
        self.tmp.cleanup()

    async def test_stale_help_does_not_render_old_source(self):
        model = SemanticModel('clarification', 'explain', 'Bitte erläutern', held=True)
        self.coordinator.router = ConversationRouter(model)
        self.assertTrue(callable(getattr(self.coordinator.router, 'decide', None)))
        pending = asyncio.create_task(self.attachment.accept('help', 'Bitte erläutern.'))
        await model.entered.wait()
        self.store.note_question(self.identifier, 'scope', 'An welchem Datum?', source='backend')
        model.release.set()
        route = await pending
        await asyncio.sleep(0)
        self.assertNotIn('Wie lautet Ihr Name?', route.reply)
        self.assertFalse(any(e.get('help_source') for e in self.events))
        self.assertEqual(self.store.operations('scope'), [])

    async def test_decision_metadata_is_request_bound_and_legacy_fake_has_no_grounding(self):
        self.assertTrue(callable(getattr(self.attachment, 'accept_decision', None)))
        decision = await self.attachment.accept_decision('repeat', 'Wiederhole die Frage.')
        await asyncio.sleep(0)
        event = next(e for e in self.events if e.get('utterance_id') == 'repeat')
        self.assertEqual(decision.disposition, 'grounded_repeat')
        self.assertEqual(decision.help_source.question_id, self.store.question('scope')['question_id'])
        self.assertEqual(set(event), {'kind', 'task_id', 'operation_id', 'utterance_id', 'context_version', 'text', 'priority'})
        class LegacyRouter:
            async def route(self, text, context): return Route('clarification', reply='Legacy Antwort')
        self.coordinator.router = LegacyRouter()
        decision = await self.attachment.accept_decision('legacy', 'anything')
        await asyncio.sleep(0)
        event = next(e for e in self.events if e.get('utterance_id') == 'legacy')
        self.assertIsNone(decision.help_source)

    async def test_new_competing_task_during_status_classification_invalidates_target(self):
        model = SemanticModel('status_query', 'reference', 'Fortschritt', held=True)
        self.coordinator.router = ConversationRouter(model)
        pending = asyncio.create_task(self.attachment.accept_decision('status-race', 'Zeige den Fortschritt.'))
        await model.entered.wait()
        self.store.create_task(self.attachment.scope, AGENT, 'Anderer Auftrag')
        model.release.set()
        decision = await pending
        self.assertEqual(decision.route.intent, 'clarification')
        self.assertEqual(decision.reason, 'authority_changed')

    async def test_same_version_question_identity_and_prior_operation_switch_reject(self):
        model = SemanticModel('continue_task', 'answer', 'Greta Falk', held=True)
        self.coordinator.router = ConversationRouter(model)
        pending = asyncio.create_task(self.attachment.accept_decision('answer-race', 'Sie dürfen Greta Falk eintragen.'))
        await model.entered.wait()
        self.store.note_question(self.identifier, 'scope', 'An welchem Datum?', source='backend')
        self.store.note_question(self.identifier, 'scope', 'Wie lautet Ihr Name?', source='backend')
        model.release.set()
        decision = await pending
        self.assertEqual(decision.reason, 'authority_changed')
        self.assertEqual((decision.proposal.intent, decision.proposal.meaning), ('continue_task', 'answer'))
        self.assertEqual(self.store.operations('scope'), [])
        self.store.accept(self.identifier, 'scope', 'first-answer', 'Greta Falk')
        text = 'Bitte ersetzen Sie die Angabe durch Greta Fink.'
        model = SemanticModel('amend_task', 'correction', text, held=True)
        self.coordinator.router = ConversationRouter(model)
        pending = asyncio.create_task(self.attachment.accept_decision('correction-race', text))
        await model.entered.wait()
        self.store.accept(self.identifier, 'scope', 'second-answer', 'Greta Fink', kind='amend_task')
        model.release.set()
        self.assertEqual((await pending).reason, 'authority_changed')
        self.assertEqual([op['utterance_id'] for op in self.store.operations('scope')], ['first-answer', 'second-answer'])

    async def test_registry_change_before_queued_help_output_suppresses_source(self):
        decision = await self.attachment.accept_decision('queued-help', 'Wiederhole die Frage.')
        self.assertEqual(decision.disposition, 'grounded_repeat')
        self.coordinator.agents = [replace(AGENT, revision='revision-b')]
        await asyncio.sleep(0)
        self.assertFalse(any(e['utterance_id'] == 'queued-help' for e in self.events))

    async def test_proposal_policy_and_durable_stages_are_separate(self):
        text = 'Büroservice: Bestelle einen Bildschirm. Kein Zubehör.'
        self.coordinator.router = ConversationRouter(SemanticModel('new_task', 'request', 'Bestelle einen Bildschirm', domain='suitable'))
        decision = await self.attachment.accept_decision('new-positive', text)
        self.assertEqual(decision.route.intent, 'new_task')
        self.assertEqual(self.store.operations('scope')[-1]['text'], text)
        self.assertEqual(self.coordinator.proposal_counts[('decoded', 'new_task', 'request', 'suitable')], 1)
        self.assertEqual(self.coordinator.routing_counts[('decision', 'accepted_model', 'policy')], 1)
        self.assertEqual(self.coordinator.routing_counts[('decision', 'accepted_model', 'durable_accepted')], 1)
        self.coordinator.router = ConversationRouter(SemanticModel('new_task', 'request', 'Bestelle einen Bildschirm', domain='unsuitable'))
        rejected = await self.attachment.accept_decision('new-negative', text)
        self.assertEqual(rejected.proposal.domain, 'unsuitable')
        self.assertEqual(self.coordinator.proposal_counts[('decoded', 'new_task', 'request', 'unsuitable')], 1)
        self.assertEqual(len(self.store.operations('scope')), 1)
        duplicate = await self.attachment.accept_decision('new-positive', text)
        self.assertEqual(duplicate.reason, 'duplicate_accepted')
        self.assertIsNone(duplicate.proposal)  # No model was rerun; do not invent old provenance.

    async def test_exact_caller_text_persists_and_dispatches_once(self):
        original = '  Sie dürfen Greta Falk eintragen.  '
        self.coordinator.router = ConversationRouter(SemanticModel('continue_task', 'answer', 'Greta Falk'))
        self.assertTrue(callable(getattr(self.coordinator.router, 'decide', None)))
        route = await self.attachment.accept('answer', original)
        self.assertEqual(route.intent, 'continue_task')
        await self.attachment.accept('answer', original)
        self.ready.set()
        for _ in range(50):
            if self.calls: break
            await asyncio.sleep(.01)
        self.assertEqual(self.calls, [original])
        self.assertEqual([o['text'] for o in self.store.operations('scope')], [original])


if __name__ == '__main__': unittest.main()
