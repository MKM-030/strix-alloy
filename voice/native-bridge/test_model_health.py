"""Two bounded fake-HTTP checks; no model or ServiceNow invocation."""
import unittest

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from model_health import require_model_ready, validate_model_health
from native_bridge import Config, Dialog


class ModelHealthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.status = 200
        self.payload = {'status': 'ok', 'draining': False}
        self.calls = []
        async def health(request):
            self.calls.append((request.method, request.path))
            if request.headers.get('Authorization') != 'Bearer ' + 'private-unit-token':
                return web.Response(status=401)
            return web.json_response(self.payload, status=self.status)
        fake = web.Application()
        fake.router.add_get('/health', health)
        self.server = TestServer(fake)
        await self.server.start_server()
        self.url = str(self.server.make_url('/health'))
        self.http = ClientSession(trust_env=False)

    async def asyncTearDown(self):
        await self.http.close()
        await self.server.close()

    async def test_only_authenticated_ready_nondraining_health_passes(self):
        validate_model_health(self.url, 'private-unit-token')
        await require_model_ready(self.http, self.url, 'private-unit-token')
        for status, payload in ((503, {'status': 'unavailable', 'draining': True}),
                                (200, {'status': 'ok', 'draining': True}),
                                (200, {'status': 'ok'}),
                                (200, {'status': 'unavailable', 'draining': False})):
            self.status, self.payload = status, payload
            with self.assertRaisesRegex(RuntimeError, 'business outcome unknown'):
                await require_model_ready(self.http, self.url, 'private-unit-token')
        with self.assertRaises(RuntimeError):
            await require_model_ready(self.http, self.url, 'wrong-unit-token')
        with self.assertRaises(ValueError):
            validate_model_health('https://external.invalid/health', 'private-unit-token')
        self.assertTrue(all(item == ('GET', '/health') for item in self.calls))

    async def test_dialog_blocks_before_send_and_detects_fault_after_first_event_poll(self):
        config = Config(model_health_url=self.url, private_model_health_token='private-unit-token')
        dialog = Dialog(config)
        dialog.http = self.http
        business = []
        async def request(method, path, **kwargs):
            business.append((method, path))
            if method == 'POST':
                # Simulates the owned controller latching fatal after dispatch.
                self.status, self.payload = 503, {'status': 'unavailable', 'draining': True}
                return {'accepted': True}
            return {'cursor': 1, 'events': [], 'busy': True}
        dialog.request = request
        with self.assertRaisesRegex(RuntimeError, 'business outcome unknown'):
            await dialog.turn('Harmless text')
        self.assertEqual(business, [('POST', '/api/message'), ('GET', '/api/events')])
        business.clear()
        with self.assertRaises(RuntimeError):
            await dialog.turn('Another harmless text')
        self.assertEqual(business, [])


if __name__ == '__main__':
    unittest.main()
