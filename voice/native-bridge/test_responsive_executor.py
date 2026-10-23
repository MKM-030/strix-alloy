"""Private reconciliation and owned transport contracts; no live business calls."""
import tempfile
import unittest
from pathlib import Path

from business_tasks import Agent, Scope, StoreConflict, StoreInvalid
from task_store import TaskStore
import asyncio
import json
from unittest.mock import patch
import aiohttp


class ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.temp.name) / 'private.sqlite3')
        self.scope = Scope('scope', 'call', 1, 'instance', 'assistant')
        self.task = self.store.create_task(self.scope, Agent('agent', 'agent', 'rev', {'continue_task': True}), 'Help')
        self.op = self.store.accept(self.task['task_id'], 'scope', 'utterance', 'Exact text')
        self.store.dispatch(self.op['operation_id'])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def evidence(self):
        return dict(source='operator', observer_ref='operator-1', observation_ref='case-1',
                    task_id=self.task['task_id'], operation_id=self.op['operation_id'],
                    context_version=1, outcome='succeeded', request_ref='REQ-1')

    def test_receipt_is_monotone_and_conflicting_binding_rejected(self):
        record = self.store.record_receipt(self.op['operation_id'], request_ref='REQ-1', receipt={'status': 'accepted'})
        self.assertEqual(record['request_ref'], 'REQ-1')
        self.store.record_receipt(self.op['operation_id'], execution_ref='RITM-1')
        with self.assertRaises(StoreConflict):
            self.store.record_receipt(self.op['operation_id'], request_ref='REQ-2')
        with self.assertRaises(StoreConflict):
            self.store.record_receipt(self.op['operation_id'], receipt={'status': 'succeeded'})
        with self.assertRaises(StoreInvalid):
            self.store.record_receipt(self.op['operation_id'], receipt={'authorization': 'bad'})
        row = self.store.operations('scope')[0]
        self.assertEqual((row['request_ref'], row['execution_ref']), ('REQ-1', 'RITM-1'))

    def test_unknown_requires_correlated_actual_evidence(self):
        self.store.record_receipt(self.op['operation_id'], request_ref='REQ-1')
        self.store.mark_unknown(self.op['operation_id'], 'lost_ack')
        for evidence in ({}, {'authoritative': True}, {**self.evidence(), 'request_ref': 'REQ-2'},
                         {**self.evidence(), 'task_id': 'wrong'}, {**self.evidence(), 'source': 'timeout'},
                         {**self.evidence(), 'context_version': 2}):
            with self.subTest(evidence=evidence), self.assertRaises((StoreInvalid, StoreConflict)):
                self.store.reconcile_unknown(self.op['operation_id'], outcome='succeeded', evidence=evidence)
        self.assertTrue(self.store.has_unresolved())

    def test_correlated_resolution_once_releases_without_replay(self):
        self.store.record_receipt(self.op['operation_id'], request_ref='REQ-1')
        self.store.mark_unknown(self.op['operation_id'], 'lost_ack')
        first = self.store.reconcile_unknown(self.op['operation_id'], outcome='succeeded', evidence=self.evidence())
        second = self.store.reconcile_unknown(self.op['operation_id'], outcome='succeeded', evidence=self.evidence())
        self.assertEqual(first, second)
        self.assertFalse(self.store.has_unresolved())
        self.assertEqual(self.store.pending('scope'), [])
        with self.assertRaises(StoreConflict):
            self.store.dispatch(self.op['operation_id'])
        events = self.store.events(self.task['task_id'], 'scope')
        self.assertEqual(sum(e['type'] == 'operation_reconciled' for e in events), 1)

    def test_reconciliation_event_failure_rolls_back_resolution(self):
        self.store.record_receipt(self.op['operation_id'], request_ref='REQ-1')
        self.store.mark_unknown(self.op['operation_id'], 'lost_ack')
        original = self.store._event
        def fail(*args, **kwargs):
            raise RuntimeError('disk failure')
        self.store._event = fail
        with self.assertRaises(RuntimeError):
            self.store.reconcile_unknown(self.op['operation_id'], outcome='succeeded', evidence=self.evidence())
        self.store._event = original
        self.assertTrue(self.store.has_unresolved())

    def test_receipt_event_failure_rolls_back_and_unsubmitted_receipt_denied(self):
        original = self.store._event
        self.store._event = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('disk failure'))
        with self.assertRaises(RuntimeError):
            self.store.record_receipt(self.op['operation_id'], request_ref='REQ-1')
        self.store._event = original
        self.assertIsNone(self.store.operations('scope')[0]['request_ref'])
        pending = self.store.accept(self.task['task_id'], 'scope', 'u2', 'Followup')
        with self.assertRaises(StoreConflict):
            self.store.record_receipt(pending['operation_id'], request_ref='REQ-2')


class OwnedExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from servicenow_executor import OwnedTaskExecutor
        self.temp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.temp.name) / 'private.sqlite3')
        self.task = self.store.create_task(Scope('scope', 'call', 1, 'instance', 'assistant'),
                                         Agent('agent', 'agent', 'rev', {'continue_task': True}), 'Help')
        self.op = self.store.accept(self.task['task_id'], 'scope', 'u1', 'Exact text')
        self.calls = []
        async def transport(method, url, *, headers, body, allow_redirects):
            self.calls.append((method, url, headers, body, allow_redirects))
            self.assertEqual(self.store.operations('scope')[0]['dispatch_state'], 'submitted')
            raise asyncio.TimeoutError()
        self.executor = OwnedTaskExecutor(self.store, origin='https://example.service-now.com',
                                          authorization=lambda: 'Bearer private-fixture', transport=transport)

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def test_lost_ack_no_retry(self):
        body = dict(command_id=self.op['operation_id'], expected_revision='root', kind='prepare', context_version=1, proposal={
            'employee_name': 'A', 'start_date': '2026-12-01', 'delivery_location': 'B', 'manager_name': 'C'})
        await self.executor.prepare(self.op['operation_id'], 'server-task', body)
        await self.executor.prepare(self.op['operation_id'], 'server-task', body)
        self.assertEqual(len(self.calls), 1)
        method, url, headers, sent, redirects = self.calls[0]
        self.assertEqual(url, 'https://example.service-now.com/api/global/scc_voice_tasks/v2/tasks/server-task/commands')
        self.assertEqual(headers['Authorization'], 'Bearer private-fixture')
        self.assertFalse(redirects)
        self.assertTrue(self.store.has_unresolved())
        self.assertNotIn('private-fixture', json.dumps(self.store.events(self.task['task_id'], 'scope')))
        with self.assertRaises(StoreConflict):
            await self.executor.prepare(self.op['operation_id'], 'server-task', {**body, 'expected_revision': 'changed'})

    async def test_stale_callback_stored_not_reattributed(self):
        self.store.record_owned_dispatch(self.op['operation_id'], 'server-task', {'command_id': self.op['operation_id'], 'kind': 'prepare'})
        self.store.dispatch(self.op['operation_id'])
        self.store.accept(self.task['task_id'], 'scope', 'u2', 'Correction')
        event = dict(event_id='event-1', sequence=1, task_id='server-task', operation_id=self.op['operation_id'],
                     context_version=1, status='awaiting_input', text='Old question')
        self.assertFalse(self.executor.observe(self.op['operation_id'], event))
        self.assertFalse(self.executor.observe(self.op['operation_id'], event))
        self.assertEqual(self.store.get_task(self.task['task_id'], 'scope')['context_version'], 2)
        self.assertEqual(self.store.events(self.task['task_id'], 'scope')[-1]['payload']['text'], 'Old question')
        with self.assertRaises(StoreConflict):
            self.executor.observe(self.op['operation_id'], {**event, 'task_id': 'another-task'})
        with self.assertRaises(StoreConflict):
            self.executor.observe(self.op['operation_id'], {**event, 'event_id': 'event-2', 'sequence': 1})

    async def test_capability_evidence_required_even_for_server_boolean(self):
        self.assertFalse(self.executor.capabilities.authoritative_idempotency)
        for evidence in ({}, {'safe_write': True}, {'source_revision': 'hash', 'qualified': True}):
            with self.assertRaises(PermissionError):
                self.executor.qualify(evidence)
        with self.assertRaises(PermissionError):
            await self.executor.commit(self.op['operation_id'], 'server-task', {})
        self.assertEqual(self.calls, [])

    async def test_out_of_order_observation_retained_without_cursor_regression(self):
        self.store.record_owned_dispatch(self.op['operation_id'], 'server-task', {'kind': 'prepare'})
        self.store.dispatch(self.op['operation_id'])
        event = dict(event_id='later', sequence=2, task_id='server-task', operation_id=self.op['operation_id'],
                     context_version=1, status='awaiting_input', text='Later')
        self.assertTrue(self.executor.observe(self.op['operation_id'], event))
        self.assertFalse(self.executor.observe(self.op['operation_id'], {**event, 'event_id': 'earlier', 'sequence': 1, 'text': 'Earlier'}))
        events = [e for e in self.store.events(self.task['task_id'], 'scope') if e['type'] == 'owned_observation']
        self.assertEqual([e['payload']['text'] for e in events], ['Later', 'Earlier'])
        self.assertLess(events[0]['sequence'], events[1]['sequence'])

    async def test_prepared_receipt_is_ack_only_and_binding_survives_reopen(self):
        async def transport(method, url, **kwargs):
            return {'task_id':'server-task', 'command_id':self.op['operation_id'], 'kind':'prepare', 'revision':'r1'}
        self.executor._transport = transport
        body = dict(command_id=self.op['operation_id'], expected_revision='root', kind='prepare', context_version=1,
                    proposal=dict(employee_name='A', start_date='2026-12-01', delivery_location='B', manager_name='C'))
        result = await self.executor.prepare(self.op['operation_id'], 'server-task', body)
        self.assertEqual(result['outcome'], 'awaiting_input')
        self.assertFalse(result['request_ref'])
        self.assertEqual(result['receipt']['operation_ref'], 'r1')
        path = self.store.path
        self.store.close()
        self.store = TaskStore(path)
        self.assertEqual(self.store.executor_binding(self.op['operation_id'])['command'], body)
        self.assertEqual(self.store.pending('scope'), [])

    async def test_http_redirect_not_followed_and_auth_never_in_body(self):
        class Response:
            status = 302
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        captured = {}
        class Session:
            def __init__(self, **kwargs): captured['session'] = kwargs
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def request(self, *args, **kwargs):
                captured['request'] = kwargs
                return Response()
        with patch('aiohttp.ClientSession', Session), self.assertRaises(RuntimeError):
            await self.executor._http('GET', self.executor.origin+'/candidate', headers={'Authorization':'Bearer fixture'}, body=None, allow_redirects=False)
        self.assertFalse(captured['session']['trust_env'])
        self.assertFalse(captured['request']['allow_redirects'])
        self.assertIsNone(captured['request']['data'])


if __name__ == '__main__':
    unittest.main()
