"""Own synchronous CREATE: only fixtures and existing loopback test servers."""
import asyncio
from dataclasses import replace
import json
import unittest
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer
from voice import bridge as implementation
from voice import caller_binding as authority
from voice.tests import test_caller_binding as fixtures
from voice.tests import test_native_caller_authority as wire

PATH = '/api/sn_voice_aia/local_voice_caller/create'
INSTANCE = 'https://soprasteriaassvsdemo14.service-now.com'
REQUEST = {'version':1,'requestId':'1'*32,'clientSessionId':'2'*32,'clientMessageId':'3'*32}
CONTROL = {'uiType':'ActionMsg','actionType':'CreateConversation','conversationId':'4'*32,
           'interactionId':'5'*32,'messageId':'6'*32}

def created(request):
    return {'requestId':request['requestId'],'clientSessionId':request['clientSessionId'],
            'userId':'voice-'+request['clientSessionId'],'body':[dict(CONTROL)]}


class OwnedCreateWireTests(unittest.IsolatedAsyncioTestCase):
    factory = wire.NativeAuthorityWireTests.factory

    async def invoke(self, data=None, response_options=None, **kwargs):
        method = getattr(authority,'create_native_caller_conversation',None)
        self.assertTrue(callable(method),'Own native CREATE transport is required')
        factory=self.factory(raw=json.dumps(data if data is not None else
            {'result':{'status':'success','created':created(REQUEST)}}).encode(),**(response_options or {}))
        def copied_factory(**options):
            http=factory(**options);post=http.post
            def copied_post(url,**options):
                options['headers']=dict(options['headers'])
                return post(url,**options)
            http.post=copied_post
            return http
        return await method(INSTANCE,PATH,'provider-secret',fixtures.TOKEN,
            dict(REQUEST),http_factory=copied_factory,**kwargs)

    async def test_original_bearer_only_exact_owned_post_and_stripped_request(self):
        self.assertEqual(await self.invoke(),created(REQUEST))
        self.assertEqual(len(self.sent),1)
        url,options=self.sent[0]
        self.assertEqual(url,INSTANCE+PATH)
        self.assertEqual(options['json'],REQUEST)
        self.assertEqual(options['headers']['Authorization'],fixtures.TOKEN)
        self.assertEqual(options['headers']['token'],'provider-secret')
        self.assertFalse(options['allow_redirects'])
        self.assertFalse(self.created[0]['trust_env'])

    async def test_ack_only_or_ambiguous_create_never_produces_binding(self):
        invalid=[{'result':{'status':'success'}}, {'result':{'status':'success','created':created(REQUEST)}}]
        invalid[1]['result']['created']['body']=[]
        for data in invalid:
            with self.subTest(data=data),self.assertRaises(ValueError):await self.invoke(data)
        for field,value in [('requestId','f'*32),('clientSessionId','f'*32),('userId','guest'),
                            ('nowSessionId',' invalid '),('email','leak@example.test')]:
            body=created(REQUEST);body[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                await self.invoke({'result':{'status':'success','created':body}})
        for control in [dict(CONTROL,interactionId=''),dict(CONTROL,messageId='bad'),
                        dict(CONTROL,uiType='OutputText'),dict(CONTROL,value='hidden output')]:
            body=created(REQUEST);body['body']=[control]
            with self.subTest(control=control),self.assertRaises(ValueError):
                await self.invoke({'result':{'status':'success','created':body}})

    async def test_changed_path_or_asserted_identity_cannot_send_any_request(self):
        method=getattr(authority,'create_native_caller_conversation',None)
        self.assertTrue(callable(method))
        for path in ('/api/sn_va_as_service/bot/integration',PATH+'?destination=other',
                     'https://evil.example'+PATH):
            factory=self.factory()
            with self.subTest(path=path),self.assertRaises(ValueError):
                await method(INSTANCE,path,'provider-secret',fixtures.TOKEN,
                    dict(REQUEST),http_factory=factory)
            self.assertEqual(self.sent,[])
        factory=self.factory()
        with self.assertRaises(ValueError):
            await method(INSTANCE,PATH,'provider-secret',fixtures.TOKEN,
                dict(REQUEST,email='asserted@example.test'),http_factory=factory)
        self.assertEqual(self.sent,[])

    async def test_wrong_instance_port_alias_or_suffix_is_refused_before_any_network(self):
        method=getattr(authority,'create_native_caller_conversation',None)
        self.assertTrue(callable(method))
        for instance in ('https://other.service-now.com',INSTANCE+':443',INSTANCE+':8443',
                         'https://soprasteriaassvsdemo14',INSTANCE+'.evil.example'):
            factory=self.factory(raw=json.dumps({'result':{'status':'success',
                'created':created(REQUEST)}}).encode())
            with self.subTest(instance=instance),self.assertRaises(ValueError):
                await method(instance,PATH,'provider-secret',fixtures.TOKEN,dict(REQUEST),
                    http_factory=factory)
            self.assertEqual(self.created,[])
            self.assertEqual(self.sent,[])

    async def test_denial_redirect_and_encoding_fail_once_without_retry(self):
        for options in ({'status':401},{'status':403},{'status':302},
                        {'headers':{'Content-Type':'application/json','Content-Encoding':'gzip'}}):
            with self.subTest(options=options),self.assertRaises(ValueError):
                await self.invoke(response_options=options)
            self.assertEqual(len(self.sent),1)

    async def test_create_claim_is_once_but_distinct_refresh_still_consumes_once(self):
        ticket=authority.CallerBootstrapCredential(fixtures.TOKEN,seconds=1)
        self.addCleanup(ticket.clear)
        method=getattr(ticket,'claim_create',None);self.assertTrue(callable(method))
        self.assertEqual(method()[0],fixtures.TOKEN)
        self.assertTrue(ticket.available)
        with self.assertRaises(ValueError):method()
        self.assertEqual(ticket.take()[0],fixtures.TOKEN)
        self.assertFalse(ticket.available)
        with self.assertRaises(ValueError):ticket.take()


class OwnedCreateBridgeTests(unittest.IsolatedAsyncioTestCase):
    start=fixtures.CallerBridgeTests.start

    async def asyncSetUp(self):
        await fixtures.CallerBridgeTests.asyncSetUp(self)
        self.bridge.settings.instance_url=INSTANCE
        self.bridge.settings.caller_create_api_path=PATH
        self.callbacks=TestClient(TestServer(self.bridge.callback_app()))
        await self.callbacks.start_server();self.addAsyncCleanup(self.callbacks.close)
        async def own(*args,**kwargs):return created(args[4])
        self.creator=AsyncMock(side_effect=own)
        self.refresher=AsyncMock()
        self.enterContext(patch('voice.bridge.create_native_caller_conversation',self.creator,create=True))
        self.enterContext(patch('voice.bridge.refresh_native_caller_session',self.refresher))

    async def settle(self):
        tasks=list(self.bridge.bootstrap_tasks)
        if tasks:await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),1)

    async def callback(self,control=None):
        session=next(iter(self.bridge.sessions.values()))
        request=self.creator.await_args.args[4]
        return await self.callbacks.post('/callback',json={
            'requestId':request['requestId'],'clientSessionId':session.sid,'userId':session.user_id,
            'body':[control or dict(CONTROL)]},headers={'Authorization':'Bearer callback-secret'})

    async def test_sync_create_bound_to_private_cookie_then_one_distinct_refresh_and_start(self):
        self.assertEqual((await self.start()).status,202)
        await self.settle();self.creator.assert_awaited_once();self.refresher.assert_awaited_once()
        session=next(iter(self.bridge.sessions.values()))
        self.assertEqual(session.user_id,'voice-'+session.sid)
        self.assertEqual([v.get('action') for v in self.sent],['START_CREATED_CONVERSATION'])
        self.assertEqual(session.conversation_binding.conversation_id,CONTROL['conversationId'])
        self.assertIsNone(session.caller_bootstrap)
        self.assertEqual(self.creator.await_args.args[3],fixtures.TOKEN)
        self.assertEqual(self.refresher.await_args.args[4],fixtures.TOKEN)
        self.assertNotIn(fixtures.TOKEN,repr(session))

    async def test_missing_sync_result_never_falls_back_or_starts(self):
        self.creator.side_effect=ValueError('no genuine create tuple')
        self.assertGreaterEqual((await self.start()).status,400)
        await self.settle();self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()
        session=next(iter(self.bridge.sessions.values()))
        self.assertTrue(session.failed);self.assertIsNone(session.caller_bootstrap)

    async def test_callback_cannot_start_before_owned_result_or_repeat_transition(self):
        entered,release=asyncio.Event(),asyncio.Event()
        async def own(*args,**kwargs):entered.set();await release.wait();return created(args[4])
        self.creator.side_effect=own
        starting=asyncio.create_task(self.start());await asyncio.wait_for(entered.wait(),1)
        await self.callback();await self.settle()
        self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()
        release.set();await starting;await self.settle()
        await self.callback();await self.settle()
        self.assertEqual(self.refresher.await_count,1)
        self.assertEqual(len(self.sent),1)

    async def test_changed_caller_during_owned_create_never_binds_or_starts(self):
        async def own(*args,**kwargs):
            session=next(iter(self.bridge.sessions.values()));session.caller_user_id='f'*32
            return created(args[4])
        self.creator.side_effect=own
        self.assertGreaterEqual((await self.start()).status,400)
        await self.settle();self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()

    async def test_changed_profile_during_owned_create_never_binds_or_starts(self):
        async def own(*args,**kwargs):
            session=next(iter(self.bridge.sessions.values()))
            session.voice_context=dict(session.voice_context,global_context_profile='f'*32)
            return created(args[4])
        self.creator.side_effect=own
        self.assertGreaterEqual((await self.start()).status,400)
        await self.settle();self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()

    async def test_changed_current_request_during_owned_create_never_binds(self):
        async def own(*args,**kwargs):
            session=next(iter(self.bridge.sessions.values()));session.requests.append('f'*32)
            return created(args[4])
        self.creator.side_effect=own
        self.assertGreaterEqual((await self.start()).status,400)
        await self.settle();self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()

    async def test_replaced_private_cookie_session_during_create_never_binds(self):
        async def own(*args,**kwargs):
            old=next(iter(self.bridge.sessions.values()))
            self.bridge.sessions[old.sid]=implementation.Conversation(sid=old.sid)
            return created(args[4])
        self.creator.side_effect=own
        self.assertGreaterEqual((await self.start()).status,400)
        await self.settle();self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()

    async def test_returned_wrong_tuple_fails_before_refresh(self):
        async def own(*args,**kwargs):
            result=created(args[4]);result['body'][0]['interactionId']=''
            return result
        self.creator.side_effect=own
        self.assertGreaterEqual((await self.start()).status,400)
        await self.settle();self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()

    async def test_owned_create_cancellation_marks_failed_and_retires_credential(self):
        self.creator.side_effect=asyncio.CancelledError()
        await asyncio.gather(asyncio.create_task(self.start()),return_exceptions=True)
        session=next(iter(self.bridge.sessions.values()))
        self.assertTrue(session.failed);self.assertIsNone(session.caller_bootstrap)
        self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()

    async def test_start_message_and_end_b2b_headers_never_contain_original_bearer(self):
        headers=[];post=self.bridge.http.post
        def record(url,**options):headers.append(dict(options.get('headers',{})));return post(url,**options)
        self.enterContext(patch.object(self.bridge.http,'post',side_effect=record))
        await self.start();await self.settle()
        session=next(iter(self.bridge.sessions.values()))
        start=self.sent[-1]
        await self.callbacks.post('/callback',json={'requestId':start['requestId'],
            'clientSessionId':session.sid,'userId':session.user_id,
            'body':[{'uiType':'InputText','label':'Wie heißt die Testperson?'}]},
            headers={'Authorization':'Bearer callback-secret'})
        response=await self.ui.post('/api/message',json={'text':'Synthetischer Name'},headers=self.headers)
        self.assertEqual(response.status,202)
        self.assertEqual((await self.ui.post('/api/end',json={},headers=self.headers)).status,202)
        await session.cleanup_task
        self.assertEqual([v.get('action') for v in self.sent],['START_CREATED_CONVERSATION',None,'END_CONVERSATION'])
        self.assertEqual(len(headers),3)
        for header in headers:
            self.assertNotIn('Authorization',header)
            self.assertNotIn(fixtures.HEADER,header)
            self.assertNotIn(fixtures.TOKEN,repr(header))

    async def test_end_drains_pending_owned_create_without_start_or_fallback(self):
        entered,release=asyncio.Event(),asyncio.Event()
        async def own(*args,**kwargs):
            entered.set()
            await release.wait()
            return created(args[4])
        self.creator.side_effect=own
        starting=asyncio.create_task(self.start())
        await asyncio.wait_for(entered.wait(),1)
        session=next(iter(self.bridge.sessions.values()))
        response=await asyncio.wait_for(self.ui.post('/api/end',json={},headers=self.headers),1)
        self.assertEqual(response.status,202)
        self.assertFalse(session.caller_create_task.done())
        self.assertEqual(self.sent,[])
        release.set()
        await starting
        await session.cleanup_task
        self.assertEqual([v.get('action') for v in self.sent],['END_CONVERSATION'])
        self.assertFalse(session.ended)
        self.creator.assert_awaited_once();self.refresher.assert_not_awaited()

    async def test_expiration_bounds_pending_create_and_retains_uncertain_ownership(self):
        entered,cancelled=asyncio.Event(),asyncio.Event()
        async def own(*args,**kwargs):
            entered.set()
            try:await asyncio.Event().wait()
            except asyncio.CancelledError:cancelled.set();raise
        self.creator.side_effect=own
        with patch('voice.bridge.CALLER_BOOTSTRAP_SECONDS',.05):
            starting=asyncio.create_task(self.start())
            await asyncio.wait_for(entered.wait(),1)
        await asyncio.wait_for(cancelled.wait(),1)
        response=await starting
        self.assertEqual(response.status,502)
        session=next(iter(self.bridge.sessions.values()))
        self.assertTrue(session.failed);self.assertIsNone(session.caller_bootstrap)
        self.assertIsNotNone(session.caller_create_task)
        self.assertEqual(self.sent,[]);self.refresher.assert_not_awaited()
        response=await self.ui.post('/api/end',json={},headers=self.headers)
        self.assertEqual(response.status,202)
        self.assertIn(session.sid,self.bridge.sessions)

    async def test_reset_retains_pending_create_and_original_private_cookie(self):
        entered,release=asyncio.Event(),asyncio.Event()
        async def own(*args,**kwargs):
            entered.set()
            await release.wait()
            return created(args[4])
        self.creator.side_effect=own
        starting=asyncio.create_task(self.start());await asyncio.wait_for(entered.wait(),1)
        old=next(iter(self.bridge.sessions.values()))
        response=await asyncio.wait_for(self.ui.post('/api/reset',json={},headers=self.headers),1)
        self.assertEqual(response.status,202)
        self.assertIs(self.bridge.sessions[old.sid],old)
        self.assertTrue(old.caller_user_id)
        self.assertEqual(self.sent,[])
        release.set()
        await starting
        await old.cleanup_task
        self.assertEqual([v.get('action') for v in self.sent],['END_CONVERSATION'])
        self.refresher.assert_not_awaited()


class OwnedCreateConfigurationTests(unittest.TestCase):
    def test_default_remains_unselected_and_arbitrary_create_destinations_are_rejected(self):
        self.assertEqual(implementation.Settings().caller_create_api_path,'')
        for path in ('/api/sn_va_as_service/bot/integration',PATH+'/',PATH+'?x=1','https://evil.example'+PATH):
            settings=implementation.Settings(user_id='fixture',instance_url='https://instance.example.test',
                caller_create_api_path=path)
            with self.subTest(path=path),self.assertRaises(ValueError):
                implementation.Bridge(settings,'provider-secret','audio-secret','callback-secret')


if __name__=='__main__':unittest.main()
