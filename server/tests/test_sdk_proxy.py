import asyncio
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name=='tests' else Path(__file__).resolve().parent))
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from yarl import URL
from gateway import Backend, Gateway

KEY = 'fixture-gateway-key-at-least-thirtytwo-chars'
TOKEN = 'fixture.platform.oauth'
BASE = '/api/webrtc/sessions'
SID = 'a' * 32


class SDKProxyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen = []
        async def native(request):
            self.seen.append((request.method, request.raw_path,
                              list(request.headers.items()), await request.read()))
            if request.headers.get('Authorization') != 'Bearer ' + TOKEN:
                return web.json_response({'error': 'unauthorized'}, status=401)
            if request.headers.get('Origin') == 'https://redirect.invalid':
                raise web.HTTPFound('https://example.invalid/never')
            return web.json_response({'native': True}, status=202)
        upstream = web.Application()
        async def health(request):
            return web.json_response({'status': 'ok'})
        upstream.router.add_get('/health', health)
        upstream.router.add_route('*', '/{tail:.*}', native)
        self.up = TestServer(upstream)
        await self.up.start_server()
        self.patch = patch('gateway.NATIVE_SDK_URL', str(self.up.make_url('')).rstrip('/'), create=True)
        self.patch.start()
        backend = Backend('fixture', str(self.up.make_url('')).rstrip('/'), 'real-model')
        self.gateway = Gateway(backend, KEY)
        # Explicit opt-in. Existing gateway has no SDK route and fails the
        # real HTTP assertion below with401 before the adapter is implemented.
        self.gateway.native_sdk_proxy = True
        self.client = TestClient(TestServer(self.gateway.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.patch.stop()
        await self.up.close()

    async def test_sdk_bearer_and_query_reach_native_without_llm_key(self):
        query = '?instance_name=soprasteriaassvsdemo14&receive_data=true'
        response = await self.client.post(BASE + query,
            headers={'Authorization': 'Bearer ' + TOKEN},
            json={'agent_id': 'agent_operator'})
        self.assertEqual(response.status, 202)
        self.assertEqual(await response.json(), {'native': True})
        self.assertEqual(self.seen[0][0:2], ('POST', BASE + query))
        self.assertNotIn(KEY, str(self.seen))
        self.assertEqual(self.gateway.active, 0)
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')

    async def test_all_verified_sdk_http_routes(self):
        for method, suffix in [('POST', '/offer'), ('POST', '/candidate'),
                               ('GET', '/candidates'), ('DELETE', '')]:
            response = await self.client.request(method, BASE + '/' + SID + suffix,
                headers={'Authorization': 'Bearer ' + TOKEN}, json={} if method == 'POST' else None)
            self.assertEqual(response.status, 202, (method, suffix))

    async def test_disabled_proxy_preserves_gateway_auth(self):
        self.gateway.native_sdk_proxy = False
        response = await self.client.post(BASE, headers={'Authorization': 'Bearer ' + TOKEN}, json={})
        self.assertEqual(response.status, 401)
        self.assertEqual(self.seen, [])

    async def test_llm_endpoints_still_require_gateway_key(self):
        for route in ['/v1/models', '/health', '/v1/chat/completions']:
            response = await self.client.post(route, headers={'Authorization': 'Bearer ' + TOKEN}, json={})
            self.assertEqual(response.status, 401)
        self.assertEqual(self.seen, [])

    async def test_wrong_methods_paths_and_encoded_paths_never_forward(self):
        for method, route in [('GET', BASE), ('POST', BASE + '/evil/offer'),
                              ('POST', BASE + '/' + SID + '/unknown'),
                              ('POST', '/api/webrtc/%73essions'),
                              ('POST', BASE + '/' + SID + '/offer/extra')]:
            response = await self.client.request(method, URL(route, encoded=True),
                headers={'Authorization': 'Bearer ' + TOKEN}, json={})
            self.assertNotEqual(response.status, 202)
        self.assertEqual(self.seen, [])

    async def test_credentials_required_and_not_replaced_with_gateway_key(self):
        for headers in [{}, {'Authorization': 'Basic fixture'},
                        {'Authorization': 'Bearer ' + KEY}]:
            response = await self.client.post(BASE, headers=headers, json={})
            self.assertEqual(response.status, 401)

    async def test_duplicate_and_conflicting_credentials_rejected(self):
        for headers in [[('Authorization', 'Bearer ' + TOKEN), ('Authorization', 'Bearer other')],
                        [('Authorization', 'Bearer ' + TOKEN), ('Cookie', 'fixture=value')],
                        [('Authorization', 'Bearer ' + TOKEN), ('X-API-Key', KEY)]]:
            response = await self.client.post(BASE, headers=headers, json={})
            self.assertEqual(response.status, 401)
        self.assertEqual(self.seen, [])

    async def test_oversized_or_encoded_request_never_forwarded(self):
        for headers, body in [({'Authorization': 'Bearer ' + TOKEN}, b'x' * 32769),
                ({'Authorization': 'Bearer ' + TOKEN, 'Content-Encoding': 'identity'}, b'{}')]:
            response = await self.client.post(BASE, headers=headers, data=body)
            self.assertIn(response.status, (400, 413))
        self.assertEqual(self.seen, [])

    async def test_native_redirect_is_not_followed(self):
        response = await self.client.post(BASE,
            headers={'Authorization': 'Bearer ' + TOKEN, 'Origin': 'https://redirect.invalid'}, json={})
        self.assertEqual(response.status, 502)
        self.assertNotIn('Location', response.headers)


if __name__ == '__main__':
    unittest.main()
