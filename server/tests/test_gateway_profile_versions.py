"""Reproduce Android's ready-but-rejected LLM boundary without real models."""
import sys
from pathlib import Path
import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gateway import Backend, Gateway

KEY = 'synthetic-gateway-version-fixture-32-characters'

class GatewayProfileVersionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = 0
        self.actual = {'status':'ok','version':{'api':'0.18.7','engine':'0.18.7','match':True},
                       'context':32768,'slots':1}
        async def health(request):
            return web.json_response(self.actual)
        async def infer(request):
            self.calls += 1
            return web.json_response({'choices':[{'message':{'content':'Welche Angaben fehlen?'}}]})
        app = web.Application()
        app.router.add_get('/health',health)
        app.router.add_post('/v1/chat/completions',infer)
        self.upstream = TestServer(app)
        await self.upstream.start_server()
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        await self.upstream.close()

    async def request(self,version):
        backend = Backend(identifier='halogen-v2',upstream=str(self.upstream.make_url('')).rstrip('/'),
            model='halogen-qwen3.8-flash-next',expected={'status':'ok','version.api':version,
            'version.engine':version,'version.match':True,'context':32768,'slots':1})
        gateway = Gateway(backend,KEY)
        client = TestClient(TestServer(gateway.app))
        self.clients.append(client)
        await client.start_server()
        return await client.post('/v1/chat/completions',headers={'Authorization':'Bearer '+KEY},
            json={'model':'halogen-v2','messages':[{'role':'user','content':'synthetic fixture'}]})

    async def test_stale_version_blocks_before_inference_and_logs_actual_http_status(self):
        with self.assertLogs('alloy.gateway',level='INFO') as logs:
            response = await self.request('0.18.1')
            self.assertEqual(response.status,503)
            await response.read()
        self.assertEqual(self.calls,0)
        request_logs = [line for line in logs.output if 'request backend=' in line]
        self.assertEqual(len(request_logs),1)
        self.assertIn('status=503',request_logs[0])

    async def test_aligned_version_forwards_and_retains_other_profile_checks(self):
        response = await self.request('0.18.7')
        self.assertEqual(response.status,200)
        await response.read()
        self.assertEqual(self.calls,1)
        self.actual['context'] = 8192
        response = await self.request('0.18.7')
        self.assertEqual(response.status,503)
        await response.read()
        self.assertEqual(self.calls,1,'A context mismatch must still block inference')

if __name__ == '__main__':
    unittest.main()
