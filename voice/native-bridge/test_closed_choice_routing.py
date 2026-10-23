"""Task14 public C01-C24 synthetic contract cases; not model qualification."""
import asyncio
import json
import unittest
from dataclasses import replace

from conversation_router import ConversationRouter, RoutingContext, LoopbackConversationModel
from route_proposal import ProposalContract
from routing_policy import PolicyRules, policy_snapshot
from test_unified_routing_policy import AGENT, context
import test_unified_routing_policy as fixtures


class ChoiceModel:
    def __init__(self, intent, meaning, domain='na', target='', held=False):
        self.intent, self.meaning, self.domain, self.target = intent, meaning, domain, target
        self.held, self.calls = held, 0
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def classify(self, text, snapshot):
        self.calls += 1
        self.text, self.snapshot = text, snapshot
        contract = ProposalContract(snapshot)
        option = next(o for o in contract.options if o.candidate.intent == self.intent
                      and o.meaning == self.meaning and o.domain == self.domain
                      and (not self.target or o.candidate.task_id == self.target))
        self.entered.set()
        if self.held:
            await self.release.wait()
        return {'choice': option.id}


class PublicChoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_c01_new_audio_reachability_and_single_field_decode(self):
        text = 'Deine gesprochene Ausgabe soll jetzt enden.'
        self.assertFalse(PolicyRules.audio_witness(text))
        # Hand-derived first option: c0 -> clarify, first nonclarify -> o00/audio.
        class Model:
            async def classify(self, *_): return {'choice': 'o00'}
        decision = await ConversationRouter(Model()).decide(text, RoutingContext('scope', []))
        self.assertEqual(decision.route.intent, 'stop_speaking')

    async def test_c01_single_field_decode(self):
        try:
            decoded = LoopbackConversationModel.decode_route('{"choice":"o00"}')
        except ValueError:
            decoded = None
        self.assertEqual(decoded, {'choice': 'o00'})

    async def test_observation_records_independent_stages_and_timings(self):
        d = await ConversationRouter(ChoiceModel('stop_speaking', 'audio')).decide(
            'Deine gesprochene Ausgabe soll jetzt enden.', RoutingContext('scope', []))
        self.assertTrue(getattr(d, 'policy_accepted', False))
        self.assertEqual(d.origin, 'model')
        self.assertGreaterEqual(d.model_elapsed_ms, 0)
        self.assertGreaterEqual(d.route_elapsed_ms, d.model_elapsed_ms)
        self.assertIsNone(d.durable_acceptance)
        self.assertFalse(d.stale_rejected)

    async def test_semantic_polite_modal_audio_is_not_hypothetical(self):
        d = await ConversationRouter(ChoiceModel('stop_speaking', 'audio')).decide(
            'Würdest du bitte deine gesprochene Ausgabe jetzt enden lassen?', RoutingContext('scope', []))
        self.assertEqual(d.route.intent, 'stop_speaking')

    async def test_request_contract_is_frozen_and_late_response_cannot_bind_next_request(self):
        first = ChoiceModel('continue_task', 'dialogue', held=True)
        router = ConversationRouter(first)
        pending = asyncio.create_task(router.decide('Die Gegenseite versteht mich nur mit Aussetzern.', context('Beschreiben Sie bitte den Fehler am Headset.')))
        await asyncio.wait_for(first.entered.wait(), 1)
        # A separate outstanding request on the same router must use its own map.
        router.model = ChoiceModel('stop_speaking', 'audio')
        second = await router.decide('Deine gesprochene Ausgabe soll jetzt enden.', RoutingContext('scope', []))
        first.release.set()
        self.assertEqual((await pending).route.intent, 'continue_task')
        self.assertEqual(second.route.intent, 'stop_speaking')
        c = ProposalContract(first.snapshot)
        with self.assertRaises((AttributeError, TypeError)):
            c.options = ()
        with self.assertRaises(TypeError):
            c._by_id['o00'] = c.options[-1]

    async def test_maximal_catalogue_passes_complete_request_to_fake_transport(self):
        ctx = context('Wie lautet Ihr Name?', 'An welchem Datum?')
        for i in range(2, 9):
            ctx.tasks.append(dict(ctx.tasks[0], task_id=f'work-{i}2', open_question=None))
        ctx.agents = [replace(AGENT, alias=f'office-{i}', agent_id=f'agent-{i}') for i in range(16)]
        seen = []
        model = LoopbackConversationModel(None, 'http://127.0.0.1:9933/v1/chat/completions', 'synthetic', '')
        def transport(payload):
            seen.append(payload)
            return b'{"choices":[{"message":{"content":"{\\"choice\\":\\"clarify\\"}"}}]}'
        model._request = transport
        d = await ConversationRouter(model).decide('  Bitte prüfe meine Äußerung.  ', ctx)
        self.assertEqual(d.reason, 'unclear')
        request = json.loads(seen[0])
        data = json.loads(request['messages'][1]['content'])
        self.assertEqual(data['utterance'], '  Bitte prüfe meine Äußerung.  ')
        self.assertEqual(len(data['context']['options']), 70)
        self.assertLessEqual(len(seen[0]), 16384)
        self.assertEqual(request['max_tokens'], 24)

    async def test_completed_after_deadline_is_discarded(self):
        class LateModel:
            async def classify(self, *_):
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    return {'choice': 'o00'}
        router = ConversationRouter(LateModel())
        d = await router.decide('Deine gesprochene Ausgabe soll jetzt enden.', RoutingContext('scope', []))
        self.assertEqual(d.reason, 'timeout')
        self.assertIsNone(d.proposal.choice_bound)
        router.model = ChoiceModel('clarification', 'unclear')
        d = await router.decide('Bitte prüfe meine Äußerung.', RoutingContext('scope', []))
        self.assertEqual(d.reason, 'unclear')
        self.assertEqual(d.proposal.offered_intent, 'clarification')

    async def test_c02_c05_c07_audio_veto_and_no_cancel_option(self):
        for text in ('Auf dem Zettel steht: „Deine gesprochene Ausgabe soll jetzt enden.“',
                     'Du sollst deine gesprochene Ausgabe nicht beenden.',
                     'Falls morgen jemand anruft, soll deine gesprochene Ausgabe enden.',
                     'Deine gesprochene Ausgabe soll jetzt enden; storniere den Auftrag.',
                     'Storniere nicht den Monitorersatz.',
                     '„Deine gesprochene Ausgabe soll jetzt enden.',
                     'Er sagte, deine gesprochene Ausgabe soll jetzt enden.',
                     'Deine gesprochene Ausgabe soll enden und beantworte meine Frage.'):
            with self.subTest(text=text):
                d = await ConversationRouter(ChoiceModel('stop_speaking', 'audio')).decide(text, context())
                self.assertEqual(d.route.intent, 'clarification')
                self.assertEqual(d.reason, 'audio_context')
        c = ProposalContract(context())
        self.assertNotIn('cancel_task', [o.candidate.intent for o in c.options])

    async def test_c08_c11_answers_dialogue_correction_without_generated_evidence(self):
        cases = (
            ('Wer ist Ihre Teamleitung?', None, 'Mira Falk; den Auftrag bitte nicht stornieren.', 'answer', 'continue_task'),
            ('An welchem Tag beginnt der Einsatz?', None, 'Am einundzwanzigsten Februar.', 'answer', 'continue_task'),
            ('Beschreiben Sie bitte den Fehler am Headset.', None, 'Die Gegenseite versteht mich nur mit Aussetzern.', 'dialogue', 'continue_task'),
            ('An welchen Lieferort soll geliefert werden?', 'Wer ist Ihre Teamleitung?', 'Meine vorige Angabe zur Teamleitung war falsch: Mira Falk.', 'correction', 'amend_task'))
        for question, prior, text, meaning, intent in cases:
            with self.subTest(text=text):
                d = await ConversationRouter(ChoiceModel(intent, meaning)).decide(text, context(question, prior))
                self.assertEqual(d.route.intent, intent)

    async def test_c05_answer_does_not_swallow_competing_control(self):
        d = await ConversationRouter(ChoiceModel('continue_task', 'answer')).decide(
            'Deine gesprochene Ausgabe soll jetzt enden; storniere den Auftrag.', context())
        self.assertEqual(d.reason, 'competing_request')

    async def test_c12_same_kind_candidates_remain_but_unclear_choice_abstains(self):
        ctx = context('Wann endet der Einsatz?', 'Wann beginnt der Einsatz?')
        c = ProposalContract(ctx)
        self.assertIn('correction', [o.meaning for o in c.options])
        d = await ConversationRouter(ChoiceModel('clarification', 'unclear')).decide(
            'Ich meinte den zweiundzwanzigsten Februar.', ctx)
        self.assertEqual(d.route.intent, 'clarification')

    def status_context(self, identical=False):
        ctx = context('')
        ctx.tasks[0]['objective'] = 'Defektes Headset austauschen'
        ctx.tasks.append(dict(ctx.tasks[0], task_id='work-22',
            objective=ctx.tasks[0]['objective'] if identical else 'Zugang zum Druckraum'))
        return ctx

    async def test_c13_c15_c16_structural_status_ambiguity(self):
        for ctx, text in ((self.status_context(True), 'Wie steht es um den Headset-Austausch?'),
                          (self.status_context(), 'Gibt es schon einen Fortschritt?'),
                          (self.status_context(), 'Wie steht es um Ticket Nr. fremdq9?')):
            for target in ('work-11', 'work-22'):
                ctx.focus_task_id = target
                d = await ConversationRouter(ChoiceModel('status_query', 'reference', target=target)).decide(text, ctx)
                self.assertEqual(d.route.intent, 'clarification', text)

    async def test_c14_c24_valid_wrong_semantic_status_is_bound_not_runtime_proven(self):
        text = 'Ist die Sache mit dem defekten Headset schon weitergekommen?'
        for target in ('work-11', 'work-22'):
            d = await ConversationRouter(ChoiceModel('status_query', 'reference', target=target)).decide(text, self.status_context())
            self.assertEqual(d.route.task_id, target)
            self.assertTrue(d.proposal.choice_bound)
            # work-22 is deliberately wrong: independent scorer must flag critical.
            self.assertEqual(d.reason, 'semantic_reference')

    async def test_c17_c18_domain_abstention_and_direct_agent_selection(self):
        agent = replace(AGENT, alias='Arbeitsplatz', name='Arbeitsplatz')
        ctx = RoutingContext('scope', [], agents=[agent])
        for text, domain, expected in (
            ('Arbeitsplatz: Ich benötige Ersatz für mein defektes Headset.', 'suitable', 'new_task'),
            ('Arbeitsplatz: Ich möchte einen Flug reservieren.', 'unsuitable', 'domain_unsuitable'),
            ('Arbeitsplatz: Ich brauche Unterstützung bei der Sache.', 'unclear', 'domain_unclear'),
            ('Der Arbeitsplatz-Agent wurde mir genannt.', 'suitable', 'selection_required')):
            d = await ConversationRouter(ChoiceModel('new_task', 'request', domain)).decide(text, ctx)
            self.assertEqual(d.route.intent if expected == 'new_task' else d.reason, expected)

    async def test_c19_grounded_help_has_actual_question_and_definition(self):
        text = 'Welche Person soll ich als Führungskraft nennen?'
        d = await ConversationRouter(ChoiceModel('clarification', 'explain')).decide(text, context('Wer ist Ihre Führungskraft?'))
        self.assertIsNotNone(d.help_source)
        self.assertIn('Wer ist Ihre Führungskraft?', d.route.reply)
        self.assertIn('zuständige', d.route.reply)

    async def test_c20_separate_diagnostics(self):
        for content, expected in (
            ('{"choice":"o00","choice":"clarify"}', (False, None, True, None)),
            ('{"choice":"o99"}', (True, True, True, False)),
            ('{"choice":"o00"}\nProsa', (False, None, True, None)),
            ('{"choice":"o00","domain":"na"}', (True, False, True, None)),
            (' ' * 65, (None, None, False, None))):
            model = LoopbackConversationModel(None, 'http://127.0.0.1:9933/v1/chat/completions', 'synthetic', '')
            model._request = lambda _, c=content: json.dumps({'choices': [{'message': {'content': c}}]}).encode()
            d = await ConversationRouter(model).decide('Bitte prüfe meine Äußerung.', RoutingContext('scope', []))
            self.assertEqual(d.route.intent, 'clarification')
            o = d.proposal
            self.assertEqual((o.json_syntax_valid, o.schema_shape_valid, o.bounds_valid, o.choice_bound), expected)

    async def test_c23_seventy_choices_complete_and_private_metadata_hidden(self):
        ctx = context('Wie lautet Ihr Name?', 'An welchem Datum?')
        for i in range(2, 9):
            ctx.tasks.append(dict(ctx.tasks[0], task_id=f'work-{i}2', open_question=None))
        ctx.agents = [replace(AGENT, alias=f'office-{i}', agent_id=f'agent-{i}') for i in range(16)]
        c = ProposalContract(ctx)
        self.assertEqual(len(c.options), 70)
        self.assertEqual(len({o.id for o in c.options}), 70)
        self.assertEqual(len(c.model_data()['tasks']), 8)
        self.assertEqual(len(c.model_data()['agents']), 16)
        encoded = json.dumps(c.model_data())
        for private in ('question-before', 'operation-before', 'question-now', 'work-11', 'revision-a'):
            self.assertNotIn(private, encoded)
        for task in ctx.tasks: task['objective'] = 'x' * 4000
        model = ChoiceModel('stop_speaking', 'audio')
        d = await ConversationRouter(model).decide('Bitte prüfe meine Äußerung.', ctx)
        self.assertEqual(d.reason, 'context_budget')
        self.assertEqual(model.calls, 0)


class PublicCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.UnifiedCoordinatorTest.asyncSetUp
    asyncTearDown = fixtures.UnifiedCoordinatorTest.asyncTearDown

    async def test_c01_c08_original_text_once_no_audio_business_operation(self):
        self.coordinator.router = ConversationRouter(ChoiceModel('stop_speaking', 'audio'))
        d = await self.attachment.accept_decision('audio', 'Deine gesprochene Ausgabe soll jetzt enden.')
        self.assertEqual(d.route.intent, 'stop_speaking')
        self.assertEqual(self.store.operations('scope'), [])
        self.store.note_question(self.identifier, 'scope', 'Wer ist Ihre Teamleitung?', source='backend')
        self.coordinator.router = ConversationRouter(ChoiceModel('continue_task', 'answer'))
        text = '  Mira Falk; den Auftrag bitte nicht stornieren.  '
        first = await self.attachment.accept('answer', text)
        self.assertEqual(first.intent, 'continue_task')
        self.assertEqual(await self.attachment.accept('answer', text), first)
        self.assertEqual([o['text'] for o in self.store.operations('scope')], [text])
        self.assertEqual(self.coordinator.router.model.text, text)

    async def test_c21_status_question_identity_change_rejects_stale_choice(self):
        model = ChoiceModel('status_query', 'reference', held=True)
        self.coordinator.router = ConversationRouter(model)
        pending = asyncio.create_task(self.attachment.accept_decision('status', 'Gibt es einen Fortschritt?'))
        await asyncio.wait_for(model.entered.wait(), 1)
        self.store.note_question(self.identifier, 'scope', 'An welchem Datum?', source='backend')
        model.release.set()
        d = await pending
        self.assertEqual(d.reason, 'authority_changed')
        self.assertTrue(d.stale_rejected)
        self.assertEqual(d.route.intent, 'clarification')
        self.assertEqual(self.store.operations('scope'), [])

    async def test_status_publication_rechecks_checkpoint(self):
        self.coordinator.router = ConversationRouter(ChoiceModel('status_query', 'reference'))
        d = await self.attachment.accept_decision('status', 'Gibt es einen Fortschritt?')
        self.assertEqual(d.route.intent, 'status_query')
        self.store.note_question(self.identifier, 'scope', 'An welchem Datum?', source='backend')
        await asyncio.sleep(0)
        self.assertFalse(any(e['utterance_id'] == 'status' for e in self.events))

    async def test_c06_business_cancel_only_changes_local_state(self):
        task = self.store.create_task(self.attachment.scope, AGENT, 'Monitorersatz')
        self.coordinator.router = ConversationRouter()
        d = await self.attachment.accept_decision('cancel', 'Bitte storniere den Monitorersatz.')
        self.assertEqual(d.route.intent, 'cancel_task')
        self.assertIsNone(d.proposal)
        self.assertEqual(self.store.get_task(task['task_id'], 'scope')['state'], 'cancelled')
        self.assertEqual(self.store.operations('scope'), [])

    async def test_c06_submitted_cancel_does_not_claim_external_cancellation(self):
        task = self.store.create_task(self.attachment.scope, AGENT, 'Monitorersatz')
        operation = self.store.accept(task['task_id'], 'scope', 'business', 'Originaler Auftrag')
        self.store.dispatch(operation['operation_id'])
        try:
            self.coordinator.router = ConversationRouter()
            d = await self.attachment.accept_decision('cancel', 'Bitte storniere den Monitorersatz.')
            self.assertEqual(d.route.intent, 'cancel_task')
            self.assertEqual(self.store.get_task(task['task_id'], 'scope')['state'], 'cancel_requested')
            await asyncio.sleep(0)
            self.assertTrue(any('Stornierung ist nicht bestätigt' in e['text'] for e in self.events))
            self.assertEqual(len(self.store.operations('scope')), 1)
        finally:
            self.store.settle(operation['operation_id'], replies=[], outcome='succeeded')
