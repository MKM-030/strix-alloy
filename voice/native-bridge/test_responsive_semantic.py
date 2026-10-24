"""Synthetic semantic contract and transaction races; no qualification corpus."""
import asyncio
import json
import tempfile
import unittest
from contextlib import contextmanager
import sqlite3
from dataclasses import replace
from pathlib import Path

from business_tasks import Agent, Scope, StoreConflict
from conversation_router import ConversationRouter, RoutingContext, Route, LoopbackConversationModel
from task_store import TaskStore
from task_coordinator import TaskCoordinator
from servicenow_executor import LegacyVAExecutor


AGENT = Agent('desk', 'a1', 'r1', {k: True for k in
              ('new_task', 'continue_task', 'amend_task', 'cancel_task')},
              name='Service Desk', description='Hilfe bei Arbeitsplatz und IT',
              supported_intents=('new_task', 'continue_task', 'amend_task'))


def proposal(intent, ref='', alias='', relation='', evidence=''):
    return dict(intent=intent, task_ref=ref, agent_alias=alias, relation=relation, evidence=evidence)


def wire_proposal(data, context):
    """Translate synthetic intent fixtures into the closed-choice wire contract.

    This is only test authoring convenience; product rejects the former protocol.
    Malformed fixture bindings deliberately remain malformed for negative tests.
    """
    from routing_policy import policy_snapshot
    snapshot = policy_snapshot(context)
    old_keys = {'intent', 'task_ref', 'agent_alias', 'relation', 'evidence'}
    if set(data) != old_keys:
        return data
    intent = data['intent']
    meaning = {'status': 'reference', '': 'unclear'}.get(data['relation'], data['relation'])
    if meaning in ('repeat', 'explain'):
        intent = 'clarification'
    ref = data['task_ref']
    target = ''
    if ref:
        try: target = snapshot.tasks[int(ref[1:]) - 1]['task_id'] if ref.startswith('t') and int(ref[1:]) > 0 else 'invalid'
        except (ValueError, IndexError): target = 'invalid'
    candidate = next((c for c in snapshot.candidates if c.intent == intent and meaning in c.meanings
        and (not target or c.task_id == target) and (not data['agent_alias'] or c.agent_alias == data['agent_alias'])), None)
    from route_proposal import ProposalContract
    option = next((o for o in ProposalContract(snapshot).options if o.candidate == candidate
        and o.meaning == meaning and o.domain == ('suitable' if intent == 'new_task' else 'na')), None)
    return {'choice': option.id if option else 'o99'}


class Model:
    def __init__(self, result):
        self.result, self.calls = result, 0

    async def classify(self, text, context):
        self.calls += 1
        return wire_proposal(self.result, context)


def context(question='Wie lautet Ihr Name?', **extra):
    task = dict(task_id='actual-workflow-id', scope_id='s', state='awaiting_input',
                context_version=1, open_question=question, agent_alias='desk', **extra)
    return RoutingContext('s', [task], agents=[AGENT], question_task_id=task['task_id'] if question else '',
                          last_question=question, question_version=1 if question else None,
                          workflow_task_id=task['task_id'])


class SemanticContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_answers_and_corrections_reject_controls_negation_and_hypothesis(self):
        cases = [('An welchen Lieferort soll geliefert werden?', 'Storniere die Flugreise'),
                 ('An welchen Lieferort soll geliefert werden?', 'Bitte die Flugreise stoppen'),
                 ('Wie lautet Ihr Name?', 'Nicht Nora Berg'),
                 ('Wie lautet Ihr Name?', 'Wenn Nora Berg')]
        for question, text in cases:
            with self.subTest(question=question, text=text):
                self.assertEqual((await ConversationRouter().route(text, context(question))).intent, 'clarification')
                previous = context('', previous_question=question, previous_question_version=0)
                self.assertEqual((await ConversationRouter().route('Korrektur: ' + text, previous)).intent, 'clarification')

    async def test_quoted_controls_reject_but_requested_quoted_values_remain_eligible(self):
        quotes = [("'", "'"), ('‘', '’'), ('‚', '‘'), ('‹', '›')]
        for opening, closing in quotes:
            with self.subTest(quotes=(opening, closing)):
                ctx = RoutingContext('s', [], agents=[AGENT])
                model = Model(proposal('new_task', alias='desk', relation='request', evidence='Mein Bildschirm flackert.'))
                text = f'Service Desk: {opening}Mein Bildschirm flackert.{closing}'
                self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, 'clarification')
                model = Model(proposal('stop_speaking', relation='audio', evidence='schweige'))
                self.assertEqual((await ConversationRouter(model).route(f'{opening}Bitte schweige jetzt.{closing}', context())).intent, 'clarification')
                self.assertEqual((await ConversationRouter().route(f'{opening}Hör bitte auf zu sprechen{closing}', context())).intent, 'clarification')
                model = Model(proposal('continue_task', 't1', relation='answer', evidence='Nora Berg'))
                self.assertEqual((await ConversationRouter(model).route(f'Sie können {opening}Nora Berg{closing} eintragen.', context())).intent, 'continue_task')
        self.assertEqual((await ConversationRouter(Model(proposal('new_task', alias='desk', relation='request', evidence='Mein Bildschirm flackert.'))).route('Service Desk: Mein Bildschirm flackert.', RoutingContext('s', [], agents=[AGENT]))).intent, 'new_task')
        self.assertEqual((await ConversationRouter(Model(proposal('stop_speaking', relation='audio', evidence='schweige'))).route('Bitte schweige jetzt.', context())).intent, 'stop_speaking')

    async def test_name_apostrophes_and_harmless_quoted_controls_keep_valid_answers(self):
        for name in ("De'Andre Smith", 'De’Andre Smith'):
            with self.subTest(name=name):
                self.assertEqual((await ConversationRouter().route(name, context())).intent, 'continue_task')
                model = Model(proposal('continue_task', 't1', relation='answer', evidence=name))
                text = f"Er sagte 'stornieren'. Sie können {name} eintragen."
                self.assertEqual((await ConversationRouter(model).route(text, context())).intent, 'continue_task')
        model = Model(proposal('continue_task', 't1', relation='answer', evidence='Nora Berg'))
        self.assertEqual((await ConversationRouter(model).route('Storniere die Reise; storniere die Reise; Nora Berg', context())).intent, 'clarification')

    async def test_wire_contract_has_disjoint_bindings_and_decoder_rejects_contradictions(self):
        from test_token_admission import transaction, framed, count_body, choice_body
        content = json.dumps(wire_proposal(proposal('status_query', 't1', relation='status', evidence='Fortschritt'), context()))
        body = choice_body(choices=[{'finish_reason': 'stop', 'message': {'content': content}}])
        async with transaction([framed(count_body()), framed(body)]) as (peer, model):
            route = await ConversationRouter(model).route('Zeig mir den Fortschritt.', context())
            captured = [json.loads(r[1]) for r in peer.requests]
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0], captured[1])
        self.assertEqual(route, Route('status_query', 'actual-workflow-id'))
        schema = captured[0]['response_format']['json_schema']['schema']
        self.assertEqual(set(schema['properties']), {'choice'})
        self.assertEqual(schema['required'], ['choice'])
        self.assertFalse(schema['additionalProperties'])
        self.assertNotIn('cancel_task', schema['properties']['choice']['enum'])

    async def test_model_status_uses_private_short_ref_and_no_model_prose(self):
        ctx = context()
        model = Model(proposal('status_query', 't1', relation='status', evidence='Fortschritt'))
        route = await ConversationRouter(model).route('Zeig mir den Fortschritt.', ctx)
        self.assertEqual(route, Route('status_query', 'actual-workflow-id'))
        self.assertEqual(model.calls, 1)
        from test_route_proposal_wire import decode_context
        data = decode_context(ctx.model_data())
        self.assertEqual(data['tasks'][0]['task_ref'], 't1')
        self.assertNotIn('actual-workflow-id', json.dumps(data))

    async def test_semantic_new_intake_needs_direct_selection_and_content_not_verb_list(self):
        ctx = RoutingContext('s', [], agents=[AGENT])
        cases = [('Service Desk: Mein Bildschirm flackert.', 'new_task'),
                 ('Service Desk bitte: Mein Bildschirm flackert.', 'new_task'),
                 ('Bitte an Service Desk, mein Bildschirm flackert.', 'new_task'),
                 ('Ich erwähne Service Desk. Mein Bildschirm flackert.', 'clarification'),
                 ('Service Desk hat gesagt: Mein Bildschirm flackert.', 'clarification'),
                 ('Wenn Service Desk helfen würde: Mein Bildschirm flackert.', 'clarification'),
                 ('Service Desk: ', 'clarification'),
                 ('Service Desk: "Mein Bildschirm flackert."', 'clarification'),
                 ('Nicht Service Desk: Mein Bildschirm flackert.', 'clarification')]
        for text, expected in cases:
            with self.subTest(text=text):
                evidence = 'mein Bildschirm flackert.' if 'mein Bildschirm' in text else 'Mein Bildschirm flackert.'
                model = Model(proposal('new_task', alias='desk', relation='request', evidence=evidence))
                self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, expected)

    async def test_reachable_semantic_audio_stop_has_action_scoped_evidence(self):
        ctx = context()
        for text, expected in [('Bitte schweige jetzt.', 'stop_speaking'),
                               ('Bitte schweige nicht jetzt.', 'clarification'),
                               ('Er sagte "Bitte schweige jetzt."', 'clarification'),
                               ('Wenn ich sage: Bitte schweige jetzt.', 'clarification')]:
            model = Model(proposal('stop_speaking', relation='audio', evidence='schweige'))
            self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, expected)

    async def test_negative_audio_idiom_cannot_escape_quoted_or_hypothetical_scope(self):
        for text, expected in [('Bitte nicht weiter sprechen.', 'stop_speaking'),
                               ('Er sagte "nicht weiter sprechen".', 'clarification'),
                               ('Wenn ich nicht weiter sprechen sage?', 'clarification')]:
            self.assertEqual((await ConversationRouter().route(text, context())).intent, expected)

    async def test_selected_new_request_does_not_require_old_question_to_be_live(self):
        ctx = context()
        ctx.tasks[0]['pending_delivery'] = True
        model = Model(proposal('new_task', alias='desk', relation='request', evidence='Mein Bildschirm flackert.'))
        route = await ConversationRouter(model).route('Service Desk: Mein Bildschirm flackert.', ctx)
        self.assertEqual(route, Route('new_task', agent_alias='desk'))

    async def test_model_field_answer_validates_type_without_generated_evidence(self):
        ctx = context()
        for text, expected in [('Sie können Nora Berg eintragen.', 'continue_task'),
                               ('Ja, bitte.', 'clarification')]:
            model = Model(proposal('continue_task', 't1', relation='answer'))
            self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, expected)
        # A conditional open answer needs semantic abstention, not a generated
        # evidence string. This stub does not establish model competence.
        self.assertEqual((await ConversationRouter(Model(proposal('clarification'))).route(
            'Wenn nötig: Nora Berg.', ctx)).intent, 'clarification')

    async def test_scoped_control_language_does_not_veto_harmless_answer(self):
        ctx = context()
        for text, expected in [('Bitte nichts abbrechen; Sie können Nora Berg eintragen.', 'continue_task'),
                               ('Er sagte "stornieren". Sie können Nora Berg eintragen.', 'continue_task'),
                               ('Storniere die Aufgabe; Sie können Nora Berg eintragen.', 'clarification')]:
            model = Model(proposal('continue_task', 't1', relation='answer', evidence='Nora Berg'))
            self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, expected)

    async def test_mixed_value_questions_and_unrelated_open_dialogue_are_closed(self):
        ctx = context('Wie lautet Ihr Name und an welchem Datum?')
        model = Model(proposal('continue_task', 't1', relation='answer', evidence='Nora Berg'))
        self.assertEqual((await ConversationRouter(model).route('Sie können Nora Berg eintragen.', ctx)).intent, 'clarification')

    async def test_polar_semantic_answer_and_question_explanation_remain_reachable(self):
        ctx = context('Sind diese Angaben korrekt?')
        model = Model(proposal('continue_task', 't1', relation='answer', evidence='Ja'))
        self.assertEqual((await ConversationRouter(model).route('Ja, das passt.', ctx)).intent, 'continue_task')
        model = Model(proposal('continue_task', 't1', relation='explain', evidence='Frage'))
        route = await ConversationRouter(model).route('Diese Frage ist unklar.', ctx)
        self.assertEqual(route.intent, 'clarification')
        self.assertIn(ctx.last_question, route.reply)
        self.assertEqual(model.calls, 1)

    async def test_benign_negated_dialogue_and_unknown_question_not_blanket_authority(self):
        ctx = context('Welche Störung hat Ihr Bildschirm?')
        text = 'Der Bildschirm zeigt kein Bild.'
        model = Model(proposal('continue_task', 't1', relation='dialogue', evidence=text))
        self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, 'continue_task')
        for question, text in [('Unbekannter Schritt?', 'Die Flugreise geht nach Rom.'),
                               ('Welche Störung hat Ihr Bildschirm?', 'Die Flugreise geht nach Rom.')]:
            ctx = context(question)
            model = Model(proposal('clarification'))
            self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, 'clarification')
            self.assertEqual((await ConversationRouter().route(text, ctx)).intent, 'clarification')

    async def test_prior_correction_requires_journal_operation_and_no_competing_question(self):
        ctx = context('', previous_question='Wie lautet Ihr Name?', previous_question_version=0,
                      previous_question_id='q0', previous_operation_id='op1', previous_operation_version=1,
                      latest_operation_id='op1', latest_operation_version=1)
        text = 'Bitte ersetzen Sie meine Angabe durch Nora Berndt.'
        model = Model(proposal('amend_task', 't1', relation='correction', evidence='Nora Berndt'))
        self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, 'amend_task')
        del ctx.tasks[0]['previous_operation_id']
        self.assertEqual((await ConversationRouter(model).route(text, ctx)).intent, 'clarification')

    async def test_invalid_bindings_and_extra_properties_fail_closed(self):
        ctx = context()
        base = proposal('status_query', 't1', relation='status', evidence='Fortschritt')
        for change in ({'task_ref': 'actual-workflow-id'}, {'task_ref': 't9'},
                       {'agent_alias': 'desk'}, {'choice': 'o99'},
                       {'reply': 'Erfolgreich!'}, {'relation': 'request'}):
            with self.subTest(change=change):
                route = await ConversationRouter(Model({**base, **change})).route('Zeig mir den Fortschritt.', ctx)
                self.assertEqual(route.intent, 'clarification')

    async def test_ineligible_agent_is_closed_even_with_malicious_new_proposal(self):
        for agent in (replace(AGENT, capabilities={'new_task': False}),
                      replace(AGENT, supported_intents=('continue_task',))):
            model = Model(proposal('new_task', alias='desk', relation='request', evidence='Mein Bildschirm flackert.'))
            ctx = RoutingContext('s', [], agents=[agent])
            self.assertEqual((await ConversationRouter(model).route('Service Desk: Mein Bildschirm flackert.', ctx)).intent, 'clarification')
        ctx = RoutingContext('s', [], agents=[AGENT])
        # Domain suitability is semantic; the catalogue has no authoritative taxonomy.
        model = Model(proposal('clarification'))
        self.assertEqual((await ConversationRouter(model).route('Service Desk: Ich suche ein Reiseziel.', ctx)).intent, 'clarification')


class AtomicCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp.name) / 'tasks.db')
        self.scope = Scope('s', 'call', 1, 'instance', 'assistant')
        self.task = self.store.create_task(self.scope, AGENT, 'IT request')
        self.store.note_question(self.task['task_id'], 's', 'Wie lautet Ihr Name?', source='backend')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_same_version_question_replacement_is_atomic_and_duplicate_is_idempotent(self):
        self.assertTrue(callable(getattr(self.store, 'routing_checkpoint', None)))
        captured = self.store.routing_checkpoint('s')
        first_id = self.store.question('s')['question_id']
        for text in ('An welchem Datum?', 'Wie lautet Ihr Name?'):
            self.store.note_question(self.task['task_id'], 's', text, source='backend')
        self.assertNotEqual(self.store.question('s')['question_id'], first_id)
        with self.assertRaises(StoreConflict):
            self.store.accept(self.task['task_id'], 's', 'stale', 'Nora Berg', preconditions=captured)
        self.assertEqual(self.store.operations('s'), [])
        fresh = self.store.routing_checkpoint('s')
        accepted = self.store.accept(self.task['task_id'], 's', 'ok', '  Nora Berg  ', preconditions=fresh)
        self.assertEqual(self.store.accept(self.task['task_id'], 's', 'ok', '  Nora Berg  ', preconditions=fresh), accepted)
        event = self.store.events(self.task['task_id'], 's')[-1]
        self.assertEqual(event['payload']['answered_question']['question_id'], self.store.events(self.task['task_id'], 's')[-2]['event_id'])
        self.assertEqual(accepted['text'], '  Nora Berg  ')

    def test_transaction_authority_guard_runs_inside_and_rejects_before_task_creation(self):
        self.assertTrue(callable(getattr(self.store, 'routing_checkpoint', None)))
        captured = self.store.routing_checkpoint('s')
        seen = []
        def authority():
            seen.append(self.store._db.in_transaction)
            return False
        with self.assertRaises(StoreConflict):
            self.store.accept_new_task(self.scope, AGENT, 'stale-new', 'Service Desk: Hilfe',
                                       preconditions=captured, authority=authority)
        self.assertEqual(seen, [True])
        self.assertEqual(len(self.store.list_tasks('s')), 1)
        self.assertEqual(self.store.operations('s'), [])

    def test_second_connection_changes_question_between_capture_and_write_transaction(self):
        captured = self.store.routing_checkpoint('s')
        other = TaskStore(self.store.path)
        transaction = self.store._transaction
        @contextmanager
        def interleave():
            other.note_question(self.task['task_id'], 's', 'An welchem Datum?', source='backend')
            with transaction():
                yield
        self.store._transaction = interleave
        try:
            with self.assertRaises(StoreConflict):
                self.store.accept(self.task['task_id'], 's', 'raced', 'Nora Berg', preconditions=captured)
            self.assertEqual(other.operations('s'), [])
        finally:
            self.store._transaction = transaction
            other.close()

    def test_unrelated_backend_progress_does_not_invalidate_checkpoint(self):
        first = self.store.accept(self.task['task_id'], 's', 'first', 'Initial request')
        self.store.dispatch(first['operation_id'])
        self.store.note_question(self.task['task_id'], 's', 'Wie lautet Ihr Name?', source='backend')
        captured = self.store.routing_checkpoint('s')
        self.store.observe(first['operation_id'], 'progress', 'backend_observed', {'text': 'Working'})
        operation = self.store.accept(self.task['task_id'], 's', 'answer', 'Nora Berg', preconditions=captured)
        self.assertEqual(operation['text'], 'Nora Berg')

    def test_previous_question_identity_and_unknown_reservation_survive_reopen(self):
        question = self.store.question('s')
        operation = self.store.accept(self.task['task_id'], 's', 'answer', 'Nora Berg')
        self.store.dispatch(operation['operation_id'])
        self.store.close()
        self.store = TaskStore(Path(self.tmp.name) / 'tasks.db')
        self.assertTrue(self.store.has_unresolved())
        accepted = next(e for e in self.store.events(self.task['task_id'], 's') if e['type'] == 'utterance_accepted')
        self.assertEqual(accepted['payload']['answered_question'], question)
        self.store.recover()
        self.assertEqual(self.store.operations('s')[0]['dispatch_state'], 'unknown')
        self.assertIsNone(self.store.question('s'))

    def test_additive_question_identity_migration_preserves_old_journal(self):
        path = self.store.path
        original_events = self.store.events(self.task['task_id'], 's')
        self.store.close()
        old = sqlite3.connect(path)
        old.execute('ALTER TABLE scope_questions DROP COLUMN question_id')
        old.commit()
        old.close()
        self.store = TaskStore(path)
        self.assertTrue(self.store.question('s')['question_id'])
        self.assertEqual(self.store.events(self.task['task_id'], 's'), original_events)
        self.assertEqual(len(self.store.list_tasks('s')), 1)


class HeldModel(Model):
    def __init__(self, result):
        super().__init__(result)
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def classify(self, text, context):
        self.context = context
        self.entered.set()
        await self.release.wait()
        return wire_proposal(self.result, context)


class IdleDialog:
    async def turn(self, *args, **kwargs):
        raise AssertionError('No stale intake may dispatch')
    async def close(self):
        pass


class HeldClassifierRaceTest(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_local_answer_and_correction_write_no_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / 'tasks.db')
            scope = Scope('s', 'call', 1, 'instance', 'assistant')
            coordinator = TaskCoordinator(store, ConversationRouter(), [AGENT], lambda _: LegacyVAExecutor(IdleDialog(), ready=asyncio.Event()))
            async def emit(event): pass
            attachment = await coordinator.attach(scope, emit)
            try:
                task_id = await attachment.note_question('An welchen Lieferort soll geliefert werden?')
                route = await attachment.accept('unbound-cancel', 'Storniere die Flugreise')
                self.assertEqual(route.intent, 'clarification')
                self.assertEqual(store.operations('s'), [])
                store.note_question(task_id, 's', 'Wie lautet Ihr Name?', source='backend')
                for index, text in enumerate(('Nicht Nora Berg', 'Wenn Nora Berg')):
                    self.assertEqual((await attachment.accept(f'bad-name-{index}', text)).intent, 'clarification')
                    self.assertEqual(store.operations('s'), [])
                accepted = store.accept(task_id, 's', 'valid-name', 'Nora Berg')
                for index, text in enumerate(('Korrektur: Nicht Nora Berg', 'Korrektur: Wenn Nora Berg')):
                    self.assertEqual((await attachment.accept(f'bad-correction-{index}', text)).intent, 'clarification')
                    self.assertEqual([op['operation_id'] for op in store.operations('s')], [accepted['operation_id']])
            finally:
                await attachment.detach()
                await attachment.wait_closed()
                store.close()

    async def test_unbound_direct_acceptance_does_not_invent_a_previous_question(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / 'tasks.db')
            scope = Scope('s', 'call', 1, 'instance', 'assistant')
            class CaptureRouter:
                async def route(self, text, context):
                    self.context = context
                    return Route('clarification')
            router = CaptureRouter()
            coordinator = TaskCoordinator(store, router, [AGENT], lambda _: LegacyVAExecutor(IdleDialog(), ready=asyncio.Event()))
            async def emit(event): pass
            attachment = await coordinator.attach(scope, emit)
            try:
                identifier = await attachment.note_question('Wie lautet Ihr Name?')
                other = store.create_task(scope, AGENT, 'Other task')
                store.note_question(other['task_id'], 's', 'An welchem Datum?', source='backend')
                operation = store.accept(identifier, 's', 'unbound', 'Unbound direct input')
                await attachment.accept('inspect', 'Inspect checkpoint')
                captured = next(t for t in router.context.tasks if t['task_id'] == identifier)
                self.assertNotIn('previous_question', captured)
                self.assertEqual(captured['latest_operation_id'], operation['operation_id'])
                self.assertEqual(captured['latest_operation_version'], 1)
            finally:
                await attachment.detach()
                await attachment.wait_closed()
                store.close()

    async def test_semantic_status_reads_fresh_journal_without_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / 'tasks.db')
            scope = Scope('s', 'call', 1, 'instance', 'assistant')
            model = HeldModel(proposal('status_query', 't1', relation='status', evidence='Fortschritt'))
            coordinator = TaskCoordinator(store, ConversationRouter(model), [AGENT],
                                          lambda _: LegacyVAExecutor(IdleDialog(), ready=asyncio.Event()))
            events = []
            async def emit(event): events.append(event)
            attachment = await coordinator.attach(scope, emit)
            try:
                task_id = await attachment.note_question('Wie lautet Ihr Name?')
                operation = store.accept(task_id, 's', 'original', 'original request')
                store.dispatch(operation['operation_id'])
                pending = asyncio.create_task(attachment.accept('status', 'Zeig mir den Fortschritt.'))
                await asyncio.wait_for(model.entered.wait(), 1)
                store.observe(operation['operation_id'], 'progress', 'backend_observed', {'text': 'Fachlich belegter Fortschritt'})
                model.release.set()
                self.assertEqual((await pending).intent, 'status_query')
                await asyncio.sleep(0)
                self.assertEqual(len(store.operations('s')), 1)
                self.assertTrue(any('bearbeitet' in e['text'] and 'Fachlich belegter Fortschritt' in e['text'] for e in events))
            finally:
                model.release.set()
                store.settle(operation['operation_id'], replies=['Fixture abgeschlossen'], outcome='succeeded')
                await attachment.detach()
                await attachment.wait_closed()
                store.close()

    async def test_model_prior_correction_receives_real_provenance_and_preserves_text(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / 'tasks.db')
            scope = Scope('s', 'call', 1, 'instance', 'assistant')
            model = Model(proposal('amend_task', 't1', relation='correction', evidence='Nora Berndt'))
            class RecordingModel(Model):
                async def classify(self, text, context):
                    from test_route_proposal_wire import decode_context
                    self.data = decode_context(context.model_data())
                    return await super().classify(text, context)
            model = RecordingModel(model.result)
            coordinator = TaskCoordinator(store, ConversationRouter(model), [AGENT],
                                          lambda _: LegacyVAExecutor(IdleDialog(), ready=asyncio.Event()))
            async def emit(event): pass
            attachment = await coordinator.attach(scope, emit)
            try:
                task_id = await attachment.note_question('Wie lautet Ihr Name?')
                question = store.question('s')
                first = store.accept(task_id, 's', 'first', 'Nora Berg')
                original = '  Bitte ersetzen Sie meine Angabe durch Nora Berndt.  '
                route = await attachment.accept('correction', original)
                self.assertEqual(route, Route('amend_task', task_id))
                self.assertEqual(store.operations('s')[-1]['text'], original)
                self.assertNotIn('previous_question_id', model.data['tasks'][0])
                self.assertNotIn('previous_operation_id', model.data['tasks'][0])
                self.assertEqual(model.data['tasks'][0]['previous_question'], question['text'])
                self.assertIsNone(store.question('s'))
                duplicate = await attachment.accept('correction', original)
                self.assertEqual(duplicate, route)
                self.assertEqual(len(store.operations('s')), 2)
            finally:
                await attachment.detach()
                await attachment.wait_closed()
                store.close()

    async def test_existing_question_cannot_use_already_revised_agent_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / 'tasks.db')
            scope = Scope('s', 'call', 1, 'instance', 'assistant')
            coordinator = TaskCoordinator(store, ConversationRouter(), [AGENT], lambda _: LegacyVAExecutor(IdleDialog(), ready=asyncio.Event()))
            async def emit(event): pass
            attachment = await coordinator.attach(scope, emit)
            try:
                await attachment.note_question('Wie lautet Ihr Name?')
                coordinator.agents = [replace(AGENT, revision='r2')]
                route = await attachment.accept('candidate', 'Nora Berg')
                self.assertEqual(route.intent, 'clarification')
                self.assertEqual(store.operations('s'), [])
            finally:
                await attachment.detach()
                await attachment.wait_closed()
                store.close()

    async def test_question_and_registry_changes_while_model_waits_accept_nothing(self):
        for change in ('question', 'revision', 'capability', 'removal', 'detach', 'version', 'terminal', 'focus'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                store = TaskStore(Path(directory) / 'tasks.db')
                scope = Scope('s', 'call', 1, 'instance', 'assistant')
                model = HeldModel(proposal('continue_task', 't1', relation='answer', evidence='Nora Berg'))
                coordinator = TaskCoordinator(store, ConversationRouter(model), [AGENT], lambda _: LegacyVAExecutor(IdleDialog(), ready=asyncio.Event()))
                events = []
                async def emit(event): events.append(event)
                attachment = await coordinator.attach(scope, emit)
                try:
                    identifier = await attachment.note_question('Wie lautet Ihr Name?')
                    pending = asyncio.create_task(attachment.accept('candidate', 'Sie können Nora Berg eintragen.'))
                    await asyncio.wait_for(model.entered.wait(), 1)
                    if change == 'question':
                        store.note_question(identifier, 's', 'An welchem Datum?', source='backend')
                    elif change == 'revision': coordinator.agents = [replace(AGENT, revision='r2')]
                    elif change == 'capability': coordinator.agents = [replace(AGENT, capabilities={'continue_task': False})]
                    elif change == 'removal': coordinator.agents = []
                    elif change == 'detach': await attachment.detach()
                    elif change == 'version': store.accept(identifier, 's', 'other', 'Other original')
                    elif change == 'terminal': store.cancel_pending(identifier, 's', 'cancel-other', text='cancel')
                    elif change == 'focus': attachment._focus = identifier
                    model.release.set()
                    route = await pending
                    self.assertEqual(route.intent, 'clarification')
                    self.assertFalse(any(op['utterance_id'] == 'candidate' for op in store.operations('s')))
                finally:
                    model.release.set()
                    await attachment.detach()
                    await asyncio.wait_for(attachment.wait_closed(), 1)
                    store.close()
