"""Loopback contract checks; no production engine or ServiceNow calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import load_config

KEY = 'fixture-demo-no-thinking-key-32-characters'
HEADERS = {'Authorization': 'Bearer ' + KEY}


class DemoNoThinkingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen = []
        async def health(request):
            return web.json_response({'status': 'ok'})
        async def capture(request):
            self.seen.append((request.path, await request.json()))
            return web.json_response({'ok': True})
        app = web.Application()
        app.router.add_get('/health', health)
        app.router.add_post('/v1/chat/completions', capture)
        app.router.add_post('/v1/responses', capture)
        self.up = TestServer(app)
        await self.up.start_server()
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        (root / 'key.txt').write_text(KEY, encoding='ascii')
        self.config_path = root / 'gateway.json'
        self.config = {
            'schema': 1, 'token_file': 'key.txt',
            'backend': {'identifier': 'halogen-v2',
                'upstream': str(self.up.make_url('')).rstrip('/'),
                'model': 'halogen-qwen3.8-flash-next',
                'routes': ['/v1/chat/completions', '/v1/responses']}}
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        await self.up.close()
        self.directory.cleanup()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')

    async def client(self, target=None):
        if target is not None:
            self.config['demo_no_thinking_model'] = target
        self.write_config()
        gateway = load_config(self.config_path)
        client = TestClient(TestServer(gateway.app))
        self.clients.append(client)
        await client.start_server()
        return client

    async def send(self, client, model='halogen-v2', route='/v1/chat/completions'):
        body = {'model': model, 'messages': [{'role': 'user', 'content': 'fixture'}],
                'enable_thinking': True, 'reasoning_effort': 'medium',
                'max_tokens': 2048, 'max_thinking_tokens': 2048, 'stream': False,
                'response_format': {'type': 'json_object'},
                'tools': [{'type': 'function', 'function': {'name': 'fixture'}}]}
        response = await client.post(route, headers=HEADERS, json=body)
        self.assertEqual(response.status, 200)
        await response.read()
        return body, self.seen[-1][1]

    async def test_enabled_alias_overrides_thinking_and_preserves_tool_contract(self):
        client = await self.client('halogen-v2')
        original, observed = await self.send(client)
        expected = dict(original, model='halogen-qwen3.8-flash-next',
                        enable_thinking=False, reasoning_effort='none')
        self.assertEqual(observed, expected)

    async def test_default_off_preserves_original_request_settings(self):
        client = await self.client()
        original, observed = await self.send(client)
        self.assertEqual(observed, dict(original, model='halogen-qwen3.8-flash-next'))

    async def test_explicit_off_preserves_original_request_settings(self):
        client = await self.client('')
        original, observed = await self.send(client)
        self.assertEqual(observed, dict(original, model='halogen-qwen3.8-flash-next'))

    async def test_upstream_model_name_does_not_trigger_alias_override(self):
        client = await self.client('halogen-v2')
        original, observed = await self.send(client, model='halogen-qwen3.8-flash-next')
        self.assertEqual(observed, original)

    async def test_other_route_does_not_trigger_chat_override(self):
        client = await self.client('halogen-v2')
        original, observed = await self.send(client, route='/v1/responses')
        self.assertEqual(observed, dict(original, model='halogen-qwen3.8-flash-next'))

    async def test_unknown_alias_is_still_rejected_before_forwarding(self):
        client = await self.client('halogen-v2')
        response = await client.post('/v1/chat/completions', headers=HEADERS,
                                     json={'model': 'another-alias'})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.seen, [])

    def test_invalid_or_conflicting_target_configuration_is_rejected(self):
        for value in (True, None, [], 'another-alias', 'halogen-qwen3.8-flash-next'):
            with self.subTest(value=value):
                self.config['demo_no_thinking_model'] = value
                self.write_config()
                with self.assertRaises(ValueError):
                    load_config(self.config_path)


if __name__ == '__main__':
    unittest.main()
