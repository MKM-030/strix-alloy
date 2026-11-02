"""Owned native CREATE must refresh its already-linked session before START."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer
from voice.tests import test_caller_binding as fixtures
TOKEN=fixtures.TOKEN

CONVERSATION='3'*32
INTERACTION='4'*32
MESSAGE='5'*32


class CallerRefreshTests(unittest.IsolatedAsyncioTestCase):
    start=fixtures.CallerBridgeTests.start

    async def asyncSetUp(self):
        await fixtures.CallerBridgeTests.asyncSetUp(self)
        self.callbacks=TestClient(TestServer(self.bridge.callback_app()))
        await self.callbacks.start_server();self.addAsyncCleanup(self.callbacks.close)
        self.refresher=AsyncMock()
        self.enterContext(patch('voice.bridge.refresh_native_caller_session',self.refresher,create=True))

    async def create_callback(self,*,control=None,**changes):
        request=self.sent[0]
        data={'clientSessionId':request['clientSessionId'],'userId':request['userId'],
            'requestId':request['requestId'],'body':[control or {'uiType':'ActionMsg','actionType':'CreateConversation',
                'conversationId':CONVERSATION,'interactionId':INTERACTION,'messageId':MESSAGE}]}
        data.update(changes)
        return await self.callbacks.post('/callback',json=data,headers={'Authorization':'Bearer callback-secret'})

    async def settle(self):
        tasks=list(self.bridge.bootstrap_tasks)
        if tasks:await asyncio.wait_for(asyncio.gather(*tasks),1)

    async def test_refresh_fences_start_and_uses_original_credential_once(self):
        await self.start();self.assertEqual(len(self.sent),1)
        entered,release=asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):entered.set();await release.wait()
        self.refresher.side_effect=refresh
        self.assertEqual((await self.create_callback()).status,200)
        for _ in range(50):
            if entered.is_set():break
            await asyncio.sleep(.002)
        self.assertTrue(entered.is_set(),'Matching CREATE must invoke its native session refresh')
        self.assertEqual(len(self.sent),1,'START must wait for the native refresh request')
        release.set();await self.settle()
        self.assertEqual([x.get('action') for x in self.sent],['CREATE_CONVERSATION','START_CREATED_CONVERSATION'])
        self.assertEqual(self.resolve.await_count,1);self.assertEqual(self.refresher.await_count,1)
        args=self.refresher.await_args.args
        self.assertEqual(args[4],TOKEN)
        self.assertEqual(args[5],{'conversation_id':CONVERSATION,'interaction_id':INTERACTION,'create_message_id':MESSAGE})
        session=next(iter(self.bridge.sessions.values()))
        self.assertIsNone(getattr(session,'caller_bootstrap',None))
        self.assertNotIn(TOKEN,repr(session))
        self.assertEqual((await self.create_callback()).status,200)
        await self.settle();self.assertEqual(self.refresher.await_count,1)

    async def test_refresh_failure_never_starts_or_retries_and_retires_credential(self):
        self.refresher.side_effect=ValueError('fixed native failure')
        await self.start();await self.create_callback();await self.settle()
        self.assertEqual(len(self.sent),1)
        session=next(iter(self.bridge.sessions.values()))
        self.assertTrue(session.failed)
        self.assertIsNone(getattr(session,'caller_bootstrap',None))
        await self.create_callback();await self.settle();self.assertEqual(self.refresher.await_count,1)

    async def test_foreign_or_incomplete_create_does_not_spend_authorization(self):
        await self.start()
        self.assertEqual((await self.create_callback(requestId='f'*32)).status,200)
        await self.settle();self.refresher.assert_not_awaited();self.assertEqual(len(self.sent),1)
        await self.create_callback(control={'uiType':'ActionMsg','actionType':'CreateConversation',
            'conversationId':CONVERSATION,'messageId':MESSAGE})
        await self.settle();self.refresher.assert_not_awaited();self.assertEqual(len(self.sent),1)

    async def test_expired_bootstrap_fails_closed_and_clears_credential_without_traffic(self):
        with patch('voice.bridge.CALLER_BOOTSTRAP_SECONDS',.02,create=True):
            await self.start()
        await asyncio.sleep(.04)
        session=next(iter(self.bridge.sessions.values()))
        self.assertTrue(session.failed)
        ticket=getattr(session,'caller_bootstrap',None)
        self.assertTrue(ticket is None or not ticket.available)
        await self.create_callback();await self.settle();self.refresher.assert_not_awaited()
        self.assertEqual(len(self.sent),1)

    async def test_end_cancels_only_pending_refresh_and_never_dispatches_start(self):
        entered,release,cancelled=asyncio.Event(),asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):
            entered.set()
            try:await release.wait()
            except asyncio.CancelledError:cancelled.set();raise
        self.refresher.side_effect=refresh
        await self.start();await self.create_callback();await asyncio.wait_for(entered.wait(),1)
        ending=asyncio.create_task(self.ui.post('/api/end',json={},headers=self.headers))
        try:
            for _ in range(50):
                if ending.done():break
                await asyncio.sleep(.002)
            self.assertTrue(ending.done(),'END must retire the outstanding bootstrap credential promptly')
            self.assertTrue(cancelled.is_set())
            self.assertEqual((await ending).status,200)
            self.assertEqual([v.get('action') for v in self.sent],['CREATE_CONVERSATION','END_CONVERSATION'])
        finally:
            release.set();await ending

    async def test_changed_private_caller_while_refresh_waits_never_starts(self):
        entered,release=asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):entered.set();await release.wait()
        self.refresher.side_effect=refresh
        await self.start();await self.create_callback();await asyncio.wait_for(entered.wait(),1)
        session=next(iter(self.bridge.sessions.values()))
        session.caller_user_id='2'*32
        session.caller_email='changed@example.test'
        release.set();await self.settle()
        self.assertEqual(len(self.sent),1,'A refresh acknowledgement cannot authorize a changed caller')
        self.assertTrue(session.failed)

    async def test_changed_conversation_binding_while_refresh_waits_never_starts(self):
        from dataclasses import replace
        entered,release=asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):entered.set();await release.wait()
        self.refresher.side_effect=refresh
        await self.start();await self.create_callback();await asyncio.wait_for(entered.wait(),1)
        session=next(iter(self.bridge.sessions.values()))
        session.conversation_binding=replace(session.conversation_binding,conversation_id='9'*32)
        release.set();await self.settle()
        self.assertEqual(len(self.sent),1)
        self.assertTrue(session.failed)

    async def test_replaced_cookie_session_while_refresh_waits_never_starts(self):
        from voice.bridge import Conversation
        entered,release=asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):entered.set();await release.wait()
        self.refresher.side_effect=refresh
        await self.start();await self.create_callback();await asyncio.wait_for(entered.wait(),1)
        session=next(iter(self.bridge.sessions.values()))
        replacement=Conversation(sid=session.sid)
        self.bridge.sessions[session.sid]=replacement
        release.set();await self.settle()
        self.assertEqual(len(self.sent),1)
        self.assertTrue(session.failed)
        self.assertFalse(replacement.started)

    async def test_reset_retires_pending_refresh_before_creating_new_cookie_session(self):
        entered,release,cancelled=asyncio.Event(),asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):
            entered.set()
            try:await release.wait()
            except asyncio.CancelledError:cancelled.set();raise
        self.refresher.side_effect=refresh
        await self.start();await self.create_callback();await asyncio.wait_for(entered.wait(),1)
        old=next(iter(self.bridge.sessions.values()))
        response=await asyncio.wait_for(self.ui.post('/api/reset',json={},headers=self.headers),1)
        self.assertEqual(response.status,200)
        self.assertTrue(cancelled.is_set())
        self.assertNotIn(old.sid,self.bridge.sessions)
        self.assertEqual(old.caller_email,'')
        self.assertEqual(old.caller_user_id,'')
        self.assertEqual([v.get('action') for v in self.sent],['CREATE_CONVERSATION','END_CONVERSATION'])
        self.assertFalse(next(iter(self.bridge.sessions.values())).started)

    async def test_shutdown_cancels_pending_metadata_refresh_without_starting(self):
        entered,release,cancelled=asyncio.Event(),asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):
            entered.set()
            try:await release.wait()
            except asyncio.CancelledError:cancelled.set();raise
        self.refresher.side_effect=refresh
        await self.start();await self.create_callback();await asyncio.wait_for(entered.wait(),1)
        session=next(iter(self.bridge.sessions.values()))
        await asyncio.wait_for(self.ui.close(),1)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(len(self.sent),1)
        self.assertIsNone(session.caller_bootstrap)
        self.assertEqual(session.caller_user_id,'')
        self.assertEqual(session.caller_email,'')

    async def test_refresh_acknowledgement_after_absolute_deadline_never_starts(self):
        entered,release=asyncio.Event(),asyncio.Event()
        async def refresh(*args,**kwargs):entered.set();await release.wait()
        self.refresher.side_effect=refresh
        with patch('voice.bridge.CALLER_BOOTSTRAP_SECONDS',.2):
            await self.start()
        await self.create_callback();await asyncio.wait_for(entered.wait(),1)
        self.assertLessEqual(self.refresher.await_args.kwargs['timeout_seconds'],.2)
        await asyncio.sleep(.25)
        release.set();await self.settle()
        session=next(iter(self.bridge.sessions.values()))
        self.assertEqual(len(self.sent),1)
        self.assertTrue(session.failed)


if __name__=='__main__':unittest.main()
