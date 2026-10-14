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
SECRET = 'DO-NOT-LOG-sensitive-value-XYZ'
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
        for forbidden in (SECRET, KEY, SIGNAL, EXPECTED_ORIGIN, 'auth_token=',
                          'Authorization', 'Bearer', 'x-api-key', '127.0.0.1'):
            self.assertNotIn(forbidden, joined)
        self.assertLess(len(starts[0]), 500 if 'path_shape=' in starts[0] else 270)
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

    async def test_known_health_models_and_inference_routes_remain_quiet(self):
        with self.assertNoLogs('alloy.gateway', level='INFO'):
            for path in ['/health', '/v1/models', '/v1/chat/completions']:
                status, _, _ = await self.fetch('GET', path, params={'auth_token':SECRET})
                self.assertEqual(status, 401)

    async def test_post_options_and_other_method_voice_requests_are_visible_and_unauthorized(self):
        for method in ['POST', 'OPTIONS', 'PUT']:
            with self.assertLogs('alloy.gateway', level='INFO') as logs:
                status, body, _ = await self.fetch(method, SIGNAL, data=SECRET)
            self.assertEqual(status, 401)
            self.assertEqual(__import__('json').loads(body), {'error':{'message':'Unauthorized'}})
            self.assert_diagnostics(logs.output, route='root_signaling', method=method if method!='PUT' else 'OTHER',
                                    origin='missing', credentials='none', upgrade='missing', status=401)

    async def test_unknown_get_is_visible_without_echoing_any_bootstrap_path_or_query(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, body, _ = await self.fetch('GET', '/unknown-' + SECRET,
                params={'auth_token':SECRET}, headers={'Origin':EXPECTED_ORIGIN})
        self.assertEqual(status, 401)
        self.assertEqual(__import__('json').loads(body), {'error':{'message':'Unauthorized'}})
        self.assert_diagnostics(logs.output, route='other', method='GET', origin='expected',
                                credentials='query', upgrade='missing', status=401)

    async def test_unknown_post_is_visible_without_echoing_body_or_bootstrap_path(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, body, _ = await self.fetch('POST', '/unknown-' + SECRET, data=SECRET,
                headers={'Authorization':'Bearer ' + SECRET})
        self.assertEqual(status, 401)
        self.assertEqual(__import__('json').loads(body), {'error':{'message':'Unauthorized'}})
        self.assertEqual(self.inference_seen, [])
        self.assert_diagnostics(logs.output, route='other', method='POST', origin='missing',
                                credentials='header', upgrade='missing', status=401)

    async def test_other_webrtc_and_voice_bootstrap_paths_receive_only_fixed_route_classes(self):
        for path, route in [('/api/WebRTC/' + SECRET, 'webrtc_other'),
                            ('/api/Voice/' + SECRET, 'voice_other')]:
            with self.assertLogs('alloy.gateway', level='INFO') as logs:
                status, _, _ = await self.fetch('POST', path, data=SECRET)
            self.assertEqual(status, 401)
            self.assert_diagnostics(logs.output, route=route, method='POST', origin='missing',
                                    credentials='none', upgrade='missing', status=401)

    async def test_signaling_like_suffix_has_no_raw_path_in_diagnostics(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, _, _ = await self.fetch('GET', SIGNAL + '_not-a-child', params={'auth_token':SECRET})
        self.assertEqual(status, 401)
        self.assert_diagnostics(logs.output, route='webrtc_other', method='GET', origin='missing',
                                credentials='query', upgrade='missing', status=401)

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

    async def test_observed_webrtc_post_emits_only_allowlisted_static_auth_ticket_shape(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, _, _ = await self.fetch('POST', '/api/webrtc/auth/ticket',
                params={'auth_token':SECRET}, headers={'Authorization':'Bearer ' + SECRET}, data=SECRET)
        self.assertEqual(status, 401)
        self.assert_diagnostics(logs.output, route='webrtc_other', method='POST', origin='missing',
                                credentials='both', upgrade='missing', status=401)
        start = next(line for line in logs.output if 'Gateway voice HTTP request ' in line)
        self.assertIn('path_shape=api/webrtc/auth/ticket', start)
        self.assertIn('segments=4', start)

    async def test_private_names_identifiers_and_numbers_are_replaced_by_other(self):
        private = 'PRIVATE-PERSON-NAME'
        identifier = '12ab' * 8
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, _, _ = await self.fetch('POST', '/webrtc/auth_token/' + private + '/123/' + identifier,
                params={'private_parameter':SECRET}, data=SECRET)
        self.assertEqual(status, 401)
        self.assert_diagnostics(logs.output, route='webrtc_other', method='POST', origin='missing',
                                credentials='none', upgrade='missing', status=401)
        start = next(line for line in logs.output if 'Gateway voice HTTP request ' in line)
        self.assertIn('path_shape=webrtc/auth_token/other/other/other', start)
        self.assertIn('segments=5', start)
        self.assertNotIn(private, '\n'.join(logs.output))
        self.assertNotIn(identifier, '\n'.join(logs.output))
        self.assertNotIn('/123/', '\n'.join(logs.output))

    async def test_path_shape_has_eight_segment_limit_and_capped_segment_count(self):
        path = '/webrtc/' + '/'.join(['agent_operator_mobile'] * 110) + '/' + SECRET
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, _, _ = await self.fetch('POST', path)
        self.assertEqual(status, 401)
        self.assert_diagnostics(logs.output, route='webrtc_other', method='POST', origin='missing',
                                credentials='none', upgrade='missing', status=401)
        start = next(line for line in logs.output if 'Gateway voice HTTP request ' in line)
        shape = re.search(r'\bpath_shape=([a-z0-9_/-]+)\b', start)
        self.assertIsNotNone(shape)
        self.assertEqual(shape.group(1).split('/'), ['webrtc'] + ['agent_operator_mobile'] * 7)
        self.assertIn('segments=99', start)

    async def test_path_shape_is_added_only_to_observed_webrtc_other_post(self):
        for method, path in [('GET','/webrtc/auth/ticket'), ('OPTIONS','/webrtc/auth/ticket'),
                             ('POST','/api/voice/ticket'), ('POST',SIGNAL)]:
            with self.assertLogs('alloy.gateway', level='INFO') as logs:
                status, _, _ = await self.fetch(method, path)
            self.assertEqual(status, 401)
            self.assertNotIn('path_shape=', '\n'.join(logs.output))
            self.assertNotIn('header_kind=', '\n'.join(logs.output))
            self.assertNotIn('auth_shape=', '\n'.join(logs.output))

    async def test_header_kind_and_auth_shape_are_fixed_presence_and_syntax_enums(self):
        jwt = 'PRIVATE_JWT_HEADER.PRIVATE_JWT_PAYLOAD.PRIVATE_JWT_SIGNATURE'
        cases = [({}, 'none', 'missing'),
                 ({'Authorization':'Bearer ' + jwt}, 'authorization', 'bearer_jwt'),
                 ({'Authorization':'Bearer ' + SECRET}, 'authorization', 'bearer_other'),
                 ({'Authorization':'Basic ' + SECRET}, 'authorization', 'non_bearer'),
                 ({'x-api-key':SECRET}, 'api_key', 'missing'),
                 ({'Authorization':'Bearer ' + jwt, 'x-api-key':SECRET}, 'both', 'bearer_jwt')]
        for headers, kind, shape in cases:
            with self.assertLogs('alloy.gateway', level='INFO') as logs:
                status, body, _ = await self.fetch('POST', '/api/webrtc/auth/ticket',
                    headers=headers, params={'auth_token':SECRET}, data=SECRET)
            self.assertEqual(status, 401)
            self.assertEqual(__import__('json').loads(body), {'error':{'message':'Unauthorized'}})
            start = next(line for line in logs.output if 'Gateway voice HTTP request ' in line)
            self.assertIn('header_kind=' + kind, start)
            self.assertIn('auth_shape=' + shape, start)
            self.assertNotIn(jwt, '\n'.join(logs.output))
            for value in jwt.split('.'): self.assertNotIn(value, '\n'.join(logs.output))
            self.assert_diagnostics(logs.output, route='webrtc_other', method='POST', origin='missing',
                credentials='query' if not headers else 'both', upgrade='missing', status=401)

    async def test_bearer_shape_does_not_decode_claims_or_accept_malformed_jwt_syntax(self):
        for value in ['a..c', '.b.c', 'a.b.', 'a.b.c.d', 'a.b.c!', 'a.b.c/private', SECRET]:
            with self.assertLogs('alloy.gateway', level='INFO') as logs:
                status, _, _ = await self.fetch('POST', '/webrtc/auth/ticket',
                    headers={'Authorization':'Bearer ' + value})
            self.assertEqual(status, 401)
            self.assertTrue(any('auth_shape=bearer_other' in line for line in logs.output))
            self.assertNotIn('auth_shape=bearer_jwt', '\n'.join(logs.output))

    async def test_valid_gateway_key_still_has_unchanged_unknown_post_404(self):
        with self.assertLogs('alloy.gateway', level='INFO') as logs:
            status, body, _ = await self.fetch('POST', '/api/webrtc/auth/ticket',
                headers={'Authorization':'Bearer ' + KEY})
        self.assertEqual((status, body), (404, '404: Not Found'))
        self.assertTrue(any('header_kind=authorization auth_shape=bearer_other' in line for line in logs.output))
        self.assertEqual(self.inference_seen, [])

    async def test_static_sdk_token_and_ice_names_are_normalized_without_echoing_unknown_segments(self):
        for operation in ['jwt','jwt_token','get_jwt','get_token','generate_token','create_token',
                          'agent_operator_token','get_auth_token','create_session','start_session',
                          'ice_servers','get_ice_servers','get_jwt_token','offer','answer','create_room',
                          'config','configuration','settings','service','services','bootstrap','handshake',
                          'call','calls','init','initialize','capabilities','status','health']:
            with self.assertLogs('alloy.gateway', level='INFO') as logs:
                status, _, _ = await self.fetch('POST', '/webrtc/' + operation.upper() + '/' + SECRET)
            self.assertEqual(status, 401)
            self.assert_diagnostics(logs.output, route='webrtc_other', method='POST', origin='missing',
                                    credentials='none', upgrade='missing', status=401)
            self.assertTrue(any('path_shape=webrtc/' + operation + '/other' in line for line in logs.output))


if __name__ == '__main__': unittest.main()
