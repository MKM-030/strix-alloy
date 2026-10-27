"""Fake-controller coverage. No local model or ServiceNow requests."""
import asyncio
import sys
import unittest
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import Backend, Gateway

PUBLIC = 'fixture-public-controller-key-32-characters'
UPSTREAM = 'fixture-private-controller-key-32-characters'
HEADERS = {'Authorization': 'Bearer ' + PUBLIC}


class ControllerConsumerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.current = dict(id='halogen-v2', checkpoint='v2', context=32768)
        self.controller_busy = False
        self.controller_draining = False
        self.catalog_id_override = None
        self.seen = []
        self.metadata_auth = []
        async def health(request):
            self.metadata_auth.append(request.headers.get('Authorization'))
            if request.headers.get('Authorization') != 'Bearer ' + UPSTREAM:
                return web.Response(status=401)
            return web.json_response(dict(status='ok', backend=self.current['id'],
                checkpoint=self.current['checkpoint'], context=self.current['context'],
                active_requests=int(self.controller_busy), queued_requests=0, draining=self.controller_draining))
        async def models(request):
            self.metadata_auth.append(request.headers.get('Authorization'))
            if request.headers.get('Authorization') != 'Bearer ' + UPSTREAM:
                return web.Response(status=401)
            return web.json_response({'object': 'list', 'data': [dict(
                id=self.catalog_id_override or self.current['id'], checkpoint=self.current['checkpoint'],
                context_capacity=self.current['context'], routes=['/v1/chat/completions'])]})
        async def chat(request):
            self.seen.append((await request.json(), request.headers.get('Authorization')))
            if self.controller_busy:
                return web.json_response({'error': {'message': 'controller busy'}}, status=429,
                                         headers={'Retry-After': '3'})
            return web.json_response({'model': self.seen[-1][0]['model'], 'ok': True})
        app = web.Application()
        app.router.add_get('/health', health)
        app.router.add_get('/v1/models', models)
        app.router.add_post('/v1/chat/completions', chat)
        self.up = TestServer(app)
        await self.up.start_server()
        self.gateway = Gateway(Backend('controller-selected', str(self.up.make_url('')).rstrip('/'),
            'controller-selected', routes=('/v1/chat/completions',)), PUBLIC, UPSTREAM,
            controller_consumer=True, controller_aliases=['gemma4-26b-a4b', 'Gemma 4 26B-A4B'])
        self.client = TestClient(TestServer(self.gateway.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.up.close()

    async def test_model_change_is_resolved_without_source_or_config_change(self):
        for active in (dict(id='halogen-v2', checkpoint='v2', context=32768),
                       dict(id='gemma4-26b-a4b', checkpoint='gemma-fixture', context=16384)):
            self.current = active
            reply = await self.client.post('/v1/chat/completions', headers=HEADERS,
                json={'model': 'Gemma 4 26B-A4B', 'messages': [{'role': 'user', 'content': 'fixture'}]})
            self.assertEqual(reply.status, 200)
            self.assertEqual((await reply.json())['model'], active['id'])
            self.assertEqual(self.seen[-1][1], 'Bearer ' + UPSTREAM)
            health = await self.client.get('/health', headers=HEADERS)
            value = await health.json()
            self.assertEqual((value['backend'], value['checkpoint'], value['context']),
                             (active['id'], active['checkpoint'], active['context']))
            models = await self.client.get('/v1/models', headers=HEADERS)
            model = (await models.json())['data'][0]
            self.assertEqual(model['id'], active['id'])
            self.assertEqual(model['compatibility_aliases'], ['gemma4-26b-a4b', 'Gemma 4 26B-A4B'])

    async def test_public_auth_and_upstream_auth_are_kept_separate(self):
        for route in ('/health', '/v1/models'):
            reply = await self.client.get(route)
            self.assertEqual(reply.status, 401)
        reply = await self.client.post('/v1/chat/completions', json={'model': 'Gemma 4 26B-A4B'})
        self.assertEqual(reply.status, 401)
        self.assertEqual(self.seen, [])
        reply = await self.client.get('/v1/models', headers=HEADERS)
        self.assertEqual(reply.status, 200)
        self.assertTrue(self.metadata_auth)
        self.assertEqual(set(self.metadata_auth), {'Bearer ' + UPSTREAM})
        self.gateway.backend_secret = 'wrong-fixture-upstream-key'
        reply = await self.client.post('/v1/chat/completions', headers=HEADERS,
                                      json={'model': 'Gemma 4 26B-A4B'})
        self.assertEqual(reply.status, 503)
        self.assertEqual(self.seen, [])

    async def test_controller_busy_status_and_retry_after_reach_caller(self):
        self.controller_busy = True
        reply = await self.client.get('/health', headers=HEADERS)
        self.assertEqual(reply.status, 200)
        self.assertEqual((await reply.json())['controller']['active_requests'], 1)
        reply = await self.client.post('/v1/chat/completions', headers=HEADERS,
                                      json={'model': 'gemma4-26b-a4b'})
        self.assertEqual(reply.status, 429)
        self.assertEqual(reply.headers.get('Retry-After'), '3')
        self.assertEqual(await reply.json(), {'error': {'message': 'controller busy'}})
        self.assertEqual(self.gateway.active, 0)

    async def test_single_system_dispatch_only_for_current_halogen(self):
        messages = [{'role': 'system', 'content': 'fixture task'}]
        reply = await self.client.post('/v1/chat/completions', headers=HEADERS,
            json={'model': 'Gemma 4 26B-A4B', 'messages': messages, 'temperature': 0})
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.seen[-1][0]['messages'][0], messages[0])
        self.assertEqual(self.seen[-1][0]['messages'][1]['role'], 'user')
        self.assertEqual(self.seen[-1][0]['temperature'], 0)
        self.current = dict(id='gemma4-26b-a4b', checkpoint='gemma-fixture', context=32768)
        reply = await self.client.post('/v1/chat/completions', headers=HEADERS,
            json={'model': 'Gemma 4 26B-A4B', 'messages': messages})
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.seen[-1][0]['messages'], messages)

    async def test_mismatched_selection_and_draining_never_submit_inference(self):
        self.catalog_id_override = 'different-fixture-model'
        reply = await self.client.post('/v1/chat/completions', headers=HEADERS,
                                      json={'model': 'gemma4-26b-a4b'})
        self.assertEqual(reply.status, 503)
        self.assertEqual(self.seen, [])
        self.catalog_id_override = None
        self.controller_draining = True
        reply = await self.client.get('/health', headers=HEADERS)
        self.assertEqual(reply.status, 503)
        self.assertTrue((await reply.json())['draining'])
        reply = await self.client.post('/v1/chat/completions', headers=HEADERS,
                                      json={'model': 'gemma4-26b-a4b'})
        self.assertEqual(reply.status, 503)
        self.assertEqual(self.seen, [])


if __name__ == '__main__':
    unittest.main()
