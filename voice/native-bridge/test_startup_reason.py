"""Pure offline diagnostics tests. No native runtime imports or service/model calls."""
import asyncio
import unittest

from startup_reason import NativeStartupError, open_with_startup_diagnostics, startup_reason


class ClassificationTests(unittest.TestCase):
    def test_existing_startup_throw_branches_have_distinct_stable_codes(self):
        cases = {
            'Configured initial topic is not offered by ServiceNow': 'servicenow_initial_topic_not_offered',
            'Configured initial topic did not reach its input control': 'servicenow_initial_topic_input_not_reached',
            'ServiceNow conversation startup timed out': 'servicenow_startup_deadline',
            'ServiceNow greeting failed': 'servicenow_startup_callback_failed',
            'ServiceNow conversation is not ready': 'servicenow_startup_not_ready',
            'ServiceNow conversation is disabled': 'servicenow_disabled',
            'ServiceNow conversation bridge unavailable': 'servicenow_bridge_unavailable',
            'ServiceNow conversation binding changed': 'servicenow_conversation_binding_changed',
        }
        for message, expected in cases.items():
            with self.subTest(expected):
                self.assertEqual(startup_reason(RuntimeError(message)), expected)

    def test_timeout_is_distinct_from_whole_startup_deadline_and_keeps_secrets_private(self):
        self.assertEqual(startup_reason(TimeoutError('https://secret.example/?token=SECRET')),
                         'servicenow_transport_deadline')

    def test_security_words_and_untrusted_messages_never_prove_access_denial(self):
        for text in ('AccessDenied', 'ACCESS DENIED', 'Zugriff verweigert', 'failureReason=acl',
                     'ServiceNow greeting failed: AccessDenied', 'servicenow_access_denied'):
            with self.subTest(text):
                self.assertEqual(startup_reason(RuntimeError(text)), 'servicenow_startup_failed')

    def test_typed_future_structural_reason_is_allowed_without_payload(self):
        self.assertEqual(startup_reason(NativeStartupError('servicenow_access_denied')),
                         'servicenow_access_denied')
        for value in ('secret-token', {}, None):
            with self.assertRaisesRegex(ValueError, '^Unknown native startup reason$'):
                NativeStartupError(value)

    def test_explicit_cause_can_recover_known_reason_without_rendering_errors(self):
        class Unrenderable(RuntimeError):
            def __str__(self):
                raise AssertionError('Never render an arbitrary exception')
        wrapper = Unrenderable('private-payload')
        wrapper.__cause__ = NativeStartupError('servicenow_access_denied')
        self.assertEqual(startup_reason(wrapper), 'servicenow_access_denied')

    def test_implicit_context_does_not_relabel_an_unrelated_failure(self):
        error = RuntimeError('unknown')
        error.__context__ = NativeStartupError('servicenow_access_denied')
        self.assertEqual(startup_reason(error), 'servicenow_startup_failed')

    def test_bounded_cyclic_causes_and_multi_argument_errors_remain_generic(self):
        first, second = RuntimeError('unknown'), ValueError('unknown')
        first.__cause__, second.__cause__ = second, first
        self.assertEqual(startup_reason(first), 'servicenow_startup_failed')
        self.assertEqual(startup_reason(RuntimeError('AccessDenied', 'private')), 'servicenow_startup_failed')

    def test_cancelled_startup_has_its_own_code(self):
        self.assertEqual(startup_reason(asyncio.CancelledError()), 'servicenow_startup_cancelled')


class CapturingLogger:
    def __init__(self):
        self.messages = []

    def warning(self, fmt, *args):
        self.messages.append(fmt % args)


class PropagationTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_returns_exact_result_from_exactly_one_open(self):
        result, calls, logger = ['owned result'], [], CapturingLogger()
        class Dialog:
            async def open(self):
                calls.append('open')
                return result
        self.assertIs(await open_with_startup_diagnostics(Dialog(), logger, 'call-fixture'), result)
        self.assertEqual(calls, ['open'])
        self.assertEqual(logger.messages, [])

    async def test_failure_keeps_exception_identity_explicit_cause_and_one_invocation(self):
        cause = TimeoutError('Bearer SECRET; transcript PRIVATE')
        error = RuntimeError('opaque transport wrapper')
        error.__cause__ = cause
        calls, logger = [], CapturingLogger()
        class Dialog:
            async def open(self):
                calls.append('open')
                raise error
        with self.assertRaises(RuntimeError) as raised:
            await open_with_startup_diagnostics(Dialog(), logger, 'call-fixture')
        self.assertIs(raised.exception, error)
        self.assertIs(raised.exception.__cause__, cause)
        self.assertEqual(calls, ['open'])
        self.assertEqual(len(logger.messages), 1)
        self.assertIn('reason=servicenow_transport_deadline', logger.messages[0])
        self.assertNotIn('SECRET', logger.messages[0])
        self.assertNotIn('PRIVATE', logger.messages[0])
        self.assertNotIn('opaque transport wrapper', logger.messages[0])

    async def test_diagnostic_handler_failure_cannot_mask_original_error(self):
        error = NativeStartupError('servicenow_initial_topic_not_offered')
        class Dialog:
            async def open(self):
                raise error
        class BrokenLogger:
            def warning(self, *args):
                raise RuntimeError('handler failed')
        with self.assertRaises(NativeStartupError) as raised:
            await open_with_startup_diagnostics(Dialog(), BrokenLogger(), 'call-fixture')
        self.assertIs(raised.exception, error)

    async def test_cancellation_propagates_and_does_not_emit_failure_or_retry(self):
        error, calls, logger = asyncio.CancelledError(), [], CapturingLogger()
        class Dialog:
            async def open(self):
                calls.append('open')
                raise error
        with self.assertRaises(asyncio.CancelledError) as raised:
            await open_with_startup_diagnostics(Dialog(), logger, 'call-fixture')
        self.assertIs(raised.exception, error)
        self.assertEqual(calls, ['open'])
        self.assertEqual(logger.messages, [])


if __name__ == '__main__':
    unittest.main()
