"""Real HTTP routing checks for bounded Native request diagnostics.

Only authorize/create_app are loaded from their actual source, so these tests
require aiohttp but do not allocate RTC sessions, run speech, or call ServiceNow.
"""
import ast
import asyncio
import json
import logging
from pathlib import Path
import re
import types
import unittest
import uuid

from aiohttp import ClientSession, ClientTimeout, WSServerHandshakeError, web
from aiohttp.test_utils import make_mocked_request


ROOT = Path(__file__).parent
source = ast.parse((ROOT / 'native_bridge.py').read_text())
selected = [node for node in source.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {'authorize', 'create_app'}]
namespace = dict(asyncio=asyncio, uuid=uuid, json=json, Path=Path,
    LOG=logging.getLogger('native-voice'), ClientSession=ClientSession,
    ClientTimeout=ClientTimeout, web=web, HTTP_KEY=web.AppKey('http', ClientSession))
exec(compile(ast.Module(body=selected, type_ignores=[]), '<actual-native-source>', 'exec'), namespace)
create_app = namespace['create_app']
SIGNAL_PATH = '/webrtc/connect/agent_operator'
SECRET = 'DO-NOT-LOG-this-sensitive-value-XYZ'


def configuration():
    return types.SimpleNamespace(instance_name='unit-test', voice_service_id='unit-service',
        instance_url='https://unit-test.service-now.com', development_token='',
        auth_mode='deny', max_call_seconds=30)


class RequestDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = configuration()
        self.app = create_app(self.config, dialog_factory=lambda:object())
        self.pending_entered = asyncio.Event()
        self.pending_release = asyncio.Event()
        async def pending_handler(request):
            self.pending_entered.set()
            await self.pending_release.wait()
            return web.Response(text=SECRET)
        self.app.router.add_get('/pending', pending_handler)
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.base = f'http://127.0.0.1:{port}'
        self.http = ClientSession()

    async def asyncTearDown(self):
        self.pending_release.set()
        await self.http.close()
        await self.runner.cleanup()

    def assert_diagnostics(self, output, *, route, method, origin, credentials, upgrade, status):
        starts = [line for line in output if 'Native HTTP request ' in line]
        ends = [line for line in output if 'Native HTTP result ' in line]
        self.assertEqual(len(starts), 1, 'request was not recorded as a bounded diagnostic')
        self.assertEqual(len(ends), 1, 'request status was not recorded')
        request_id = re.search(r'\brequest=([0-9a-f]{12})\b', starts[0])
        self.assertIsNotNone(request_id)
        self.assertIn('request=' + request_id.group(1), ends[0])
        for key, value in [('route', route), ('method', method), ('origin', origin),
                           ('credentials', credentials), ('upgrade', upgrade)]:
            self.assertIn(key + '=' + value, starts[0])
        self.assertIn('status=' + str(status), ends[0])
        joined = '\n'.join(output)
        for forbidden in (SECRET, self.base, 'auth_token', 'Bearer', 'unit-test',
                          'unit-service', 'Authorization', '127.0.0.1', '/pending',
                          SIGNAL_PATH, 'service-now.com'):
            self.assertNotIn(forbidden, joined)
        self.assertLess(len(starts[0]), 260)
        self.assertLess(len(ends[0]), 120)

    async def request(self, method, path, *, headers=None, params=None, body=None):
        async with self.http.request(method, self.base + path, headers=headers,
                                     params=params, data=body) as response:
            return response.status, await response.text(), response.headers

    async def test_unknown_path_404_is_recorded_without_any_request_secrets(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            status, body, _ = await self.request('POST', '/private-' + SECRET,
                headers={'Origin':'https://' + SECRET, 'Authorization':'Bearer ' + SECRET,
                         'X-Unused-Header':SECRET, 'Upgrade':SECRET},
                params={'auth_token':SECRET, 'private_parameter':SECRET}, body=SECRET)
        self.assertEqual((status, body), (404, '404: Not Found'))
        self.assert_diagnostics(logs.output, route='other', method='POST', origin='other',
                                credentials='both', upgrade='other', status=404)

    async def test_unstripped_funnel_prefix_has_its_own_bounded_path_class(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            status, _, _ = await self.request('GET', '/scc-native' + SIGNAL_PATH,
                params={'auth_token':SECRET})
        self.assertEqual(status, 404)
        self.assert_diagnostics(logs.output, route='prefixed_signaling', method='GET',
                                origin='missing', credentials='query', upgrade='missing', status=404)

    async def test_duplicated_signaling_suffix_is_distinguished_from_an_unknown_path(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            status, _, _ = await self.request('GET', SIGNAL_PATH + SIGNAL_PATH,
                params={'auth_token':SECRET})
        self.assertEqual(status, 404)
        self.assert_diagnostics(logs.output, route='duplicated_signaling', method='GET',
                                origin='missing', credentials='query', upgrade='missing', status=404)

    async def test_wrong_method_405_retains_original_allow_header(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            status, body, headers = await self.request('POST', SIGNAL_PATH)
        self.assertEqual((status, body), (405, '405: Method Not Allowed'))
        self.assertEqual(set(headers['Allow'].split(',')), {'GET', 'HEAD'})
        self.assert_diagnostics(logs.output, route='signaling', method='POST', origin='missing',
                                credentials='none', upgrade='missing', status=405)

    async def test_matched_websocket_401_keeps_authorization_and_allocates_no_session(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            with self.assertRaises(WSServerHandshakeError) as denied:
                await self.http.ws_connect(self.base + SIGNAL_PATH,
                    params={'instance_name':self.config.instance_name,
                            'voice_service_id':self.config.voice_service_id, 'auth_token':SECRET},
                    headers={'Origin':self.config.instance_url})
        self.assertEqual(denied.exception.status, 401)
        self.assert_diagnostics(logs.output, route='signaling', method='GET', origin='expected',
                                credentials='query', upgrade='websocket', status=401)
        async with self.http.get(self.base + '/health') as response:
            self.assertEqual((await response.json())['nativeSessions'], 0)

    async def test_matched_http_401_response_is_unchanged(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            status, body, _ = await self.request('GET', SIGNAL_PATH)
        self.assertEqual((status, body), (401, 'Voice authorization rejected'))
        self.assert_diagnostics(logs.output, route='signaling', method='GET', origin='missing',
                                credentials='none', upgrade='missing', status=401)

    async def test_header_only_credential_and_empty_origin_remain_value_free(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            status, _, _ = await self.request('GET', SIGNAL_PATH,
                headers={'Authorization':SECRET, 'Origin':''})
        self.assertEqual(status, 401)
        self.assert_diagnostics(logs.output, route='signaling', method='GET', origin='other',
                                credentials='header', upgrade='missing', status=401)

    async def test_unusual_method_uses_other_instead_of_echoing_client_input(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            status, _, _ = await self.request('PUT', SIGNAL_PATH)
        self.assertEqual(status, 405)
        self.assert_diagnostics(logs.output, route='signaling', method='OTHER', origin='missing',
                                credentials='none', upgrade='missing', status=405)

    async def test_health_success_and_wrong_method_do_not_emit_diagnostics(self):
        with self.assertNoLogs('native-voice', level='INFO'):
            status, _, _ = await self.request('GET', '/health', params={'auth_token':SECRET})
            self.assertEqual(status, 200)
            status, _, _ = await self.request('POST', '/health', body=SECRET)
            self.assertEqual(status, 405)

    async def test_arrival_is_visible_before_a_slow_handler_completes(self):
        with self.assertLogs('native-voice', level='INFO') as logs:
            request_task = asyncio.create_task(self.request('GET', '/pending',
                params={'auth_token':SECRET}))
            try:
                await asyncio.wait_for(self.pending_entered.wait(), 1)
                self.assertTrue(any('Native HTTP request ' in record.getMessage()
                                    for record in logs.records), 'slow request arrival was invisible')
                self.assertFalse(any('Native HTTP result ' in record.getMessage()
                                     for record in logs.records))
            finally:
                self.pending_release.set()
                status, body, _ = await request_task
        self.assertEqual((status, body), (200, SECRET))
        self.assert_diagnostics(logs.output, route='other', method='GET', origin='missing',
                                credentials='query', upgrade='missing', status=200)

    async def test_unhandled_exception_is_preserved_without_logging_its_message(self):
        self.assertEqual(len(self.app.middlewares), 1, 'request diagnostic middleware missing')
        request = make_mocked_request('GET', '/private-' + SECRET)
        failure = RuntimeError(SECRET)
        async def fail_handler(request): raise failure
        with self.assertLogs('native-voice', level='INFO') as logs:
            with self.assertRaises(RuntimeError) as raised:
                await self.app.middlewares[0](request, fail_handler)
        self.assertIs(raised.exception, failure)
        self.assert_diagnostics(logs.output, route='other', method='GET', origin='missing',
                                credentials='none', upgrade='missing', status=500)

    async def test_handler_cancellation_is_preserved_without_logging_its_message(self):
        self.assertEqual(len(self.app.middlewares), 1, 'request diagnostic middleware missing')
        request = make_mocked_request('GET', '/private-' + SECRET)
        failure = asyncio.CancelledError(SECRET)
        async def cancel_handler(request): raise failure
        with self.assertLogs('native-voice', level='INFO') as logs:
            with self.assertRaises(asyncio.CancelledError) as raised:
                await self.app.middlewares[0](request, cancel_handler)
        self.assertIs(raised.exception, failure)
        self.assert_diagnostics(logs.output, route='other', method='GET', origin='missing',
                                credentials='none', upgrade='missing', status=0)


if __name__ == '__main__': unittest.main()
