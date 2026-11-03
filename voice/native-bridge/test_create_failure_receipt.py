"""Trusted loopback error/terminal protocol; no remote auth or model requests."""
import json
import unittest
from native_bridge import Config, Dialog
from startup_reason import NativeStartupError, startup_reason


class CreateFailureReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dialog = Dialog(Config())
        self.dialog.bind_caller_authorization('Bearer synthetic.original')
        self.dialog.csrf = 'same-private-session'
        self.addAsyncCleanup(self.dialog.shutdown)
        self.response = {'error': {'source': 'scc_local_caller_create_v1', 'version': 1,
            'reason': 'caller_create_unauthorized', 'creationOutcome': 'unknown', 'receiptId': ''}}
        self.status = 502
        self.close_failure = False
        owner = self
        class Response:
            headers = {'Content-Type': 'application/json'}
            def __init__(self):
                self.status = owner.status
                self.content = self
            async def __aenter__(self): return self
            async def __aexit__(self, *args):
                if owner.close_failure: raise RuntimeError('synthetic private close failure')
            async def json(self): return owner.response
            async def iter_chunked(self, size):
                yield owner.response if type(owner.response) is bytes else json.dumps(owner.response).encode()
        class HTTP:
            def request(self, *args, **kwargs): return Response()
            async def close(self): pass
        self.dialog.http = HTTP()

    async def start_failure(self):
        try:
            await self.dialog.request('POST', '/api/start',
                caller_authorization='Bearer synthetic.original', json={})
        except RuntimeError as error:
            return error
        self.fail('A rejected CREATE must remain a startup failure')

    async def test_closed502_structural401_reason_survives_without_auth_retry(self):
        error = await self.start_failure()
        self.assertEqual(startup_reason(error), 'servicenow_caller_create_unauthorized')
        self.assertIsInstance(error, NativeStartupError)

    async def test_proven_no_create_terminal_requires_same_initial_receipt(self):
        self.response['error'].update(reason='caller_create_access_denied',
            creationOutcome='not_created', receiptId='a'*32)
        await self.start_failure()
        self.response = {'ended': False, 'localTerminal': True, 'creationOutcome': 'not_created',
            'cleanup': 'not_required', 'receiptId': 'a'*32}
        self.status = 200
        self.dialog.must_reset = True
        await self.dialog.reset_owned_session()
        self.assertFalse(self.dialog.must_reset)
        self.assertEqual(self.dialog.csrf, '')
        self.assertFalse(self.dialog.conversation_ended)

    async def test_foreign_or_unbound_terminal_cannot_release_cookie(self):
        for nonce in ('', 'b'*32):
            self.response = {'ended': False, 'localTerminal': True, 'creationOutcome': 'not_created',
                'cleanup': 'not_required', 'receiptId': nonce}
            self.status = 200
            self.dialog.must_reset = True
            with self.assertRaisesRegex(RuntimeError, 'not acknowledged'):
                await self.dialog.reset_owned_session()
            self.assertTrue(self.dialog.must_reset)
            self.assertEqual(self.dialog.csrf, 'same-private-session')

    async def test_mismatched_terminal_after_genuine_initial_receipt_stays_retained(self):
        self.response['error'].update(reason='caller_create_access_denied',
            creationOutcome='not_created', receiptId='a'*32)
        await self.start_failure()
        self.response = {'ended': False, 'localTerminal': True, 'creationOutcome': 'not_created',
            'cleanup': 'not_required', 'receiptId': 'b'*32}
        self.status = 200
        self.dialog.must_reset = True
        with self.assertRaisesRegex(RuntimeError, 'not acknowledged'):
            await self.dialog.reset_owned_session()
        self.assertTrue(self.dialog.must_reset)
        self.assertEqual(self.dialog.csrf, 'same-private-session')

    async def test_loopback_context_close_failure_cannot_bind_negative_nonce(self):
        self.response['error'].update(reason='caller_create_access_denied',
            creationOutcome='not_created', receiptId='a'*32)
        self.close_failure = True
        error = await self.start_failure()
        self.assertNotEqual(startup_reason(error), 'servicenow_caller_create_access_denied')
        self.assertEqual(self.dialog._create_failure_receipt_id, '')

    async def test_arbitrary_error_body_cannot_assert_auth_reason(self):
        for body in ({'error': 'caller_create_unauthorized PRIVATE'},
                     {'error': {**self.response['error'], 'version': True}},
                     {'error': {**self.response['error'], 'receiptId': 'foreign'}},
                     {'error': {**self.response['error'], 'extra': 'PRIVATE'}},
                     b'{' + b'x'*5000):
            self.response = body
            error = await self.start_failure()
            self.assertEqual(startup_reason(error), 'servicenow_bridge_unavailable')
            self.assertNotIn('PRIVATE', repr(error))

    async def test_wrong_method_or_path_does_not_parse_startup_receipt(self):
        with self.assertRaises(RuntimeError) as raised:
            await self.dialog.request('POST', '/api/end', json={})
        self.assertEqual(startup_reason(raised.exception), 'servicenow_bridge_unavailable')
