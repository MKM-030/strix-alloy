"""Real owned bootstrap and cleanup, with synthetic remote CREATE transport."""
import asyncio
import json
import unittest
from unittest.mock import patch

from voice import caller_binding as authority
from voice.tests import test_local_caller_create as fixtures


class CreateFailureSettlement(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.OwnedCreateBridgeTests.asyncSetUp
    start = fixtures.OwnedCreateBridgeTests.start
    settle = fixtures.OwnedCreateBridgeTests.settle

    def remote(self, status=403, *, close_failure=False, mutate=None, foreign=False):
        owner = self
        self.remote_posts = 0
        class Response:
            headers = {'Content-Type': 'application/json'}
            def __init__(self, request):
                self.status = status
                self.request = request
                self.content = self
            async def __aenter__(self): return self
            async def __aexit__(self, *args):
                if mutate: mutate()
                if close_failure: raise RuntimeError('PRIVATE_RESPONSE')
            async def iter_chunked(self, size):
                request = self.request
                yield json.dumps({'result': {'status': 'failure', 'failure': {
                    'contract': 'scc_local_caller_create_v1', 'version': 1,
                    'outcome': 'not_created', 'reason': 'access_denied',
                    'requestId': 'f'*32 if foreign else request['requestId'],
                    'clientSessionId': request['clientSessionId'],
                    'clientMessageId': request['clientMessageId'],
                    'serviceId': '8aa131d793f787105c8132d47aba1095',
                    'contextProfile': 'c623e20f93374354e7f2b9fa6aba1081'}}}).encode()
        class HTTP:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def post(self, url, **options):
                owner.remote_posts += 1
                return Response(options['json'])
        async def create(*args, **options):
            return await authority.create_native_caller_conversation(*args, **options,
                http_factory=lambda **_: HTTP())
        self.creator.side_effect = create

    async def settled_session(self):
        # Capture before cleanup may remove the proved absent owner.
        response = await self.start()
        tasks = list(self.bridge.owned_tasks)
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        return response

    async def test_received401_has_fixed_auth_reason_but_retains_unknown_cleanup(self):
        self.remote(status=401)
        response = await self.settled_session()
        self.assertEqual(response.status, 502)
        self.assertEqual(response.content_type, 'application/json')
        data = await response.json()
        self.assertEqual(data, {'error': {'source': 'scc_local_caller_create_v1',
            'version': 1, 'reason': 'caller_create_unauthorized',
            'creationOutcome': 'unknown', 'receiptId': ''}})
        session = next(iter(self.bridge.sessions.values()))
        self.assertEqual(session.cleanup_state, 'unresolved')
        self.assertFalse(session.ended)
        self.assertEqual(self.remote_posts, 1)
        self.assertEqual(self.sent, [])
        self.refresher.assert_not_awaited()

    async def test_proven_prehandler_denial_returns_distinct_terminal_without_remote_end(self):
        self.remote()
        response = await self.settled_session()
        self.assertEqual(response.status, 502)
        self.assertEqual(response.content_type, 'application/json')
        error = (await response.json())['error']
        self.assertEqual(error['creationOutcome'], 'not_created')
        self.assertRegex(error['receiptId'], r'^[0-9a-f]{32}$')
        self.assertEqual(self.bridge.sessions, {})
        terminal = await self.ui.post('/api/end', json={}, headers=self.headers)
        self.assertEqual(terminal.status, 200)
        self.assertEqual(await terminal.json(), {'ended': False, 'localTerminal': True,
            'creationOutcome': 'not_created', 'cleanup': 'not_required',
            'receiptId': error['receiptId']})
        self.assertEqual(self.remote_posts, 1)
        self.assertEqual(self.sent, [])
        self.refresher.assert_not_awaited()
        self.assertEqual((await self.ui.get('/api/session')).status, 200)

    async def test_context_close_failure_cannot_settle_even_valid_denial(self):
        self.remote(close_failure=True)
        await self.settled_session()
        session = next(iter(self.bridge.sessions.values()))
        self.assertEqual(session.cleanup_state, 'unresolved')
        self.assertNotIn(session.sid, self.bridge.end_receipts)

    async def test_foreign_request_receipt_cannot_settle(self):
        self.remote(foreign=True)
        await self.settled_session()
        self.assertEqual(next(iter(self.bridge.sessions.values())).cleanup_state, 'unresolved')

    async def test_changed_caller_invalidates_even_genuine_remote_negative(self):
        def mutate():
            next(iter(self.bridge.sessions.values())).caller_email = 'changed@example.test'
        self.remote(mutate=mutate)
        await self.settled_session()
        self.assertEqual(next(iter(self.bridge.sessions.values())).cleanup_state, 'unresolved')

    async def test_changed_source_invalidates_genuine_remote_negative(self):
        def mutate():
            self.bridge.settings.inbound_id = 'changed-source'
        self.remote(mutate=mutate)
        await self.settled_session()
        self.assertEqual(next(iter(self.bridge.sessions.values())).cleanup_state, 'unresolved')

    async def test_changed_profile_invalidates_genuine_remote_negative(self):
        def mutate():
            next(iter(self.bridge.sessions.values())).voice_context['global_context_profile'] = 'e'*32
        self.remote(mutate=mutate)
        await self.settled_session()
        self.assertEqual(next(iter(self.bridge.sessions.values())).cleanup_state, 'unresolved')

    async def test_contradictory_created_binding_prevents_negative_settlement(self):
        def mutate():
            session = next(iter(self.bridge.sessions.values()))
            from voice.bridge import ConversationBinding
            session.conversation_binding = ConversationBinding(fixtures.CONTROL['conversationId'],
                fixtures.CONTROL['messageId'], session.caller_create_request_id, fixtures.CONTROL['interactionId'])
        self.remote(mutate=mutate)
        await self.settled_session()
        self.assertEqual(next(iter(self.bridge.sessions.values())).cleanup_state, 'unresolved')
        self.assertEqual(self.sent, [])

    async def test_wrong_csrf_cannot_consume_negative_tombstone(self):
        self.remote()
        response = await self.settled_session()
        self.assertEqual(response.status, 502)
        denied = await self.ui.post('/api/end', json={},
            headers={**self.headers, 'X-CSRF-Token': 'foreign'})
        self.assertEqual(denied.status, 403)
        self.assertEqual(len(self.bridge.end_receipts), 1)
