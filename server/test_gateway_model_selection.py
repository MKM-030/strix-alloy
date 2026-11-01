"""Exactly three fake-controller cases; no model, mic or ServiceNow calls."""
import importlib.util
from pathlib import Path
import sys
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location('gateway_selection_under_test', HERE / 'gateway.py')
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

PUBLIC = 'fixture-public-task77-key-32-characters'
PRIVATE = 'fixture-controller-task77-key-32-characters'
HEADERS = {'Authorization': 'Bearer ' + PUBLIC}
GEMMA = 'gemma4-26b-a4b'
DISPLAY = 'Gemma 4 26B-A4B'
ACTIVE_ALIAS = 'scc-local-active'


class SelectionContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.active = 'halogen-v2'
        self.posts = []
        async def health(request):
            if request.headers.get('Authorization') != 'Bearer ' + PRIVATE:
                return web.Response(status=401)
            return web.json_response(dict(status='ok', backend=self.active,
                checkpoint=self.active, context=32768, active_requests=0,
                queued_requests=0, draining=False))
        async def models(request):
            if request.headers.get('Authorization') != 'Bearer ' + PRIVATE:
                return web.Response(status=401)
            return web.json_response({'data': [dict(id=self.active, checkpoint=self.active,
                context_capacity=32768, routes=['/v1/chat/completions'])]})
        async def chat(request):
            self.assertEqual(request.headers.get('Authorization'), 'Bearer ' + PRIVATE)
            self.posts.append(await request.json())
            return web.json_response({'model': self.posts[-1]['model']})
        app = web.Application()
        app.router.add_get('/health', health)
        app.router.add_get('/v1/models', models)
        app.router.add_post('/v1/chat/completions', chat)
        self.up = TestServer(app)
        await self.up.start_server()
        self.addAsyncCleanup(self.up.close)
        gateway = MODULE.Gateway(MODULE.Backend('controller-selected',
            str(self.up.make_url('')).rstrip('/'), 'controller-selected'),
            PUBLIC, PRIVATE, controller_consumer=True,
            controller_aliases=[ACTIVE_ALIAS],
            controller_model_aliases={GEMMA: GEMMA, DISPLAY: GEMMA})
        self.client = TestClient(TestServer(gateway.app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def post(self, model):
        return await self.client.post('/v1/chat/completions', headers=HEADERS,
            json={'model': model, 'messages': [{'role': 'user', 'content': 'fixture'}]})

    async def test_fixed_gemma_identifiers_conflict_with_loaded_halogen_without_post(self):
        for alias in (GEMMA, DISPLAY):
            response = await self.post(alias)
            self.assertEqual(response.status, 409)
            error = (await response.json())['error']
            self.assertEqual(error['code'], 'model_selection_mismatch')
            self.assertEqual(error['required_model'], GEMMA)
            self.assertEqual(error['active_model'], 'halogen-v2')
            self.assertEqual(self.posts, [])

    async def test_gemma_display_alias_uses_gemma_only_when_gemma_is_active(self):
        self.active = GEMMA
        response = await self.post(DISPLAY)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())['model'], GEMMA)
        self.assertEqual(self.posts[-1]['model'], GEMMA)

    async def test_general_alias_follows_active_model_and_canonical_id_stays_direct(self):
        for model in ('halogen-v2', GEMMA):
            self.active = model
            for requested in (ACTIVE_ALIAS, model):
                response = await self.post(requested)
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())['model'], model)
            response = await self.client.get('/v1/models', headers=HEADERS)
            metadata = (await response.json())['data'][0]
            self.assertEqual(metadata['id'], model)
            self.assertEqual(metadata['compatibility_aliases'], [ACTIVE_ALIAS])
            response = await self.client.get('/health', headers=HEADERS)
            self.assertEqual((await response.json())['backend'], model)


if __name__ == '__main__':
    unittest.main()
