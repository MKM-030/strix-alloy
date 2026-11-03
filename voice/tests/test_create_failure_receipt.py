"""Synthetic fixed-endpoint failure receipts; no real network or credentials."""
import dataclasses
import json
import unittest
from voice import caller_binding as authority
from voice.tests import test_create_diagnostics as diagnostic_fixtures
from voice.tests import test_local_caller_create as fixtures


CONTRACT = 'scc_local_caller_create_v1'
PRIVATE = diagnostic_fixtures.PRIVATE


def denial():
    return {'result': {'status': 'failure', 'failure': {
        'contract': CONTRACT, 'version': 1, 'outcome': 'not_created',
        'reason': 'access_denied', 'requestId': '1'*32, 'clientSessionId': '2'*32,
        'clientMessageId': '3'*32, 'serviceId': authority.CALLER_SERVICE_ID,
        'contextProfile': authority.CALLER_PROFILE_ID}}}


class CreateFailureReceiptTests(unittest.IsolatedAsyncioTestCase):
    factory = diagnostic_fixtures.CreateDiagnostics.factory
    invoke = diagnostic_fixtures.CreateDiagnostics.invoke

    async def failure(self, *, status=401, point='', raw=None, headers=None, **extra):
        factory = self.factory(status=status, point=point, raw=raw, headers=headers)
        with self.assertLogs('voice-bridge', 'WARNING') as capture:
            try:
                await self.invoke(factory, **extra)
            except ValueError as error:
                self.assertEqual(type(error).__name__, 'CallerCreateFailure')
                self.assertEqual(str(error), 'Native caller CREATE unavailable')
                receipt = error.receipt
            else:
                self.fail('CREATE failure was accepted')
        self.assertLessEqual(len(self.calls), 1)
        if self.request_headers is not None:
            self.assertEqual(self.request_headers, {})
        self.assertEqual(len(capture.records), 1)
        self.assertNotIn(PRIVATE, repr(capture.records[0].__dict__))
        self.assertNotIn(PRIVATE, repr(receipt))
        return receipt

    def assert_correlated(self, receipt):
        self.assertEqual((receipt.request_id, receipt.client_session_id, receipt.client_message_id),
                         ('1'*32, '2'*32, '3'*32))
        for value in fixtures.REQUEST.values():
            if isinstance(value, str): self.assertNotIn(value, repr(receipt))

    async def test_received_401_is_typed_but_never_proves_noncreation_or_reads_body(self):
        receipt = await self.failure(status=401, point='read')
        self.assertEqual(receipt.reason, 'caller_create_unauthorized')
        self.assertEqual(receipt.outcome, 'unknown')
        self.assertEqual(receipt.contract, '')
        self.assertEqual(receipt.http_status, 401)
        self.assertEqual(receipt.dispatch_state, 'response_received')
        self.assertTrue(receipt.close_completed)
        self.assert_correlated(receipt)

    async def test_exact_pre_handler_403_receipt_after_normal_closes_proves_noncreation(self):
        receipt = await self.failure(status=403, raw=json.dumps(denial()).encode())
        self.assertEqual(receipt.reason, 'caller_create_access_denied')
        self.assertEqual(receipt.outcome, 'not_created')
        self.assertEqual(receipt.contract, CONTRACT)
        self.assertEqual(receipt.http_status, 403)
        self.assertTrue(receipt.close_completed)
        self.assert_correlated(receipt)

    async def test_generic_403_is_not_a_negative_creation_receipt(self):
        receipt = await self.failure(status=403, raw=b'{"error":"denied"}')
        self.assertEqual(receipt.reason, 'caller_create_access_denied')
        self.assertEqual(receipt.outcome, 'unknown')
        self.assertEqual(receipt.contract, '')
        self.assertTrue(receipt.close_completed)

    async def test_foreign_inexact_or_malformed_403_receipts_remain_unknown(self):
        cases = []
        for key, value in (
            ('contract', 'foreign'), ('version', True), ('outcome', 'created'),
            ('reason', 'expired'), ('requestId', 'f'*32), ('clientSessionId', 'f'*32),
            ('clientMessageId', 'f'*32), ('serviceId', 'f'*32), ('contextProfile', 'f'*32),
            ('extra', PRIVATE)):
            value_body = denial()
            value_body['result']['failure'][key] = value
            cases.append(json.dumps(value_body).encode())
        for key in denial()['result']['failure']:
            value_body = denial()
            del value_body['result']['failure'][key]
            cases.append(json.dumps(value_body).encode())
        body = denial(); body['result']['extra'] = PRIVATE
        cases.extend((json.dumps(body).encode(), b'{"result":{},"result":{}}', b'\xff',
                      b'{"x":NaN}', b'not json', b' '*4097))
        for raw in cases:
            with self.subTest(raw=raw[:50]):
                receipt = await self.failure(status=403, raw=raw)
                self.assertEqual(receipt.outcome, 'unknown')
                self.assertEqual(receipt.contract, '')

    async def test_encoding_or_content_type_cannot_supply_a_negative_receipt(self):
        for headers in ({'Content-Type': 'text/plain'},
                        {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}):
            with self.subTest(headers=headers):
                receipt = await self.failure(status=403, headers=headers,
                    raw=json.dumps(denial()).encode())
                self.assertEqual(receipt.outcome, 'unknown')

    async def test_native_401_wrapped_in_503_never_becomes_negative_receipt(self):
        receipt = await self.failure(status=503, point='read', raw=json.dumps(denial()).encode())
        self.assertEqual(receipt.reason, 'caller_create_unavailable')
        self.assertEqual(receipt.outcome, 'unknown')

    async def test_response_or_client_close_failure_invalidates_403_proof(self):
        for point in ('response_exit', 'session_exit'):
            with self.subTest(point=point):
                receipt = await self.failure(status=403, point=point,
                    raw=json.dumps(denial()).encode())
                self.assertEqual(receipt.outcome, 'unknown')
                self.assertEqual(receipt.contract, '')
                self.assertFalse(receipt.close_completed)
                self.assertEqual(receipt.stage, 'transport_close')

    async def test_close_failure_does_not_erase_received_401_reason(self):
        for point in ('response_exit', 'session_exit'):
            with self.subTest(point=point):
                receipt = await self.failure(status=401, point=point)
                self.assertEqual(receipt.reason, 'caller_create_unauthorized')
                self.assertEqual(receipt.outcome, 'unknown')
                self.assertFalse(receipt.close_completed)

    async def test_exact_correlated_no_dispatch_failure_can_settle_without_http(self):
        receipt = await self.failure(instance_url='https://foreign.invalid')
        self.assertEqual(self.calls, [])
        self.assertEqual(receipt.outcome, 'not_created')
        self.assertEqual(receipt.contract, CONTRACT)
        self.assertEqual(receipt.dispatch_state, 'not_dispatched')
        self.assertEqual(receipt.http_status, 0)
        self.assertFalse(receipt.close_completed)
        self.assert_correlated(receipt)
        for point in ('factory', 'session_enter'):
            with self.subTest(point=point):
                receipt = await self.failure(point=point)
                self.assertEqual(self.calls, [])
                self.assertEqual(receipt.outcome, 'not_created')
                self.assertEqual(receipt.dispatch_state, 'not_dispatched')

    async def test_malformed_correlation_never_creates_a_settleable_receipt(self):
        for request in ({}, dict(fixtures.REQUEST, requestId=PRIVATE),
                        dict(fixtures.REQUEST, clientMessageId='1'*32)):
            with self.subTest(request=request):
                receipt = await self.failure(request=request)
                self.assertEqual(self.calls, [])
                self.assertEqual(receipt.outcome, 'unknown')
                self.assertEqual(receipt.contract, '')

    async def test_possible_dispatch_or_response_entry_failure_remains_unknown(self):
        for point in ('post', 'response_enter'):
            with self.subTest(point=point):
                receipt = await self.failure(point=point)
                self.assertEqual(receipt.outcome, 'unknown')
                self.assertEqual(receipt.dispatch_state, 'may_have_dispatched')
                self.assertFalse(receipt.close_completed)

    async def test_immutable_receipt_cannot_be_relabelled_after_transport(self):
        receipt = await self.failure()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            receipt.outcome = 'not_created'

    async def test_receipt_rejects_foreign_fields_and_401_noncreation_relabelling(self):
        receipt = await self.failure()
        for changes in (
            {'stage': PRIVATE}, {'reason': PRIVATE}, {'dispatch_state': PRIVATE},
            {'http_status': True}, {'close_completed': 1}, {'request_id': PRIVATE},
            {'contract': PRIVATE}, {'contract': CONTRACT},
            {'outcome': 'not_created', 'contract': CONTRACT}):
            with self.subTest(fields=tuple(changes)):
                with self.assertRaisesRegex(ValueError, '^Invalid caller CREATE failure receipt$'):
                    dataclasses.replace(receipt, **changes)

