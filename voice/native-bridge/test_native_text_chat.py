"""No-network native Chat contract tests with an owned fake Dialog."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from aiohttp import WSMsgType, web
from assistant_settings import CallSettings
from native_text_chat import NativeTextChat

class Socket:
    def __init__(self):
        self.sent=[]; self.incoming=asyncio.Queue(); self.closed=False
    async def prepare(self,request): pass
    async def send_json(self,value): self.sent.append(value)
    def __aiter__(self): return self
    async def __anext__(self):
        msg=await self.incoming.get()
        if msg is None: raise StopAsyncIteration
        return SimpleNamespace(type=WSMsgType.TEXT,data=json.dumps(msg))
    async def close(self):
        if not self.closed: self.closed=True; self.incoming.put_nowait(None)

class Dialog:
    def __init__(self,config,settings):
        self.call_settings=settings; self.bound=[]; self.inputs=[]; self.must_reset=False
        self.metadata=dict(conversation_id='a'*32,interaction_id='b'*32)
        self.open_gate=asyncio.Event(); self.open_gate.set()
        self.cleanup_gate=asyncio.Event(); self.cleanup_gate.set()
        self.closes=0; self.shutdowns=0; self._call_owned=False; self.started=False
    def bind_caller_authorization(self,value): self.bound.append(value)
    async def open(self):
        self.started=True; await self.open_gate.wait(); return ['Für wen ist der Laptop?']
    async def turn(self,text,on_reply=None):
        self.inputs.append(text); await on_reply('Welchen Nachnamen meinten Sie?'); return ['unused duplicate']
    async def close(self): self.closes+=1; self.must_reset=not self.cleanup_gate.is_set()
    async def wait_owned_cleanup(self): await self.cleanup_gate.wait(); self.must_reset=False
    async def shutdown(self): self.shutdowns+=1

class TextChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.socket=Socket(); self.active=set(); self.dialogs=[]; self.tasks=[]; self.authorized=[]; self.readiness=0
        self.settings=Mock(spec=CallSettings); self.settings.introduction='Guten Tag.'
        async def authorize(request,config,http,**kwargs):
            self.authorized.append(kwargs); return self.settings
        async def ready(): self.readiness+=1
        def factory(config,settings):
            value=Dialog(config,settings); self.dialogs.append(value); return value
        self.manager=NativeTextChat(SimpleNamespace(max_call_seconds=30),object(),self.active,
            authorize,factory,before_create=ready,websocket_factory=lambda **kwargs:self.socket)
        self.request=SimpleNamespace(query={'auth_token':'synthetic-token'})
    async def asyncTearDown(self):
        for dialog in self.dialogs: dialog.open_gate.set(); dialog.cleanup_gate.set()
        await self.manager.shutdown()
        for task in self.tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
    async def until(self,predicate):
        async with asyncio.timeout(1):
            while not predicate(): await asyncio.sleep(0)
    def start(self):
        task=asyncio.create_task(self.manager.handle(self.request)); self.tasks.append(task); return task
    async def test_wire_original_submission_and_owned_cleanup(self):
        task=self.start(); await self.until(lambda:any(x['type']=='metadata' for x in self.socket.sent))
        self.socket.incoming.put_nowait({'type':'user_query','content':'  Lea Oltmer?  '})
        await self.until(lambda:bool(self.dialogs[0].inputs))
        await self.socket.close(); await task
        d=self.dialogs[0]
        self.assertEqual(d.inputs,['  Lea Oltmer?  ']); self.assertEqual(d.bound,['Bearer synthetic-token'])
        self.assertTrue(d._call_owned); self.assertEqual(d.closes,1); self.assertEqual(d.shutdowns,1)
        self.assertEqual(self.authorized,[{'with_settings':True}]); self.assertEqual(self.readiness,1)
        self.assertEqual(self.socket.sent[0]['type'],'connected')
        self.assertEqual([x['content'] for x in self.socket.sent if x['type']=='static'],
            ['Guten Tag.','Für wen ist der Laptop?','Welchen Nachnamen meinten Sie?'])
        self.assertEqual(next(x for x in self.socket.sent if x['type']=='metadata')['metadata'],d.metadata)
        self.assertFalse(self.active)
    async def test_auth_failure_and_shared_capacity_never_create_dialog(self):
        self.manager.authorize=lambda *a,**kw: asyncio.sleep(0,result=False)
        with self.assertRaises(web.HTTPUnauthorized): await self.manager.handle(self.request)
        self.assertFalse(self.active); self.assertFalse(self.dialogs)
        self.active.add(object())
        with self.assertRaises(web.HTTPServiceUnavailable): await self.manager.handle(self.request)
        self.assertFalse(self.dialogs)
        self.active.clear()
    async def test_disconnect_during_open_and_pending_cleanup_keep_capacity(self):
        task=self.start(); await self.until(lambda:bool(self.dialogs))
        d=self.dialogs[0]; d.open_gate.clear(); d.cleanup_gate.clear()
        await self.until(lambda:d.started)
        await self.socket.close(); await self.until(lambda:d.closes==1)
        self.assertEqual(len(self.active),1); self.assertEqual(d.shutdowns,0)
        d.cleanup_gate.set(); await task
        self.assertFalse(self.active); self.assertEqual(d.shutdowns,1); self.assertEqual(d.inputs,[])
    async def test_invalid_input_cannot_submit(self):
        task=self.start(); await self.until(lambda:bool(self.dialogs)); self.dialogs[0].open_gate.clear()
        self.socket.incoming.put_nowait({'type':'user_query','content':'x','extra':True})
        await task
        self.assertEqual(self.dialogs[0].inputs,[])
        self.assertTrue(any(x['type']=='error' for x in self.socket.sent)); self.assertFalse(self.active)
    async def test_bounded_startup_queue_never_submits_overflow(self):
        task=self.start(); await self.until(lambda:bool(self.dialogs))
        d=self.dialogs[0]; d.open_gate.clear()
        for index in range(9):
            self.socket.incoming.put_nowait({'type':'user_query','content':str(index)})
        await task
        self.assertEqual(d.inputs,[])
        self.assertTrue(any(x['type']=='error' for x in self.socket.sent))
        self.assertFalse(self.active)
    async def test_pending_admission_reserves_shared_capacity(self):
        gate=asyncio.Event()
        async def authorize(*args,**kwargs):
            await gate.wait(); return self.settings
        self.manager.authorize=authorize
        task=self.start(); await self.until(lambda:bool(self.active))
        with self.assertRaises(web.HTTPServiceUnavailable):
            await self.manager.handle(self.request)
        self.assertFalse(self.dialogs)
        gate.set(); await self.until(lambda:bool(self.dialogs))
        await self.socket.close(); await task
        self.assertFalse(self.active)
    async def test_cancel_handler_keeps_owned_cleanup_alive(self):
        task=self.start(); await self.until(lambda:bool(self.dialogs)); d=self.dialogs[0]
        d.cleanup_gate.clear(); task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        await self.until(lambda:d.closes==1)
        self.assertEqual(len(self.active),1)
        d.cleanup_gate.set(); await self.until(lambda:not self.active)
        self.assertEqual(d.shutdowns,1)

if __name__=='__main__': unittest.main()
