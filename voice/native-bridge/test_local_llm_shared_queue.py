"""Native text and ServiceNow share a serial, authenticated gateway.

All HTTP is confined to in-process test servers on ephemeral ports. The fixed
production route is mapped explicitly; no service, token file or model is used.
"""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'server')]
import local_llm_socket
from local_llm_socket import LocalTextSocket, validate_local_conversation
from test_local_llm_fixed_routes import wire_context
from gateway import Backend, Gateway

CHAT = 'http://127.0.0.1:8841/v1/chat/completions'
MODELS = 'http://127.0.0.1:8841/v1/models'
KEY = 'synthetic-shared-gateway-key-32-characters'
UPSTREAM_KEY = 'synthetic-controller-key-32-characters'
HEADERS = {'Authorization': 'Bearer ' + KEY}


def sse(text):
    events = [dict(choices=[dict(delta=dict(content=text), finish_reason=None)]),
              dict(choices=[dict(delta={}, finish_reason='stop')])]
    return ''.join('data: ' + json.dumps(item) + '\n\n' for item in events) + 'data: [DONE]\n\n'


class MappedHTTP:
    """Map only the literal shared production gateway onto one test client."""
    def __init__(self, client):
        self.client, self.requests, self.closed = client, [], False

    def get(self, url, **kwargs):
        if url != MODELS:
            raise AssertionError('Native selection bypassed the shared queue gateway')
        self.requests.append(('GET', url, kwargs))
        return self.client.get('/v1/models', **kwargs)

    def post(self, url, **kwargs):
        if url != CHAT:
            raise AssertionError('Native generation bypassed the shared queue gateway')
        self.requests.append(('POST', url, kwargs))
        return self.client.post('/v1/chat/completions', **kwargs)

    async def close(self):
        self.closed = True


class SharedGatewayEndpointTests(unittest.TestCase):
    def test_shared_queue_is_default_and_arbitrary_endpoints_are_rejected(self):
        self.assertEqual(local_llm_socket.CONTROLLER_CHAT_URL, CHAT)
        self.assertEqual(local_llm_socket.CONTROLLER_MODELS_URL, MODELS)
        validate_local_conversation(CHAT, 'C:/synthetic-only-token')
        for bad in ['http://127.0.0.1:8731/v1/chat/completions',
                    'http://localhost:8841/v1/chat/completions',
                    'https://127.0.0.1:8841/v1/chat/completions',
                    CHAT + '?route=other', CHAT + '#fragment',
                    'http://127.0.0.1:8841/v1/completions']:
            with self.subTest(url=bad), self.assertRaises(ValueError):
                validate_local_conversation(bad, 'C:/synthetic-only-token')


class SharedGatewayIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.business_release = asyncio.Event()
        self.started = asyncio.Queue()
        self.seen, self.auth, self.active, self.maximum_active = [], [], 0, 0
        self.sockets, self.tasks = [], []

        async def health(request):
            self.assertEqual(request.headers.get('Authorization'), 'Bearer ' + UPSTREAM_KEY)
            return web.json_response(dict(status='ok', backend='halogen-v2', checkpoint='v2', context=32768,
                active_requests=self.active, queued_requests=0, draining=False))

        async def models(request):
            self.assertEqual(request.headers.get('Authorization'), 'Bearer ' + UPSTREAM_KEY)
            return web.json_response(dict(data=[dict(id='halogen-v2', checkpoint='v2',
                context_capacity=32768, routes=['/v1/chat/completions'])]))

        async def chat(request):
            value = await request.json()
            name = value['messages'][-1]['content']
            self.auth.append(request.headers.get('Authorization'))
            self.seen.append(name)
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.started.put_nowait(name)
            try:
                if name == 'ServiceNow business fixture':
                    await self.business_release.wait()
                return web.Response(text=sse('Ja, ich höre Sie. Wie kann ich helfen?'),
                                    content_type='text/event-stream')
            finally:
                self.active -= 1

        app = web.Application()
        app.router.add_get('/health', health)
        app.router.add_get('/v1/models', models)
        app.router.add_post('/v1/chat/completions', chat)
        self.upstream = TestServer(app, handler_cancellation=True)
        await self.upstream.start_server()
        self.gateway = Gateway(Backend('controller-selected',
            str(self.upstream.make_url('')).rstrip('/'), 'controller-selected',
            routes=('/v1/chat/completions',)), KEY, UPSTREAM_KEY,
            concurrency=1, queue_limit=8, queue_seconds=120, controller_consumer=True,
            controller_model_aliases={'Gemma 4 26B-A4B': 'gemma4-26b-a4b'})
        self.client = TestClient(TestServer(self.gateway.app, handler_cancellation=True))
        await self.client.start_server()
        self.key_patch = patch.object(local_llm_socket, '_token', return_value=KEY)
        self.key_patch.start()

    async def asyncTearDown(self):
        self.business_release.set()
        for socket in self.sockets:
            await socket.close()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.client.close()
        await self.upstream.close()
        self.key_patch.stop()

    async def wait_counts(self, active, waiting):
        async with asyncio.timeout(2):
            while self.gateway.active != active or len(self.gateway.waiters) != waiting:
                await asyncio.sleep(.005)

    async def start_business(self):
        task = asyncio.create_task(self.client.post('/v1/chat/completions', headers=HEADERS,
            json=dict(model='halogen-v2', messages=[dict(role='user', content='ServiceNow business fixture')],
                      stream=True)))
        self.tasks.append(task)
        self.assertEqual(await asyncio.wait_for(self.started.get(), 2), 'ServiceNow business fixture')
        return task

    async def start_front(self):
        self.assertEqual(local_llm_socket.CONTROLLER_CHAT_URL, CHAT)
        http = MappedHTTP(self.client)
        source = LocalTextSocket(CHAT, 'C:/synthetic-only-token', http=http)
        self.sockets.append(source)
        await source.send_json(dict(type='session.start', mode='text', system_prompt='Central assistant rules'))
        await source.send_json(dict(type='session.update', system_prompt_patch=wire_context()))
        await source.send_json(dict(type='input.text', text='Hörst du mich?'))
        return source, http

    async def test_overlap_queues_front_once_instead_of_429_without_parallel_generation(self):
        business = await self.start_business()
        source, http = await self.start_front()
        await self.wait_counts(1, 1)
        self.assertFalse(source._task.done())
        self.assertEqual(self.seen, ['ServiceNow business fixture'])
        self.business_release.set()
        response = await business
        self.assertEqual(response.status, 200)
        await response.read()
        await asyncio.wait_for(source._task, 2)
        await self.wait_counts(0, 0)
        events = []
        while not source.events.empty():
            events.append(source.events.get_nowait())
        self.assertFalse(source.transient_busy)
        self.assertFalse(any(item['type'] == 'error' for item in events))
        self.assertEqual([item['text'] for item in events if item['type'] == 'response.text.done'],
                         ['Ja, ich höre Sie. Wie kann ich helfen?'])
        self.assertEqual(self.seen, ['ServiceNow business fixture', 'Hörst du mich?'])
        self.assertEqual(self.maximum_active, 1)
        self.assertEqual(self.auth, ['Bearer ' + UPSTREAM_KEY] * 2)
        self.assertEqual([(method, url) for method, url, _ in http.requests], [('GET', MODELS), ('POST', CHAT)])
        body = http.requests[-1][2]['json']
        self.assertEqual((body['max_tokens'], body['reasoning_effort'], body['enable_thinking']), (192, 'none', False))

    async def test_cancelled_queued_front_never_reaches_controller_or_retries_business(self):
        business = await self.start_business()
        source, _ = await self.start_front()
        await self.wait_counts(1, 1)
        await source._cancel()
        await self.wait_counts(1, 0)
        self.business_release.set()
        response = await business
        self.assertEqual(response.status, 200)
        await response.read()
        await self.wait_counts(0, 0)
        self.assertEqual(self.seen, ['ServiceNow business fixture'])
        self.assertEqual(self.maximum_active, 1)
        self.assertEqual(self.gateway.cancelled, 1)


if __name__ == '__main__':
    unittest.main()
