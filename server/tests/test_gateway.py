import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from aiohttp import web,ClientSession,ClientTimeout
from aiohttp.test_utils import TestClient,TestServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gateway import Backend,Gateway

KEY='fixture-public-key-material-32-characters'
BACKEND_KEY='fixture-upstream-key-material-32-characters'
HEADERS={'Authorization':'Bearer '+KEY}

class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen=[]; self.start=asyncio.Event(); self.release=asyncio.Event()
        async def health(request):
            if request.headers.get('Authorization')!='Bearer '+BACKEND_KEY:
                return web.Response(status=401)
            return web.json_response({'status':'ok','version':'fixture-v1'})
        async def chat(request):
            body=await request.json(); self.seen.append((body,dict(request.headers)))
            if body.get('redirect'): raise web.HTTPFound('https://example.invalid/never')
            if body.get('hold'):
                self.start.set(); await self.release.wait()
            if body.get('stream'):
                response=web.StreamResponse(headers={'Content-Type':'text/event-stream'})
                await response.prepare(request)
                await response.write(b'data: {"text":"first"}\n\n')
                self.start.set(); await self.release.wait()
                await response.write(b'data: [DONE]\n\n'); return response
            return web.json_response({'model':body['model'],'choices':[{'message':{'content':'OK'}}]})
        upstream=web.Application()
        upstream.router.add_get('/health',health)
        upstream.router.add_post('/v1/chat/completions',chat)
        self.up=TestServer(upstream,handler_cancellation=True)
        await self.up.start_server()
        self.gateway=Gateway(Backend('fixture',str(self.up.make_url('')).rstrip('/'),'real-model',
            expected={'status':'ok','version':'fixture-v1'},routes=('/v1/chat/completions',)),
            KEY,BACKEND_KEY,body_bytes=2048)
        self.client=TestClient(TestServer(self.gateway.app,handler_cancellation=True))
        await self.client.start_server()

    async def asyncTearDown(self):
        self.release.set(); await self.client.close(); await self.up.close()

    async def test_authorization_required_everywhere(self):
        for path in ['/health','/v1/models','/logs','/admin']:
            r=await self.client.get(path); self.assertEqual(r.status,401)
        r=await self.client.get('/health',headers={'Authorization':'Bearer wrong'})
        self.assertEqual(r.status,401)

    async def test_health_live_and_model_mapping(self):
        r=await self.client.get('/health',headers=HEADERS); self.assertEqual(r.status,200)
        r=await self.client.post('/v1/chat/completions',headers=HEADERS,json={'model':'fixture'})
        self.assertEqual(r.status,200); self.assertEqual((await r.json())['model'],'real-model')
        self.assertEqual(self.seen[-1][1]['Authorization'],'Bearer '+BACKEND_KEY)
        self.assertNotIn(KEY,str(self.seen[-1]))

    async def test_unknown_model_and_routes_are_refused(self):
        r=await self.client.post('/v1/chat/completions',headers=HEADERS,json={'model':'other'})
        self.assertEqual(r.status,400); self.assertEqual(self.seen,[])
        r=await self.client.post('/v1/embeddings',headers=HEADERS,json={'model':'fixture'})
        self.assertEqual(r.status,501)
        r=await self.client.get('/logs',headers=HEADERS); self.assertEqual(r.status,404)

    async def test_redirect_is_not_followed(self):
        r=await self.client.post('/v1/chat/completions',headers=HEADERS,
                                 json={'model':'fixture','redirect':True})
        self.assertEqual(r.status,503)

    async def test_body_limit_and_json_validation(self):
        r=await self.client.post('/v1/chat/completions',headers=HEADERS,data='x'*4096)
        self.assertEqual(r.status,413)
        r=await self.client.post('/v1/chat/completions',headers=HEADERS,data='{')
        self.assertEqual(r.status,400)
        self.assertEqual(self.gateway.active,0)

    async def test_sse_is_forwarded_before_backend_finishes(self):
        r=await self.client.post('/v1/chat/completions',headers=HEADERS,
                                 json={'model':'fixture','stream':True})
        first=await asyncio.wait_for(r.content.readuntil(b'\n\n'),2)
        self.assertEqual(first,b'data: {"text":"first"}\n\n')
        self.assertFalse(self.release.is_set())
        self.release.set(); self.assertEqual(await r.read(),b'data: [DONE]\n\n')

    async def test_slow_nonstream_response_uses_configured_request_budget(self):
        # Scale long request/read timers so the old 300-second idle cap is 0.3s,
        # while the configured 1200-second budget is 1.2s. Keep connect/health
        # timers intact; the request still travels through real HTTP sockets.
        def accelerated_timeout(*args, **kwargs):
            for field in ('total', 'sock_read'):
                if kwargs.get(field, 0) >= 300:
                    kwargs[field] *= .001
            return ClientTimeout(*args, **kwargs)

        gateway=Gateway(self.gateway.backend,KEY,BACKEND_KEY,request_seconds=1200)
        client=TestClient(TestServer(gateway.app,handler_cancellation=True))
        try:
            with patch('gateway.aiohttp.ClientTimeout',side_effect=accelerated_timeout):
                await client.start_server()
                pending=asyncio.create_task(client.post('/v1/chat/completions',headers=HEADERS,
                    json={'model':'fixture','hold':True,'stream':False}))
                await asyncio.wait_for(self.start.wait(),2)
                await asyncio.sleep(.6)
                self.release.set()
                response=await asyncio.wait_for(pending,2)
                self.assertEqual(response.status,200)
                self.assertEqual((await response.json())['choices'][0]['message']['content'],'OK')
                self.assertEqual(gateway.completed,1)
        finally:
            self.release.set()
            await client.close()

    async def test_busy_rejects_without_queueing_another_generation(self):
        pending=asyncio.create_task(self.client.post('/v1/chat/completions',headers=HEADERS,
                    json={'model':'fixture','hold':True}))
        await asyncio.wait_for(self.start.wait(),2)
        r=await self.client.post('/v1/chat/completions',headers=HEADERS,json={'model':'fixture'})
        self.assertEqual(r.status,429); self.assertEqual(len(self.seen),1)
        self.release.set(); r=await pending; await r.read()

    async def test_peer_disconnect_releases_request_slot(self):
        r=await self.client.post('/v1/chat/completions',headers=HEADERS,
                                 json={'model':'fixture','stream':True})
        await r.content.readuntil(b'\n\n'); r.close()
        for _ in range(100):
            if self.gateway.active==0: break
            await asyncio.sleep(.01)
        self.assertEqual(self.gateway.active,0)
        self.assertEqual(self.gateway.cancelled,1)

    async def test_wrong_health_identity_is_not_ready(self):
        self.gateway.backend.expected['version']='different'
        r=await self.client.get('/health',headers=HEADERS); self.assertEqual(r.status,503)

class OriginTests(unittest.TestCase):
    def test_nonlocal_and_ambiguous_origins_refused(self):
        for origin in ['https://example.com','http://localhost:8731','http://127.0.0.1:8731/v1',
                       'http://user:pass@127.0.0.1:8731','http://127.0.0.1:8731?x=1']:
            with self.assertRaises(ValueError): Backend('x',origin,'x')

if __name__=='__main__': unittest.main()
