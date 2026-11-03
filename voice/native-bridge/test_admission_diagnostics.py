"""Fixed admission-stage diagnostics against synthetic transports only."""
import asyncio
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import aiohttp
import caller_create_preflight as preflight
import native_bridge
import sdk_admission
import sdk_sessions
import test_caller_create_preflight as f


class AdmissionDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, transport, metadata, probe=None):
        if transport == 'sdk':
            clients = [metadata] + ([probe] if probe is not None else [])
            with self.assertRaises(sdk_admission.AdmissionDenied) as caught:
                await f.admit(f.Factory(*clients))
            return caught.exception.status
        request, config = f.EntryPreflightTests.wss(self)
        with patch.object(aiohttp, 'ClientSession', f.Factory(*([probe] if probe is not None else []))):
            self.assertIs(await native_bridge.authorize(request, config, metadata, with_settings=True), False)
        return 401

    def event(self, logs, transport, stage, outcome, public, upstream):
        messages = [r.getMessage() for r in logs.records if r.getMessage().startswith('Voice admission ')]
        self.assertEqual(len(messages), 1, messages)
        expected = (f'Voice admission transport={transport} stage={stage} outcome={outcome} '
                    f'public_status={public} upstream_status={upstream} elapsed_ms=')
        self.assertTrue(messages[0].startswith(expected), messages[0])
        self.assertRegex(messages[0], r'elapsed_ms=[0-9]+$')
        self.assertLessEqual(int(messages[0].rsplit('=', 1)[1]), 10000)
        for forbidden in (f.AUTHORIZATION, f.INSTANCE, f.SERVICE, f.PROFILE, f.AGENT,
                          'private-body', 'synthetic private', 'Traceback', 'https://'):
            self.assertNotIn(forbidden, '\n'.join(r.getMessage() for r in logs.records))

    async def test_metadata_http_denial_is_distinct_for_both_entrypoints(self):
        for transport in ('sdk', 'wss'):
            for upstream in (401, 403):
                with self.subTest(transport=transport, upstream=upstream):
                    metadata = f.Client(f.AUTH_URL, f.Response(upstream, {'private-body': f.AUTHORIZATION}))
                    public = 401 if transport == 'wss' or upstream == 401 else 403
                    with self.assertLogs('native-voice', level='WARNING') as logs:
                        self.assertEqual(await self.invoke(transport, metadata), public)
                    self.event(logs, transport, 'metadata_http', 'http_denied', public, upstream)

    async def test_after_metadata_200_preflight_401_is_identified_without_payload(self):
        for transport in ('sdk', 'wss'):
            metadata = f.Client(f.AUTH_URL, f.Response(200, f.settings_response()))
            probe = f.Client(f.CREATE_URL, f.Response(401, {'private-body': f.AUTHORIZATION}))
            with self.subTest(transport=transport), self.assertLogs('native-voice', level='WARNING') as logs:
                self.assertEqual(await self.invoke(transport, metadata, probe), 401)
            self.event(logs, transport, 'caller_preflight_http', 'http_denied', 401, 401)
            self.assertEqual((len(metadata.calls), len(probe.calls)), (1, 1))

    async def test_settings_group_preserves_sdk_403_and_wss_401(self):
        for transport in ('sdk', 'wss'):
            for body in ({'result': []}, f.settings_response(profile='invalid')):
                metadata = f.Client(f.AUTH_URL, f.Response(200, body))
                with self.subTest(transport=transport), self.assertLogs('native-voice', level='WARNING') as logs:
                    public = await self.invoke(transport, metadata)
                self.assertEqual(public, 403 if transport == 'sdk' else 401)
                self.event(logs, transport, 'settings', 'invalid', public, 200)

    async def test_malformed_metadata_json_is_a_body_failure(self):
        for transport in ('sdk', 'wss'):
            metadata = f.Client(f.AUTH_URL, f.Response(200, raw=b'{private-body'))
            with self.subTest(transport=transport), self.assertLogs('native-voice', level='WARNING') as logs:
                public = await self.invoke(transport, metadata)
            self.event(logs, transport, 'metadata_body', 'invalid', public, 200)

    async def test_invalid_preflight_400_and_context_exit_failure_are_distinct(self):
        for transport in ('sdk', 'wss'):
            for response, stage, outcome in (
                    (f.Response(400, {'private-body': f.AUTHORIZATION}), 'caller_preflight_body', 'invalid'),
                    (f.Response(400, f.MALFORMED_DENIAL, exit_error=True), 'caller_preflight_close', 'transport')):
                metadata = f.Client(f.AUTH_URL, f.Response(200, f.settings_response()))
                probe = f.Client(f.CREATE_URL, response)
                with self.subTest(transport=transport, stage=stage), self.assertLogs('native-voice', level='WARNING') as logs:
                    public = await self.invoke(transport, metadata, probe)
                self.event(logs, transport, stage, outcome, public, 400)

    async def test_metadata_context_exit_failure_cannot_be_reported_as_settings_success(self):
        for transport in ('sdk', 'wss'):
            metadata = f.Client(f.AUTH_URL, f.Response(200, f.settings_response(), exit_error=True))
            with self.subTest(transport=transport), self.assertLogs('native-voice', level='WARNING') as logs:
                public = await self.invoke(transport, metadata)
            self.event(logs, transport, 'metadata_close', 'transport', public, 200)

    async def test_metadata_http_denial_is_final_only_after_contexts_close(self):
        for transport in ('sdk', 'wss'):
            metadata = f.Client(f.AUTH_URL, f.Response(401, {}, exit_error=True))
            with self.subTest(transport=transport), self.assertLogs('native-voice', level='WARNING') as logs:
                public = await self.invoke(transport, metadata)
            self.assertEqual(public, 403 if transport == 'sdk' else 401)
            self.event(logs, transport, 'metadata_close', 'transport', public, 401)

    async def test_timeout_remains_denied_and_has_only_a_fixed_reason(self):
        for transport in ('sdk', 'wss'):
            metadata = f.Client(f.AUTH_URL, f.Response(200, f.settings_response(), enter_delay=0.08))
            module = sdk_admission if transport == 'sdk' else native_bridge
            with self.subTest(transport=transport), patch.object(module, 'AUTHORIZATION_TIMEOUT_SECONDS', 0.01):
                with self.assertLogs('native-voice', level='WARNING') as logs:
                    public = await asyncio.wait_for(self.invoke(transport, metadata), 0.3)
                self.event(logs, transport, 'metadata_http', 'timeout', public, 0)

    async def test_external_cancellation_is_logged_and_still_propagates(self):
        for transport in ('sdk', 'wss'):
            metadata = f.Client(f.AUTH_URL, f.Response(200, f.settings_response()))
            response = f.Response(400, f.MALFORMED_DENIAL)
            response.content.gate = asyncio.Event()
            probe = f.Client(f.CREATE_URL, response)
            async def operation():
                if transport == 'sdk':
                    await f.admit(f.Factory(metadata, probe))
                else:
                    request, config = f.EntryPreflightTests.wss(self)
                    with patch.object(aiohttp, 'ClientSession', f.Factory(probe)):
                        await native_bridge.authorize(request, config, metadata, with_settings=True)
            with self.subTest(transport=transport), self.assertLogs('native-voice', level='WARNING') as logs:
                pending = asyncio.create_task(operation())
                await asyncio.wait_for(response.content.started.wait(), 0.3)
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
            self.event(logs, transport, 'caller_preflight', 'cancelled', 0, 0)

    async def test_sdk_manager_local_header_rejection_is_observed_before_admit(self):
        def forbidden(*args, **kwargs):
            self.fail('No authority or allocation belongs after malformed local headers')
        manager = sdk_sessions.SDKSessionManager(SimpleNamespace(), set(), forbidden, forbidden)
        manager._enabled = lambda: True
        request = SimpleNamespace(raw_headers=[(b'Content-Type', b'application/json')])
        with self.assertLogs('native-voice', level='WARNING') as logs:
            with self.assertRaises(sdk_sessions._Rejected) as caught:
                await manager.create(request)
        self.assertEqual(caught.exception.status, 401)
        self.event(logs, 'sdk', 'local_request', 'denied', 401, 0)

    async def test_closed_valid_preflight_and_alternate_profile_keep_existing_success(self):
        for profile in (f.PROFILE, '1' * 32):
            metadata = f.Client(f.AUTH_URL, f.Response(200, f.settings_response(profile=profile)))
            clients = [metadata] + ([f.Client(f.CREATE_URL, f.Response(400, f.MALFORMED_DENIAL))]
                                    if profile == f.PROFILE else [])
            with self.assertNoLogs('native-voice', level='WARNING'):
                result = await f.admit(f.Factory(*clients))
            self.assertEqual(result.call_settings.context_profile, profile)


class DiagnosticSanitizationTests(unittest.TestCase):
    def test_untrusted_values_never_enter_diagnostic_fields(self):
        with self.assertLogs('native-voice', level='WARNING') as logs:
            preflight.log_admission_failure('private-body', {'token': f.AUTHORIZATION}, object(),
                                            999, -1, object())
        self.assertEqual(logs.records[0].getMessage(),
            'Voice admission transport=unknown stage=unknown outcome=unknown public_status=0 upstream_status=0 elapsed_ms=0')

    def test_clock_clamp_and_failing_diagnostic_handler_do_not_escape(self):
        with patch.object(preflight.time, 'monotonic', return_value=1000000):
            with self.assertLogs('native-voice', level='WARNING') as logs:
                preflight.log_admission_failure('sdk', 'settings', 'invalid', 403, 200, 1.0)
        self.assertTrue(logs.records[0].getMessage().endswith('elapsed_ms=10000'))
        with patch.object(preflight.LOG, 'warning', side_effect=RuntimeError('private-body')):
            preflight.log_admission_failure('sdk', 'settings', 'invalid', 403, 200, 1.0)


if __name__ == '__main__':
    unittest.main()
