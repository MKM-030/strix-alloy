import asyncio
from contextlib import suppress
import json
from pathlib import Path
import sys
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gateway import Backend,Gateway,load_config

KEY='fixture-public-key-material-32-characters'
HEADERS={'Authorization':'Bearer '+KEY}
ROUTE='/v1/chat/completions'


class GatewayQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.started=asyncio.Queue()
        self.gates={name:asyncio.Event() for name in ('first','second','third','last')}
        self.seen=[]; self.running=0; self.max_running=0; self.tasks=[]
        async def health(request):
            return web.json_response({'status':'ok'})
        async def chat(request):
            body=await request.json(); name=body['name']
            self.seen.append(name); self.running+=1
            self.max_running=max(self.max_running,self.running)
            self.started.put_nowait(name)
            try:
                await self.gates[name].wait()
                return web.json_response({'name':name,'model':body['model']})
            finally:
                self.running-=1
        upstream=web.Application()
        upstream.router.add_get('/health',health)
        upstream.router.add_post(ROUTE,chat)
        self.up=TestServer(upstream,handler_cancellation=True)
        await self.up.start_server()
        self.gateway=Gateway(Backend('fixture',str(self.up.make_url('')).rstrip('/'),
                                     'real-model',routes=(ROUTE,)),KEY,
                             queue_limit=2,queue_seconds=1)
        self.client=TestClient(TestServer(self.gateway.app,handler_cancellation=True))
        await self.client.start_server()

    async def asyncTearDown(self):
        for gate in self.gates.values(): gate.set()
        for task in self.tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.client.close()
        await self.up.close()

    def post(self,name):
        task=asyncio.create_task(self.client.post(ROUTE,headers=HEADERS,
            json={'model':'fixture','name':name}))
        self.tasks.append(task)
        return task

    async def start_first(self):
        task=self.post('first')
        self.assertEqual(await asyncio.wait_for(self.started.get(),2),'first')
        return task

    async def assert_waiting(self,task):
        # A completed 429 is the regression: the concurrent caller must wait.
        await asyncio.sleep(.05)
        self.assertFalse(task.done(),'A request within queue capacity was rejected instead of waiting')

    async def wait_counts(self,active,queued):
        async def check():
            while True:
                response=await self.client.get('/health',headers=HEADERS)
                payload=await response.json()
                if payload['active_requests']==active and payload.get('queued_requests')==queued:
                    return payload
                await asyncio.sleep(.01)
        return await asyncio.wait_for(check(),2)

    async def test_parallel_calls_wait_fifo_without_parallel_generation(self):
        first=await self.start_first()
        second=self.post('second'); await self.assert_waiting(second)
        third=self.post('third'); await self.assert_waiting(third)
        await self.wait_counts(1,2)
        self.assertEqual(self.seen,['first'])
        self.gates['first'].set()
        self.assertEqual((await first).status,200)
        self.assertEqual(await asyncio.wait_for(self.started.get(),2),'second')
        self.assertFalse(third.done())
        self.gates['second'].set()
        self.assertEqual((await second).status,200)
        self.assertEqual(await asyncio.wait_for(self.started.get(),2),'third')
        self.gates['third'].set()
        self.assertEqual((await third).status,200)
        await self.wait_counts(0,0)
        self.assertEqual(self.max_running,1)
        self.assertEqual(self.gateway.completed,3)

    async def test_queue_overflow_rejects_without_reaching_backend(self):
        self.gateway.queue_limit=1
        await self.start_first()
        second=self.post('second'); await self.assert_waiting(second)
        response=await asyncio.wait_for(self.post('third'),2)
        self.assertEqual(response.status,429)
        self.assertEqual(response.headers['Retry-After'],'1')
        await self.wait_counts(1,1)
        self.assertEqual(self.seen,['first'])

    async def test_wait_timeout_is_finite_and_queue_capacity_recovers(self):
        self.gateway.queue_limit=1; self.gateway.queue_seconds=.15
        first=await self.start_first()
        began=asyncio.get_running_loop().time()
        response=await asyncio.wait_for(self.post('second'),1)
        elapsed=asyncio.get_running_loop().time()-began
        self.assertGreaterEqual(elapsed,.1)
        self.assertLess(elapsed,1)
        self.assertEqual(response.status,429)
        self.assertEqual(response.headers['Retry-After'],'1')
        await self.wait_counts(1,0)
        third=self.post('third'); await self.assert_waiting(third)
        self.gates['first'].set(); self.gates['third'].set()
        self.assertEqual((await first).status,200)
        self.assertEqual((await third).status,200)
        await self.wait_counts(0,0)
        self.assertEqual(self.seen,['first','third'])

    async def test_disconnected_waiter_releases_queue_capacity_and_no_active_slot(self):
        self.gateway.queue_limit=1
        first=await self.start_first()
        second=self.post('second'); await self.assert_waiting(second)
        await self.wait_counts(1,1)
        second.cancel()
        with suppress(asyncio.CancelledError): await second
        await self.wait_counts(1,0)
        third=self.post('third'); await self.assert_waiting(third)
        self.gates['first'].set(); self.gates['third'].set()
        self.assertEqual((await first).status,200)
        self.assertEqual((await third).status,200)
        await self.wait_counts(0,0)
        self.assertEqual(self.seen,['first','third'])
        self.assertEqual(self.gateway.cancelled,1)

    async def test_draining_rejects_queued_and_new_calls(self):
        first=await self.start_first()
        second=self.post('second'); await self.assert_waiting(second)
        self.gateway.draining=True
        self.assertEqual((await asyncio.wait_for(second,.5)).status,429)
        self.assertEqual((await self.post('third')).status,429)
        await self.wait_counts(1,0)
        self.gates['first'].set()
        self.assertEqual((await first).status,200)
        await self.wait_counts(0,0)
        self.assertEqual(self.seen,['first'])

    async def test_auth_and_model_validation_do_not_consume_waiting_capacity(self):
        self.gateway.queue_limit=1
        await self.start_first()
        second=self.post('second'); await self.assert_waiting(second)
        unauthorized=await self.client.post(ROUTE,json={'model':'fixture'})
        self.assertEqual(unauthorized.status,401)
        wrong_model=await self.client.post(ROUTE,headers=HEADERS,json={'model':'wrong'})
        self.assertEqual(wrong_model.status,400)
        invalid_json=await self.client.post(ROUTE,headers=HEADERS,data='{')
        self.assertEqual(invalid_json.status,400)
        unsupported=await self.client.post('/v1/embeddings',headers=HEADERS,json={'model':'fixture'})
        self.assertEqual(unsupported.status,501)
        await self.wait_counts(1,1)
        self.assertEqual(self.seen,['first'])


class GatewayQueueHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.gateway=Gateway(Backend('fixture','http://127.0.0.1:8731','real-model'),
                             KEY,queue_limit=1)

    async def test_cancel_after_grant_returns_reserved_slot(self):
        self.assertTrue(await self.gateway.acquire_slot())
        waiting=asyncio.create_task(self.gateway.acquire_slot())
        await asyncio.sleep(0)
        self.gateway.release_slot()
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError): await waiting
        self.assertEqual(self.gateway.active,0)
        self.assertFalse(self.gateway.waiters)
        self.assertTrue(await self.gateway.acquire_slot())
        self.gateway.release_slot()

    async def test_drain_after_grant_returns_reserved_slot(self):
        self.assertTrue(await self.gateway.acquire_slot())
        waiting=asyncio.create_task(self.gateway.acquire_slot())
        await asyncio.sleep(0)
        self.gateway.release_slot()
        self.gateway.draining=True
        self.assertFalse(await waiting)
        self.assertEqual(self.gateway.active,0)
        self.assertFalse(self.gateway.waiters)


class GatewayQueueConfigTests(unittest.TestCase):
    def test_queue_limits_require_bounded_integer_and_finite_timeout(self):
        backend=Backend('fixture','http://127.0.0.1:8731','real-model')
        for limit in (-1,65,1.5,True,'8',None):
            with self.subTest(queue_limit=limit), self.assertRaises(ValueError):
                Gateway(backend,KEY,queue_limit=limit)
        for seconds in (0,-1,3601,float('inf'),float('-inf'),float('nan'),
                        True,'120',None,10**500):
            with self.subTest(queue_seconds=seconds), self.assertRaises(ValueError):
                Gateway(backend,KEY,queue_seconds=seconds)

    def test_config_defaults_disable_queue_and_explicit_settings_enable_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'token.txt').write_text(KEY,encoding='ascii')
            path=root/'gateway.json'
            config={'schema':1,'token_file':'token.txt','backend':{
                'identifier':'fixture','upstream':'http://127.0.0.1:8731','model':'real-model'}}
            path.write_text(json.dumps(config),encoding='utf-8')
            default=load_config(path)
            self.assertEqual(default.queue_limit,0)
            self.assertEqual(default.queue_seconds,120)
            config.update(queue_limit=8,queue_seconds=120)
            path.write_text(json.dumps(config),encoding='utf-8')
            enabled=load_config(path)
            self.assertEqual(enabled.queue_limit,8)
            self.assertEqual(enabled.queue_seconds,120)


if __name__=='__main__': unittest.main()
