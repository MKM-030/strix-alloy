"""Real HTTP tests for narrow voice-route diagnostics before Gateway auth."""
import asyncio
from pathlib import Path
import re
import sys
import unittest

from aiohttp import web, WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import Backend, Gateway

KEY = 'fixture-voice-diagnostic-key-at-least-32-characters'
SECRET = 'DO-NOT-LOG-sensitive-value-voice-XYZ'
EXPECTED_ORIGIN = 'https://soprasteriaassvsdemo14.service-now.com'
SIGNAL = '/webrtc/connect/agent_operator'


class GatewayVoiceDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.inference_seen = []
        async def health(request): return web.json_response({'status':'ok'})
        async def chat(request):
            self.inference_seen.append(await request.json())
            return web.json_response({'ok':True})
        app = web.Application()
        app.router.add_get('/health', health)
        app.router.add_post('/v1/chat/completions', chat)
        self.upstream = TestServer(app)
        await self.upstream.start_server()
        self.gateway = Gateway(Backend('fixture', str(self.upstream.make_url('')).rstrip('/'),
            'fixture-upstream-model', expected={'status':'ok'}), KEY)
        self.client = TestClient(TestServer(self.gateway.app, access_log=None))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.upstream.close()

    def assert_diagnostics(self, output, *, route, method, origin, credentials, upgrade, status):
        starts = [line for line in output if 'Gateway voice HTTP request ' in line]
        ends = [line for line in output if 'Gateway voice HTTP result ' in line]
        self.assertEqual(len(starts), 1, 'voice request before Gateway authentication is invisible')
        self.assertEqual(len(ends), 1, 'voice request outcome is invisible')
        request_id = re.search(r'\brequest=([0-9a-f]{12})\b', starts[0])
        self.assertIsNotNone(request_id)
        self.assertIn('request=' + request_id.group(1), ends[0])
        for key, value in [('route',route), ('method',method), ('origin',origin),
                           ('credentials',credentials), ('upgrade',upgrade)]:
            self.assertIn(key + '=' + value, starts[0])
        self.assertIn('status=' + str(status), ends[0])
        joined = '\n'.join(output)
        for forbidden in (SECRET, KEY, SIGNAL, EXPECTED_ORIGIN, 'auth_token',
                          'Authorization', 'Bearer', 'x-api-key', '127.0.0.1'):
            self.assertNotIn(forbidden, joined)
        self.assertLess(len(starts[0]), 270)
        self.assertLess(len(ends[0]), 140)

    async def fetch(self, method, path, **kwargs):
        async with self.client.request(method, path, **kwargs) as response:
            return response.status, await response.text(), response.headers

    async def test_unknown_root_voice_get_is_logged_before_unchanged_401(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, body, _ = await self.fetch('GET', SIGNAL,
                params={'auth_token':SECRET, 'private_parameter':SECRET},
                headers={'Origin':EXPECTED_ORIGIN, 'Authorization':'Bearer ' + SECRET})
        self.assertEqual(status, 401)
        self.assertEqual(__import__('json').loads(body), {'error':{'message':'Unauthorized'}})
        self.assertEqual(self.inference_seen, [])
        self.assert_diagnostics(logs.output, route='root_signaling', method='GET', origin='expected',
                                credentials='both', upgrade='missing', status=401)

    async def test_native_prefixed_voice_get_has_a_distinct_route_class(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, _, _ = await self.fetch('GET', '/scc-native' + SIGNAL)
        self.assertEqual(status, 401)
        self.assert_diagnostics(logs.output, route='prefixed_signaling', method='GET', origin='missing',
                                credentials='none', upgrade='missing', status=401)

    async def test_child_path_is_classified_without_echoing_its_suffix(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, _, _ = await self.fetch('GET', SIGNAL + '/' + SECRET,
                params={'auth_token':SECRET}, headers={'Origin':'https://' + SECRET, 'Upgrade':SECRET})
        self.assertEqual(status, 401)
        self.assert_diagnostics(logs.output, route='root_signaling', method='GET', origin='other',
                                credentials='query', upgrade='other', status=401)

    async def test_root_websocket_401_is_classified_without_weakening_authentication(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            with self.assertRaises(WSServerHandshakeError) as denied:
                await self.client.ws_connect(SIGNAL, params={'auth_token':SECRET},
                    headers={'Origin':EXPECTED_ORIGIN})
        self.assertEqual(denied.exception.status, 401)
        self.assertEqual(self.inference_seen, [])
        self.assert_diagnostics(logs.output, route='root_signaling', method='GET', origin='expected',
                                credentials='query', upgrade='websocket', status=401)

    async def test_head_is_observed_and_original_empty_401_body_is_preserved(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, body, _ = await self.fetch('HEAD', SIGNAL, headers={'x-api-key':SECRET})
        self.assertEqual((status, body), (401, ''))
        self.assert_diagnostics(logs.output, route='root_signaling', method='HEAD', origin='missing',
                                credentials='header', upgrade='missing', status=401)

    async def test_authenticated_unknown_voice_route_keeps_original_404(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, body, _ = await self.fetch('GET', SIGNAL, headers={'Authorization':'Bearer ' + KEY})
        self.assertEqual((status, body), (404, '404: Not Found'))
        self.assert_diagnostics(logs.output, route='root_signaling', method='GET', origin='missing',
                                credentials='header', upgrade='missing', status=404)

    async def test_non_voice_and_near_prefix_requests_remain_quiet(self):
        with self.assertNoLogs('alloy.gateway', level='INFO'):
            for path in ['/health', '/v1/models', '/private-' + SECRET, SIGNAL + '_not-a-child']:
                status, _, _ = await self.fetch('GET', path, params={'auth_token':SECRET})
                self.assertEqual(status, 401)

    async def test_non_get_or_head_voice_requests_remain_quiet_and_unauthorized(self):
        with self.assertNoLogs('alloy.gateway', level='INFO'):
            for method in ['POST', 'OPTIONS', 'PUT']:
                status, _, _ = await self.fetch(method, SIGNAL, data=SECRET)
                self.assertEqual(status, 401)

    async def test_authenticated_health_retains_existing_response_without_diagnostics(self):
        with self.assertNoLogs('alloy.gateway', level='INFO'):
            status, body, _ = await self.fetch('GET', '/health', headers={'Authorization':'Bearer ' + KEY})
        self.assertEqual(status, 200)
        self.assertEqual(__import__('json').loads(body)['backend'], 'fixture')

    async def test_chat_payload_and_existing_inference_logging_are_unchanged(self):
        payload = {'model':'fixture', 'messages':[{'role':'user', 'content':SECRET}], 'stream':False}
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, body, _ = await self.fetch('POST', '/v1/chat/completions',
                headers={'Authorization':'Bearer ' + KEY}, json=payload)
        self.assertEqual(status, 200)
        self.assertEqual(__import__('json').loads(body), {'ok':True})
        self.assertEqual(self.inference_seen, [{**payload, 'model':'fixture-upstream-model'}])
        self.assertFalse(any('Gateway voice HTTP ' in line for line in logs.output))
        self.assertNotIn(SECRET, '\n'.join(logs.output))

    async def test_unhandled_handler_exception_is_preserved_without_message_logging(self):
        self.assertTrue(hasattr(self.gateway, 'diagnose_voice_route'), 'voice diagnostics middleware missing')
        request = make_mocked_request('GET', SIGNAL)
        failure = RuntimeError(SECRET)
        async def fail_handler(request): raise failure
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            with self.assertRaises(RuntimeError) as raised:
                await self.gateway.diagnose_voice_route(request, fail_handler)
        self.assertIs(raised.exception, failure)
        self.assert_diagnostics(logs.output, route='root_signaling', method='GET', origin='missing',
                                credentials='none', upgrade='missing', status=500)

    async def test_handler_cancellation_is_preserved_without_message_logging(self):
        self.assertTrue(hasattr(self.gateway, 'diagnose_voice_route'), 'voice diagnostics middleware missing')
        request = make_mocked_request('GET', SIGNAL)
        failure = asyncio.CancelledError(SECRET)
        async def cancel_handler(request): raise failure
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            with self.assertRaises(asyncio.CancelledError) as raised:
                await self.gateway.diagnose_voice_route(request, cancel_handler)
        self.assertIs(raised.exception, failure)
        self.assert_diagnostics(logs.output, route='root_signaling', method='GET', origin='missing',
                                credentials='none', upgrade='missing', status=0)


if __name__ == '__main__': unittest.main()
