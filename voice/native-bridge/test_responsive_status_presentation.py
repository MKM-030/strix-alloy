"""German status presentation over real local journal states; no live transport."""

import asyncio
import tempfile
import unittest
from pathlib import Path

import task_coordinator
from business_tasks import Agent, Scope, StoreDenied
from conversation_router import Route
from servicenow_executor import LegacyVAExecutor
from task_store import TaskStore


class StatusRouter:
    def __init__(self):
        self.target = ''

    async def route(self, text, context):
        return Route('status_query', self.target)


class InertDialog:
    async def turn(self, *args, **kwargs):
        raise AssertionError('a status query must not dispatch business work')

    async def close(self):
        pass


class StatusPresentationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp.name) / 'tasks.db')
        self.scope = Scope('scope', 'call', 1, 'instance', 'assistant')
        self.agent = Agent('desk', 'agent', 'revision', {key: True for key in
            ('new_task', 'continue_task', 'amend_task', 'cancel_task')})
        self.router = StatusRouter()
        self.events = []
        self.delivered = asyncio.Event()

        async def emit(event):
            self.events.append(event)
            self.delivered.set()

        self.coordinator = task_coordinator.TaskCoordinator(self.store, self.router,
            [self.agent], lambda scope: LegacyVAExecutor(InertDialog()))
        self.attachment = await self.coordinator.attach(self.scope, emit)

    async def asyncTearDown(self):
        await self.coordinator.shutdown(1)
        self.store.close()
        self.tmp.cleanup()

    def prepare(self, state, *, reply=''):
        original = '  Lieferung für Nora Berg am 17. November  '
        task = self.store.create_task(self.scope, self.agent, original)
        self.router.target = task['task_id']
        operation = self.store.accept(task['task_id'], 'scope', 'original', original,
            kind='new_task', voice_context={'assistant_id': 'assistant'})
        if state == 'cancelled':
            self.store.cancel_pending(task['task_id'], 'scope', 'cancel', text='Abbrechen')
        elif state != 'queued':
            self.store.dispatch(operation['operation_id'])
            if reply:
                self.store.observe(operation['operation_id'], 'progress',
                    'backend_observed', {'text': reply})
            if state == 'cancel_requested':
                self.store.cancel_pending(task['task_id'], 'scope', 'cancel', text='Abbrechen')
            elif state == 'outcome_unknown':
                self.store.mark_unknown(operation['operation_id'], 'synthetic_uncertain')
            elif state != 'running':
                self.store.settle(operation['operation_id'], replies=[reply] if reply else [], outcome=state)
        self.assertEqual(self.store.get_task(task['task_id'], 'scope')['state'], state)
        return task, operation

    def snapshot(self):
        return (self.store.list_tasks('scope'), self.store.operations('scope'),
            [self.store.events(task['task_id'], 'scope') for task in self.store.list_tasks('scope')],
            self.store.question('scope'), self.store.routing_checkpoint('scope'))

    async def assert_status(self, task, expected):
        before = self.snapshot()
        context_before = (self.attachment._context_task, self.attachment._focus)
        decision = await self.attachment.accept_decision('status', 'Wie ist der Stand?')
        await asyncio.wait_for(self.delivered.wait(), 1)
        self.assertEqual(decision.route, Route('status_query', task['task_id']))
        self.assertEqual(decision.route.reply, '')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.attachment._context_task, self.attachment._focus), context_before)
        self.assertEqual(len(self.events), 1)
        event = self.events[0]
        self.assertEqual(set(event), {'kind', 'task_id', 'operation_id', 'utterance_id',
            'context_version', 'text', 'priority'})
        self.assertEqual(event, dict(kind='local_reply', task_id=task['task_id'],
            operation_id='', utterance_id='status',
            context_version=self.store.get_task(task['task_id'], 'scope')['context_version'],
            text=expected, priority=0))
        self.assertLessEqual(len(event['text']), 4000)
        self.assertFalse(self.attachment._wake.is_set())

    async def test_queued_status_reports_local_acceptance_without_submission(self):
        task, _ = self.prepare('queued')
        await self.assert_status(task, 'Die Aufgabe ist lokal angenommen und wartet auf die Übermittlung.')
        self.assertEqual(self.store.operations('scope')[0]['dispatch_state'], 'unsubmitted')

    async def test_running_status_retains_observed_reply_without_claiming_completion(self):
        task, _ = self.prepare('running', reply='Zwischenstand')
        await self.assert_status(task, 'Die Aufgabe wird bearbeitet. Letzte Antwort: Zwischenstand')

    async def test_awaiting_input_status_preserves_actual_question(self):
        task, _ = self.prepare('awaiting_input', reply='An welchen Lieferort?')
        await self.assert_status(task, 'Die Aufgabe wartet auf weitere Angaben. Letzte Antwort: An welchen Lieferort?')

    async def test_succeeded_status_requires_journal_success_state(self):
        task, _ = self.prepare('succeeded', reply='Abgeschlossen')
        await self.assert_status(task, 'Die Aufgabe wurde erfolgreich abgeschlossen. Letzte Antwort: Abgeschlossen')

    async def test_failed_status_reports_journal_failure(self):
        task, _ = self.prepare('failed', reply='Nicht verfügbar')
        await self.assert_status(task, 'Die Aufgabe ist fehlgeschlagen. Letzte Antwort: Nicht verfügbar')

    async def test_cancel_requested_does_not_claim_external_cancellation(self):
        task, _ = self.prepare('cancel_requested', reply='Anfrage angekommen')
        await self.assert_status(task, 'Der Abbruch ist vorgemerkt. Eine bereits übermittelte Aktion kann ich nicht sicher stoppen; eine Stornierung ist nicht bestätigt. Letzte Antwort: Anfrage angekommen')
        self.assertEqual(self.store.operations('scope')[0]['dispatch_state'], 'submitted')

    async def test_cancelled_status_preserves_unsent_local_cancellation(self):
        task, _ = self.prepare('cancelled')
        await self.assert_status(task, 'Die Aufgabe wurde abgebrochen.')
        self.assertEqual(self.store.operations('scope')[0]['dispatch_state'], 'cancelled')
        self.assertIsNone(self.store.operations('scope')[0]['submitted_at'])

    async def test_unknown_status_cannot_establish_outcome_or_retry(self):
        task, _ = self.prepare('outcome_unknown', reply='Anfrage angekommen')
        await self.assert_status(task, 'Das Ergebnis der Aufgabe lässt sich nicht feststellen. Die Anfrage wird nicht automatisch wiederholt. Letzte Antwort: Anfrage angekommen')
        self.assertEqual(self.store.operations('scope')[0]['dispatch_state'], 'unknown')

    async def test_status_binds_original_task_and_uses_its_latest_operation_reply(self):
        task, first = self.prepare('awaiting_input', reply='Alte Antwort')
        second = self.store.accept(task['task_id'], 'scope', 'second', '  Berlin  ')
        self.store.dispatch(second['operation_id'])
        self.store.observe(second['operation_id'], 'new-progress', 'backend_observed', {'text': 'Aktueller Zwischenstand'})
        self.store.settle(second['operation_id'], replies=['Aktuelle Antwort'])
        self.store.observe(first['operation_id'], 'late-progress', 'backend_observed', {'text': 'Verspätete alte Antwort'})
        other = self.store.create_task(self.scope, self.agent, 'Andere Aufgabe')
        self.attachment._focus = other['task_id']
        await self.assert_status(task, 'Die Aufgabe wartet auf weitere Angaben. Letzte Antwort: Aktuelle Antwort')
        self.assertEqual(self.store.operations('scope')[0]['text'], '  Lieferung für Nora Berg am 17. November  ')
        self.assertEqual(self.store.operations('scope')[1]['text'], '  Berlin  ')

    async def test_status_clips_retained_text_to_public_output_limit(self):
        task, _ = self.prepare('awaiting_input', reply='Ä' * 4000)
        # Hand-counted prefix (39) plus suffix label (17) leaves 3944 characters.
        await self.assert_status(task, 'Die Aufgabe wartet auf weitere Angaben. Letzte Antwort: ' + 'Ä' * 3944)

    async def test_status_cannot_read_a_different_call_scope(self):
        task, _ = self.prepare('queued')
        other_scope = Scope('other-scope', 'other-call', 1, 'instance', 'assistant')
        foreign = self.store.create_task(other_scope, self.agent, 'Private andere Aufgabe')
        before = self.snapshot()
        self.router.target = foreign['task_id']
        with self.assertRaises(StoreDenied):
            await self.attachment.accept('status', 'Wie ist der Stand?')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.events, [])
        self.assertEqual(self.store.get_task(task['task_id'], 'scope')['state'], 'queued')


class FutureAndInvalidPresentationTest(unittest.TestCase):
    def render(self, state, reply=''):
        renderer = getattr(task_coordinator, 'render_grounded_status', None)
        self.assertTrue(callable(renderer), 'finite pure status renderer is required')
        return renderer(state, reply)

    def test_future_full_mode_states_are_pure_presentation_only(self):
        for state, expected in (
            ('ready_to_commit', 'Die Aufgabe ist zur verbindlichen Ausführung bereit; diese ist noch nicht bestätigt.'),
            ('committing', 'Die verbindliche Ausführung läuft; ihr Ergebnis ist noch nicht bestätigt.'),
        ):
            with self.subTest(state=state):
                self.assertEqual(self.render(state), expected)

    def test_missing_or_invalid_state_fails_closed_without_reply_success_claim(self):
        for state in (None, '', 'invented', 'SUCCEEDED', [], {}):
            with self.subTest(state=state):
                self.assertEqual(self.render(state, 'Erfolgreich abgeschlossen'),
                    'Der Status der Aufgabe lässt sich nicht feststellen.')


if __name__ == '__main__':
    unittest.main()
