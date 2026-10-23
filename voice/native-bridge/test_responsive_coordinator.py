import asyncio
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from business_tasks import Agent, Scope, StoreCapacity, StoreDenied
from conversation_router import Route, ConversationRouter
from task_store import TaskStore
from servicenow_executor import LegacyVAExecutor
from task_coordinator import TaskCoordinator


class Router:
    async def route(self, text, context):
        if text.startswith('new'):
            return Route('new_task', agent_alias='desk')
        if text == 'status':
            return Route('status_query', context.tasks[0]['task_id'])
        if text == 'stop audio':
            return Route('stop_speaking')
        if text == 'cancel':
            return Route('cancel_task', context.tasks[0]['task_id'])
        return Route('amend_task', context.tasks[0]['task_id'])


class HeldDialog:
    def __init__(self):
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.calls = []
        self.closed = False
        self.replies = ['Your name?']

    async def turn(self, text, on_reply=None, voice_context=None):
        self.calls.append((text, voice_context))
        self.started.set()
        await asyncio.wait_for(self.release.wait(), 120)
        for reply in reversed(self.replies):
            await on_reply(reply)
            await on_reply(reply)
        return list(self.replies)

    async def close(self):
        self.closed = True


async def eventually(predicate):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(.005)
    raise AssertionError('condition did not become true')


class CoordinatorTest(unittest.IsolatedAsyncioTestCase):
    async def test_late_settlement_cannot_replace_the_question_answered_before_acceptance(self):
        # Use public store operations so settlement can deliberately arrive after
        # continuation acceptance without changing the process-owned worker model.
        task = self.store.create_task(self.scope, self.agent, 'Original task')
        first = self.store.accept(task['task_id'], 'scope', 'first', 'first request')
        self.store.dispatch(first['operation_id'])
        self.store.note_question(task['task_id'], 'scope', 'Wie lautet Ihr Name?', source='backend', context_version=1)
        answer = self.store.accept(task['task_id'], 'scope', 'answer', '  Nora Berg  ')
        self.store.settle(first['operation_id'], replies=['An welchem Datum?'])
        events = self.store.events(task['task_id'], 'scope')
        noted = next(event for event in events if event['type'] == 'question_noted')
        accepted = next(event for event in events if event['type'] == 'utterance_accepted' and event['operation_id'] == answer['operation_id'])
        settled = next(event for event in events if event['type'] == 'operation_settled')
        self.assertLess(noted['sequence'], accepted['sequence'])
        self.assertLess(accepted['sequence'], settled['sequence'])
        self.assertEqual(noted['context_version'], settled['context_version'])
        self.coordinator.router = ConversationRouter()
        wrong = await self.attachment.accept('wrong-correction', 'Korrektur: Am 17. November')
        self.assertEqual(wrong.intent, 'clarification')
        self.assertEqual(len(self.store.operations('scope')), 2)
        self.assertEqual(self.store.operations('scope')[1]['text'], '  Nora Berg  ')
        self.assertIsNone(self.store.question('scope'))
        correct = await self.attachment.accept('right-correction', 'Korrektur: Nora Berndt')
        self.assertEqual((correct.intent, correct.task_id), ('amend_task', task['task_id']))
        self.assertEqual(self.store.operations('scope')[-1]['text'], 'Korrektur: Nora Berndt')
        self.assertIsNone(self.store.question('scope'))

    async def test_grounded_local_help_during_held_execution_preserves_original(self):
        await self.attachment.accept('first', 'new request')
        await self.dialog.started.wait()
        task_id = self.store.operations('scope')[0]['task_id']
        await self.attachment.note_question('An welchen Lieferort soll geliefert werden?', task_id=task_id)
        self.coordinator.router = ConversationRouter()
        for index, (text, expected) in enumerate((
            ('Was bedeutet die aktuelle Frage?', 'Ort beziehungsweise die Adresse'),
            ('Was brauchst du von mir?', 'An welchen Lieferort soll geliefert werden?'),
            ('Wiederhole die Frage', 'An welchen Lieferort soll geliefert werden?'),
            ('Was hast du verstanden?', 'new request'),
            ('Kann ich noch eine andere Frage stellen?', 'nacheinander'),
        )):
            route = await asyncio.wait_for(self.attachment.accept(f'help-{index}', text), .1)
            self.assertEqual(route.intent, 'clarification')
            self.assertIn(expected, route.reply)
        self.assertEqual(len(self.store.operations('scope')), 1)
        self.assertEqual(len(self.dialog.calls), 1)
        self.assertEqual(self.store.get_task(task_id, 'scope')['state'], 'running')
        unrelated = await self.attachment.accept('unrelated', 'Wie ist das Wetter auf dem Mars?')
        self.assertEqual(unrelated.intent, 'clarification')
        self.assertEqual(len(self.store.operations('scope')), 1)
        class SemanticModel:
            async def classify(self, text, context):
                return {'intent': 'continue_task', 'task_ref': 't1', 'agent_alias': '',
                        'relation': 'dialogue', 'evidence': 'Abholung'}
        self.coordinator.router = ConversationRouter(SemanticModel())
        original = '  Wie funktioniert die Abholung?  '
        route = await self.attachment.accept('substantive', original)
        self.assertEqual((route.intent, route.task_id), ('continue_task', task_id))
        self.assertEqual(self.store.pending('scope')[0]['text'], original)
        self.dialog.release.set()
        await eventually(lambda: len(self.dialog.calls) == 2 and not self.store.has_unresolved())
        self.assertEqual(self.dialog.calls[1][0], original)

    async def test_explicit_post_answer_correction_uses_journal_despite_focus_change(self):
        self.coordinator.router = ConversationRouter()
        task_id = await self.attachment.note_question('Wie lautet Ihr Name?')
        await self.attachment.accept('answer', '  Nora Berg  ')
        await self.dialog.started.wait()
        self.coordinator.router = Router()
        await self.attachment.accept('other', 'new second')
        self.coordinator.router = ConversationRouter()
        route = await self.attachment.accept('correction', 'Korrektur: Nora Berndt')
        self.assertEqual((route.intent, route.task_id), ('amend_task', task_id))
        self.assertIsNone(self.store.question('scope'))
        self.assertEqual(self.store.operations('scope')[-1]['text'], 'Korrektur: Nora Berndt')
        self.assertEqual((await self.attachment.accept('stale', 'Nora Busch')).intent, 'clarification')

    async def test_current_question_help_rejects_stale_and_multiple_bindings(self):
        task_id = await self.attachment.note_question('Wie lautet Ihr Name?')
        other = self.store.create_task(self.scope, self.agent, 'Other task')
        self.store.note_question(other['task_id'], 'scope', 'An welchem Datum?', source='backend')
        self.coordinator.router = ConversationRouter()
        route = await self.attachment.accept('ambiguous', 'Was bedeutet die aktuelle Frage?')
        self.assertEqual(route.intent, 'clarification')
        self.assertNotIn('Kalendertag', route.reply)
        self.assertEqual(len(self.store.operations('scope')), 0)
        self.assertNotEqual(task_id, other['task_id'])

    async def test_execution_active_tracks_eligible_work_not_unknown_or_unrelated_queue(self):
        self.assertFalse(self.attachment.execution_active)
        await self.attachment.accept('u-active', 'new first')
        self.assertTrue(self.attachment.execution_active)
        await self.dialog.started.wait()
        self.assertTrue(self.attachment.execution_active)
        await self.attachment.accept('u-other', 'new second')
        self.dialog.release.set()
        await eventually(lambda: not self.store.has_unresolved())
        self.assertFalse(self.attachment.execution_active)
        self.assertEqual(len(self.store.pending('scope')), 1)
        # Submitted observation becoming unknown must not masquerade as work forever.
        async def fail(*args, **kwargs):
            raise RuntimeError('synthetic uncertain executor')
        self.dialog.turn = fail
        await self.attachment.accept('u-uncertain', 'change request')
        await eventually(lambda: self.store.get_task(self.store.operations('scope')[0]['task_id'], 'scope')['state'] == 'outcome_unknown')
        self.assertFalse(self.attachment.execution_active)

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp.name) / 'tasks.db')
        self.scope = Scope('scope', 'call', 1, 'instance', 'assistant')
        self.agent = Agent('desk', 'agent', 'revision', {k: True for k in ('new_task', 'continue_task', 'amend_task', 'cancel_task')})
        self.dialog = HeldDialog()
        self.events = []
        async def emit(event):
            self.events.append(event)
        self.emit = emit
        self.coordinator = TaskCoordinator(self.store, Router(), [self.agent], lambda scope: LegacyVAExecutor(self.dialog))
        self.attachment = await self.coordinator.attach(self.scope, emit)

    async def asyncTearDown(self):
        self.dialog.release.set()
        await self.coordinator.shutdown(1)
        self.store.close()
        self.tmp.cleanup()

    async def test_held_120_second_request_does_not_block_local_status(self):
        await self.attachment.accept('u1', 'new request')
        await self.dialog.started.wait()
        start = time.monotonic()
        await self.attachment.accept('u2', 'status')
        await eventually(lambda: any(e['kind'] == 'local_reply' and 'running' in e['text'] for e in self.events))
        self.assertLess(time.monotonic() - start, .1)
        self.assertEqual(len(self.dialog.calls), 1)

    async def test_32_total_accepted_no_drop_and_33_rejected(self):
        await self.attachment.accept('u0', 'new request')
        await self.dialog.started.wait()
        for index in range(1, 32):
            await self.attachment.accept(f'u{index}', f'change {index}')
        self.assertEqual(len(self.store.pending('scope')), 31)
        with self.assertRaises(StoreCapacity):
            await self.attachment.accept('u32', 'change 32')
        self.assertEqual(len(self.store.pending('scope')), 31)

    async def test_new_task_never_enters_busy_or_awaiting_context(self):
        await self.attachment.accept('u1', 'new first')
        await self.dialog.started.wait()
        await self.attachment.accept('u2', 'new second')
        self.dialog.release.set()
        await eventually(lambda: self.coordinator.snapshot('scope')[0]['state'] == 'awaiting_input')
        self.assertEqual(len(self.dialog.calls), 1)
        self.assertEqual(len(self.store.pending('scope')), 1)

    async def test_audio_stop_does_not_cancel_business_and_cancel_is_honest(self):
        await self.attachment.accept('u1', 'new request')
        await self.dialog.started.wait()
        await self.attachment.accept('u2', 'stop audio')
        self.assertEqual(self.coordinator.snapshot('scope')[0]['state'], 'running')
        await self.attachment.accept('u3', 'cancel')
        self.dialog.release.set()
        await eventually(lambda: not self.store.has_unresolved())
        self.assertEqual(self.coordinator.snapshot('scope')[0]['state'], 'cancel_requested')

    async def test_amendment_suppresses_stale_question_and_preserves_exact_text(self):
        await self.attachment.accept('u1', 'new request')
        await self.dialog.started.wait()
        await self.attachment.accept('u2', '  exact amendment!  ', voice_context={'language': 'de-DE'})
        self.dialog.release.set()
        await eventually(lambda: len(self.dialog.calls) == 2 and not self.store.has_unresolved())
        await eventually(lambda: any(e['kind'] == 'backend_reply' for e in self.events))
        replies = [e for e in self.events if e['kind'] == 'backend_reply']
        self.assertEqual([e['utterance_id'] for e in replies], ['u2'])
        self.assertEqual(self.dialog.calls[1], ('  exact amendment!  ', {'language': 'de-DE'}))
        self.assertEqual(self.coordinator.snapshot('scope')[0]['open_question'], 'Your name?')

    async def test_detach_observes_submitted_without_output_or_pending_dispatch(self):
        await self.attachment.accept('u1', 'new request')
        await self.dialog.started.wait()
        await self.attachment.accept('u2', 'change')
        await self.attachment.detach()
        count = len(self.events)
        self.dialog.release.set()
        await eventually(lambda: self.dialog.closed)
        self.assertEqual(len(self.dialog.calls), 1)
        self.assertEqual(len(self.events), count)
        self.assertFalse(self.store.has_unresolved())

    async def test_second_scope_cannot_take_slot_or_read_first_scope(self):
        other = Scope('other', 'other-call', 1, 'instance', 'assistant')
        await self.attachment.accept('u1', 'new secret')
        with self.assertRaises(StoreDenied):
            await self.coordinator.attach(other, self.emit)
        self.assertEqual(self.coordinator.snapshot('other'), [])

    async def test_ready_barrier_detach_never_dispatches(self):
        await self.attachment.detach()
        await eventually(lambda: self.dialog.closed)
        ready = asyncio.Event()
        dialog = HeldDialog()
        self.attachment = await self.coordinator.attach(Scope('s2','c2',2,'instance','assistant'), self.emit,
            executor=LegacyVAExecutor(dialog, ready=ready))
        await self.attachment.accept('u1', 'new request')
        await asyncio.sleep(.01)
        self.assertFalse(self.store.has_unresolved())
        await self.attachment.detach()
        ready.set()
        await eventually(lambda: dialog.closed)
        self.assertEqual(dialog.calls, [])

    async def test_restart_unknown_blocks_dispatch_and_full_always_denied(self):
        task = self.store.create_task(Scope('old','old-call',0,'instance','assistant'), self.agent, 'Old')
        operation = self.store.accept(task['task_id'], 'old', 'old-u', 'Old', kind='new_task')
        self.store.dispatch(operation['operation_id'])
        self.store.recover()
        await self.attachment.accept('u1', 'new request')
        await asyncio.sleep(.02)
        self.assertEqual(self.dialog.calls, [])
        full = TaskCoordinator(self.store, Router(), [self.agent], lambda _: LegacyVAExecutor(self.dialog), mode='full')
        with self.assertRaises(StoreDenied):
            await full.attach(self.scope, self.emit, executor=LegacyVAExecutor(self.dialog))

    async def test_callback_duplicates_and_order_do_not_duplicate_final_output(self):
        self.dialog.replies = ['First', 'Second']
        await self.attachment.accept('u1', 'new request')
        self.dialog.release.set()
        await eventually(lambda: len([e for e in self.events if e['kind'] == 'backend_reply']) == 2)
        # Legacy strings have no sequence identity: preserve arrival order.
        self.assertEqual([e['text'] for e in self.events if e['kind'] == 'backend_reply'], ['Second', 'First'])
        events = self.store.events(self.coordinator.snapshot('scope')[0]['task_id'], 'scope')
        self.assertEqual(len([e for e in events if e['type'] == 'backend_observed']), 2)

    async def test_callback_is_audible_before_turn_ack_and_status_remains_responsive(self):
        callback = asyncio.Event()
        async def turn(text, on_reply=None, voice_context=None):
            await on_reply('Your name?')
            callback.set()
            await self.dialog.release.wait()
            return ['Your name?']
        self.dialog.turn = turn
        await self.attachment.accept('u1', 'new request')
        await callback.wait()
        await eventually(lambda: any(e['kind'] == 'backend_reply' for e in self.events))
        self.assertTrue(self.store.has_unresolved())
        await asyncio.wait_for(self.attachment.accept('status', 'status'), .1)

    async def test_greeting_question_can_accept_literal_answer_without_fake_awaiting_state(self):
        self.coordinator.router = ConversationRouter()
        task_id = await self.attachment.note_question('Wie lautet Ihr Name?')
        self.assertEqual(self.store.get_task(task_id, 'scope')['state'], 'queued')
        route = await self.attachment.accept('name', 'Marcel Muster')
        self.assertEqual((route.intent, route.task_id), ('continue_task', task_id))
        await self.dialog.started.wait()
        self.assertEqual(self.dialog.calls[0][0], 'Marcel Muster')
        self.assertIsNone(self.store.question('scope'))

    async def test_running_question_keeps_binding_after_focus_change(self):
        await self.attachment.accept('first', 'new request')
        await self.dialog.started.wait()
        task_id = self.coordinator.snapshot('scope')[0]['task_id']
        await self.attachment.note_question('Wie lautet Ihr Name?', task_id=task_id)
        await self.attachment.accept('second', 'new second')
        self.coordinator.router = ConversationRouter()
        route = await self.attachment.accept('answer', 'Marcel Muster')
        self.assertEqual(route.task_id, task_id)
        self.assertEqual(self.store.pending('scope')[-1]['text'], 'Marcel Muster')

    async def test_failed_new_acceptance_does_not_create_orphan_task(self):
        with self.assertRaises(Exception):
            await self.attachment.accept('bad', 'new request', voice_context={'token': 'forbidden'})
        self.assertEqual(self.coordinator.snapshot('scope'), [])

    async def test_tts_failure_never_retries_or_stops_business(self):
        from conversation_output import OutputArbiter
        from core import PlaybackBuffer
        class BrokenSpeech:
            async def synthesize(self, text):
                raise RuntimeError('fake audio failure')
                yield b''
        arbiter = OutputArbiter(BrokenSpeech(), PlaybackBuffer(), self.emit, lambda: True)
        self.attachment.emit = arbiter.publish
        try:
            await self.attachment.accept('first', 'new request')
            await self.dialog.started.wait()
            self.dialog.release.set()
            await eventually(lambda: not self.store.has_unresolved())
            await eventually(lambda: any(e['kind'] == 'error' for e in self.events))
            self.assertEqual(len(self.dialog.calls), 1)
            self.assertEqual(self.coordinator.snapshot('scope')[0]['state'], 'awaiting_input')
        finally:
            await arbiter.close()

    async def test_shutdown_timeout_does_not_cancel_submitted_observation(self):
        await self.attachment.accept('first', 'new request')
        await self.dialog.started.wait()
        result = await self.coordinator.shutdown(.001)
        self.assertEqual(result['pending'], 1)
        self.assertTrue(self.store.has_unresolved())
        self.assertFalse(self.dialog.closed)
        self.dialog.release.set()
        await eventually(lambda: self.dialog.closed)
        self.assertFalse(self.store.has_unresolved())

    async def test_owned_cleanup_ack_retains_scope_reservation(self):
        cleanup = asyncio.Event()
        self.dialog.must_reset = True
        async def owned_cleanup():
            await cleanup.wait()
            self.dialog.must_reset = False
        self.dialog.wait_owned_cleanup = owned_cleanup
        await self.attachment.detach()
        await eventually(lambda: self.dialog.closed)
        with self.assertRaises(StoreDenied):
            await self.coordinator.attach(Scope('other','other-call',1,'instance','assistant'), self.emit)
        cleanup.set()
        await eventually(lambda: self.coordinator._owner is None)

    async def test_question_superseded_by_pending_amendment_not_used_for_short_answer(self):
        await self.attachment.accept('first', 'new request')
        await self.dialog.started.wait()
        await self.attachment.accept('amend', 'change date')
        self.attachment.executor.ready = asyncio.Event()
        self.dialog.release.set()
        await eventually(lambda: self.coordinator.snapshot('scope')[0]['state'] == 'awaiting_input')
        self.coordinator.router = ConversationRouter()
        route = await self.attachment.accept('yes', 'Ja')
        self.assertNotEqual(route.intent, 'continue_task')
        self.assertEqual(len(self.store.pending('scope')), 1)

    async def test_new_task_duplicate_does_not_create_extra_work(self):
        await self.attachment.accept('first', 'new request')
        await self.dialog.started.wait()
        await self.attachment.accept('first', 'new request')
        self.assertEqual(len(self.coordinator.snapshot('scope')), 1)
        self.assertEqual(len(self.store.operations('scope')), 1)

    async def test_cancel_before_readiness_never_sends(self):
        self.attachment.executor.ready = asyncio.Event()
        await self.attachment.accept('first', 'new request')
        await self.attachment.accept('cancel', 'cancel')
        self.attachment.executor.ready.set()
        await asyncio.sleep(.02)
        self.assertEqual(self.dialog.calls, [])
        self.assertEqual(self.coordinator.snapshot('scope')[0]['state'], 'cancelled')

    async def test_status_includes_persisted_callback_before_settlement(self):
        callback = asyncio.Event()
        async def turn(text, on_reply=None, voice_context=None):
            await on_reply('Observed answer')
            callback.set()
            await self.dialog.release.wait()
            return ['Observed answer']
        self.dialog.turn = turn
        await self.attachment.accept('first', 'new request')
        await callback.wait()
        await self.attachment.accept('status', 'status')
        await eventually(lambda: any(e['kind'] == 'local_reply' and 'Observed answer' in e['text'] for e in self.events))

    async def test_full_mode_hashed_local_files_still_cannot_attach(self):
        from responsive_config import load_responsive_config
        folder = Path(self.tmp.name)
        capabilities = {}
        for name in ('verified_principal', 'agent_tool_binding', 'revision_fence', 'durable_operation_claim', 'reconciliation'):
            artifact = folder / (name + '.txt')
            artifact.write_text('self declared', encoding='utf-8')
            capabilities[name] = {'artifact': artifact.name, 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(), 'status': 'verified'}
        (folder / 'authority.json').write_text(json.dumps({'capabilities': capabilities}), encoding='utf-8')
        profile = folder / 'profile.json'
        profile.write_text(json.dumps({'enabled': False, 'mode': 'full', 'capability_evidence': {'authority': 'authority.json'}}), encoding='utf-8')
        config = load_responsive_config(profile)
        self.assertFalse(config.authority_verified)
        full = TaskCoordinator(self.store, Router(), [self.agent], lambda _: LegacyVAExecutor(self.dialog), mode=config.mode)
        with self.assertRaises(StoreDenied):
            await full.attach(self.scope, self.emit)
        self.assertEqual(self.dialog.calls, [])

    async def test_multiple_agents_require_explicit_question_task(self):
        self.coordinator.agents.append(Agent('other', 'a2', 'r', {'continue_task': True}))
        with self.assertRaises(StoreDenied):
            await self.attachment.note_question('Your name?')
        self.assertEqual(self.coordinator.snapshot('scope'), [])

    async def test_readiness_failure_never_claims_or_retries_business(self):
        class BrokenBarrier:
            async def wait(self):
                raise RuntimeError('fake readiness failure')
        self.attachment.executor.ready = BrokenBarrier()
        await self.attachment.accept('first', 'new request')
        await eventually(lambda: any(e['kind'] == 'error' for e in self.events))
        self.assertFalse(self.store.has_unresolved())
        self.assertEqual(len(self.store.pending('scope')), 1)
        self.assertEqual(self.dialog.calls, [])

    async def test_public_availability_tracks_owned_cleanup_and_unresolved_work(self):
        self.assertFalse(self.coordinator.available)
        await self.attachment.detach()
        await self.attachment.wait_closed()
        self.assertTrue(self.coordinator.available)
        task = self.store.create_task(Scope('old','old-call',0,'instance','assistant'), self.agent, 'Old')
        operation = self.store.accept(task['task_id'], 'old', 'old-u', 'Old', kind='new_task')
        self.store.dispatch(operation['operation_id'])
        self.assertFalse(self.coordinator.available)
        self.store.recover()
        self.assertFalse(self.coordinator.available)

    async def test_wait_closed_timeout_does_not_cancel_business(self):
        await self.attachment.accept('first', 'new request')
        await self.dialog.started.wait()
        await self.attachment.detach()
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(self.attachment.wait_closed(), .001)
        self.assertTrue(self.store.has_unresolved())
        self.dialog.release.set()
        await asyncio.wait_for(self.attachment.wait_closed(), 1)
        self.assertTrue(self.dialog.closed)
        self.assertFalse(self.store.has_unresolved())
        self.assertTrue(self.coordinator.available)

    async def test_availability_remains_false_after_shutdown_or_for_full_mode(self):
        await self.coordinator.shutdown(1)
        self.assertFalse(self.coordinator.available)
        full = TaskCoordinator(self.store, Router(), [self.agent], lambda _: LegacyVAExecutor(self.dialog), mode='full')
        self.assertFalse(full.available)

    async def test_settlement_question_supersedes_callback_for_name_routing(self):
        async def turn(text, on_reply=None, voice_context=None):
            await on_reply('Your name?')
            return ['Your name?', 'Soll ich fortfahren?']
        self.dialog.turn = turn
        await self.attachment.accept('first', 'new request')
        await eventually(lambda: self.coordinator.snapshot('scope')[0]['state'] == 'awaiting_input')
        self.coordinator.router = ConversationRouter()
        route = await self.attachment.accept('name', 'Marcel Muster')
        self.assertNotEqual(route.intent, 'continue_task')
        self.assertEqual(len(self.store.operations('scope')), 1)

    async def test_callback_only_question_remains_answerable_after_empty_settlement(self):
        calls = []
        async def turn(text, on_reply=None, voice_context=None):
            calls.append(text)
            if len(calls) == 1:
                await on_reply('Your name?')
            return []
        self.dialog.turn = turn
        await self.attachment.accept('first', 'new request')
        await eventually(lambda: self.coordinator.snapshot('scope')[0]['result_version'] == 1)
        self.coordinator.router = ConversationRouter()
        route = await self.attachment.accept('name', 'Marcel Muster')
        self.assertEqual(route.intent, 'continue_task')
        await eventually(lambda: len(calls) == 2)
        self.assertEqual(calls, ['new request', 'Marcel Muster'])
        self.assertIsNone(self.store.question('scope'))

    async def test_status_prefers_newer_settlement_over_historical_callbacks(self):
        turns = 0
        async def turn(text, on_reply=None, voice_context=None):
            nonlocal turns
            turns += 1
            if turns == 1:
                await on_reply('First result')
                return ['First result']
            return ['Final result']
        self.dialog.turn = turn
        await self.attachment.accept('first', 'new request')
        await eventually(lambda: self.coordinator.snapshot('scope')[0]['result_version'] == 1)
        first = self.store.operations('scope')[0]
        await self.attachment.accept('second', 'continue request')
        await eventually(lambda: self.coordinator.snapshot('scope')[0]['result_version'] == 2)
        # A delayed older-operation observation must not outrank the newer result.
        self.store.observe(first['operation_id'], 'late-first', 'backend_observed', {'text': 'Late first result'})
        await self.attachment.accept('status', 'status')
        await eventually(lambda: any(e['utterance_id'] == 'status' for e in self.events))
        status = next(e['text'] for e in self.events if e['utterance_id'] == 'status')
        self.assertIn('Letzte Antwort: Final result', status)
        self.assertNotIn('first result', status.lower())

    async def test_status_prefers_current_callback_over_previous_settlement(self):
        turns = 0
        callback = asyncio.Event()
        async def turn(text, on_reply=None, voice_context=None):
            nonlocal turns
            turns += 1
            if turns == 1:
                return ['Previous result']
            await on_reply('Current progress')
            callback.set()
            await self.dialog.release.wait()
            return ['Current progress']
        self.dialog.turn = turn
        await self.attachment.accept('first', 'new request')
        await eventually(lambda: self.coordinator.snapshot('scope')[0]['result_version'] == 1)
        await self.attachment.accept('second', 'continue request')
        await callback.wait()
        await self.attachment.accept('status', 'status')
        await eventually(lambda: any(e['utterance_id'] == 'status' for e in self.events))
        status = next(e['text'] for e in self.events if e['utterance_id'] == 'status')
        self.assertIn('Letzte Antwort: Current progress', status)
        self.assertTrue(self.store.has_unresolved())


if __name__ == '__main__':
    unittest.main()
