"""Offline integration checks for per-call native assistant settings."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from native_bridge import Config, Dialog, Speech, NativeCall, authorize
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings

A = 'a'*32
P = 'b'*32
G = 'c'*32
PRIVATE = 'PRIVATE_POLICY_DO_NOT_LOG'
CONTEXT = {'interaction_requester_session_language':'en', 'interaction_user_language':'en',
    'requester_session_language':'en', 'voice_assistant':A, 'interaction_ai_voice':'true'}

class CallSettingsStub:
    language = 'en'
    introduction = 'Hello from the configured assistant.'
    vad_start_ms = 80
    vad_stop_ms = 200
    max_call_seconds = 300
    unsupported_metadata = {'vad.confidence':.7,'vad.min_volume':.3}
    def native_context(self): return dict(CONTEXT)
    def asr_context(self): return {'language':self.language,'terms':['Smart Country Convention']}
    def select_language(self, text):
        if text == 'Bitte Deutsch':
            self.language = 'de'
            return True
        return False

class Response:
    status=200
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False
    async def json(self): return {'text':'Recognized'}
class HTTP:
    def post(self, url, **kwargs):
        self.kwargs=kwargs
        return Response()

class NativeSettingsIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_asr_uses_per_call_language_terms_without_native_cloud_voice(self):
        http=HTTP()
        speech=Speech(http,Config())
        speech.call_settings=CallSettingsStub()
        await speech.transcribe(bytes(3200))
        fields={part[0]['name']:part[2] for part in http.kwargs['data']._fields}
        self.assertEqual(fields['language'],'en')
        self.assertEqual(fields['prompt'],'Smart Country Convention')
        self.assertNotIn('voice_id',fields)
        speech.call_settings.language='de'
        await speech.transcribe(bytes(3200))
        fields={part[0]['name']:part[2] for part in http.kwargs['data']._fields}
        self.assertEqual(fields['language'],'de')

    async def test_dialog_forwards_context_separately_from_user_text(self):
        class Capturing(Dialog):
            def __init__(self):
                super().__init__(Config())
                self.http=object()
                self.sent=[]
            async def request(self,method,path,**kwargs):
                if method=='POST': self.sent.append((path,kwargs['json']))
                if path=='/api/session':
                    return {'csrf':'owned','serviceNowEnabled':True,'started':False}
                return {'cursor':0,'events':[],'busy':False}
        dialog=Capturing()
        dialog.call_settings=CallSettingsStub()
        await dialog.open()
        await dialog.turn('Real user intent')
        self.assertEqual(dialog.sent[0],('/api/start',{'voice_context':CONTEXT}))
        self.assertEqual(dialog.sent[1],('/api/message',{'text':'Real user intent','voice_context':CONTEXT}))
        self.assertNotIn(PRIVATE,dialog.sent[1][1]['text'])

    async def test_queued_turn_keeps_language_selected_when_audio_was_recognized(self):
        class Capturing(Dialog):
            def __init__(self):
                super().__init__(Config())
                self.sent=[]
            async def request(self,method,path,**kwargs):
                if path=='/api/message': self.sent.append(kwargs['json'])
                return {'cursor':0,'events':[],'busy':False}
        dialog=Capturing()
        dialog.call_settings=CallSettingsStub()
        first_context=dialog.call_settings.native_context()
        first_context.update(interaction_requester_session_language='en',interaction_user_language='en',requester_session_language='en')
        dialog.call_settings.language='de'
        await dialog.turn('Earlier English utterance',voice_context=first_context)
        self.assertEqual(dialog.sent[0]['voice_context']['requester_session_language'],'en')
        self.assertEqual(dialog.sent[0]['text'],'Earlier English utterance')

    async def test_native_call_owns_configured_timing_greeting_and_limits(self):
        class FakeDialog:
            metadata={}
            async def close(self): pass
        original=Config(greeting='old',vad_silence_ms=1200,max_call_seconds=1800)
        settings=CallSettingsStub()
        call=NativeCall(original,object(),FakeDialog(),call_settings=settings)
        try:
            self.assertIsNot(call.config,original)
            self.assertEqual(call.config.greeting,settings.introduction)
            self.assertEqual(call.config.vad_silence_ms,200)
            self.assertEqual(call.config.max_call_seconds,300)
            self.assertEqual(call.config.vad_threshold,original.vad_threshold)
            self.assertEqual(original.greeting,'old')
            self.assertEqual(original.vad_silence_ms,1200)
        finally: await call.close()

    async def test_inactivity_waits_for_audio_to_drain_and_never_cancels_native_turn(self):
        class IdleSettings(CallSettingsStub):
            inactivity_seconds=.03
        class FakeDialog:
            metadata={}
            async def open(self): return []
            async def close(self): pass
        settings=IdleSettings()
        settings.introduction=''
        call=NativeCall(Config(),object(),FakeDialog(),call_settings=settings)
        call.playback.put(bytes(960),0)
        worker=call.spawn(call.process_turns())
        try:
            await asyncio.sleep(.06)
            self.assertFalse(call.input_ended.is_set())
            call.playback.read(960)
            await asyncio.wait_for(call.input_ended.wait(),.3)
            await asyncio.wait_for(worker,.3)
            self.assertTrue(call.turns_settled.is_set())
        finally: await call.close()

    async def test_content_tts_stage_timings_are_numeric_and_do_not_log_dialogue(self):
        finished=asyncio.Event()
        class FakeSpeech:
            async def transcribe(self,pcm): return PRIVATE
            async def synthesize(self,text):
                yield bytes(960)
                finished.set()
        class FakeDialog:
            metadata={}
            async def open(self): return []
            async def turn(self,text,on_reply=None): await on_reply(PRIVATE)
            async def close(self): pass
        call=NativeCall(Config(),FakeSpeech(),FakeDialog())
        with self.assertLogs('native-voice',level='INFO') as logs:
            call.spawn(call.process_turns())
            await call.turns.put((0,bytes(3200)))
            await asyncio.wait_for(finished.wait(),.5)
            await call.close()
        logged=' '.join(logs.output)
        self.assertRegex(logged,r'stage=callback_content turn=1 backend_elapsed_ms=[0-9]+')
        self.assertRegex(logged,r'stage=content_tts_first_chunk turn=1 elapsed_ms=[0-9]+ backend_elapsed_ms=[0-9]+ bytes=960')
        self.assertRegex(logged,r'stage=content_tts_end turn=1 elapsed_ms=[0-9]+ chunks=1 bytes=960')
        self.assertNotIn(PRIVATE,logged)

    async def test_idle_uses_only_explicit_configured_goodbye_and_drains_it_before_close(self):
        class GoodbyeSettings(CallSettingsStub):
            inactivity_seconds=.02
            configured_goodbye='Configured localized goodbye.'
            introduction=''
        class FakeSpeech:
            def __init__(self): self.spoken=[]
            async def synthesize(self,text):
                self.spoken.append(text)
                yield bytes(960)
        class FakeDialog:
            metadata={}
            async def open(self): return []
            async def close(self): pass
        speech=FakeSpeech(); call=NativeCall(Config(),speech,FakeDialog(),call_settings=GoodbyeSettings())
        async def drain():
            while not call.input_ended.is_set():
                call.playback.read(960)
                await asyncio.sleep(.005)
        drain_task=asyncio.create_task(drain())
        worker=call.spawn(call.process_turns())
        try:
            await asyncio.wait_for(call.input_ended.wait(),.5)
            await asyncio.wait_for(worker,.5)
            self.assertEqual(speech.spoken,['Configured localized goodbye.'])
            self.assertEqual(len(call.playback.data),0)
        finally:
            drain_task.cancel(); await asyncio.gather(drain_task,return_exceptions=True)
            await call.close()

class LoopbackSettingsContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent=[]
        async def receive(request):
            self.sent.append(await request.json())
            return web.json_response({'status':'success'})
        app=web.Application(); app.router.add_post('/bot',receive)
        self.bot=TestServer(app); await self.bot.start_server()
        self.bridge=Bridge(Settings(instance_url='https://instance.example.test',user_id='demo',defer_start_until_message=True),'unit-sn','unit-audio','unit-callback')
        self.bridge.bot_url=str(self.bot.make_url('/bot'))
        self.ui=TestClient(TestServer(self.bridge.ui_app()),cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin=str(self.ui.make_url('/')).rstrip('/')
        info=await (await self.ui.get('/api/session')).json()
        self.headers={'Origin':self.bridge.origin,'X-CSRF-Token':info['csrf']}
    async def asyncTearDown(self):
        await self.ui.close(); await self.bot.close()
    async def post(self,path,payload,headers=None):
        return await self.ui.post(path,json=payload,headers=self.headers if headers is None else headers)
    async def test_private_start_context_reaches_all_three_native_language_keys(self):
        self.assertEqual((await self.post('/api/start',{'voice_context':CONTEXT})).status,202)
        await self.post('/api/message',{'text':'Actual name'})
        self.assertEqual(self.sent[0]['contextVariables'],CONTEXT)
        self.assertEqual(self.sent[0]['message']['text'],'Actual name')
        session=next(iter(self.bridge.sessions.values()))
        self.bridge.consume(session,{'body':[{'uiType':'InputText'}]})
        updated=dict(CONTEXT,interaction_requester_session_language='de',interaction_user_language='de',requester_session_language='de')
        await self.post('/api/message',{'text':'Bitte Deutsch','voice_context':updated})
        self.assertEqual(self.sent[1]['contextVariables'],updated)
    async def test_rejects_bad_context_before_start_and_keeps_csrf_guard(self):
        invalid=[dict(CONTEXT,voice_assistant='wrong'),dict(CONTEXT,requester_session_language='es'),dict(CONTEXT,global_deployment_id=P),dict(CONTEXT,voice_assistant_system_message='x'*16001)]
        for context in invalid:
            self.assertEqual((await self.post('/api/start',{'voice_context':context})).status,400)
        self.assertEqual((await self.post('/api/start',{'voice_context':CONTEXT},headers={'Origin':self.bridge.origin})).status,403)
        self.assertFalse(next(iter(self.bridge.sessions.values())).started)
    async def test_private_context_preserves_authorized_extended_language_tag(self):
        tag='de-DE-u-co-phonebk-x-test'
        context=dict(CONTEXT,interaction_requester_session_language=tag,interaction_user_language=tag,requester_session_language=tag)
        self.assertEqual((await self.post('/api/start',{'voice_context':context})).status,202)
        await self.post('/api/message',{'text':'Real intent'})
        self.assertEqual(self.sent[0]['contextVariables']['requester_session_language'],tag)

    async def test_new_private_cookie_session_does_not_inherit_context(self):
        await self.post('/api/start',{'voice_context':CONTEXT})
        response=await self.post('/api/reset',{})
        info=await response.json()
        self.headers['X-CSRF-Token']=info['csrf']
        await self.post('/api/start',{})
        await self.post('/api/message',{'text':'Fresh'})
        self.assertNotIn('contextVariables',self.sent[0])

class NativeBrowserSettingsAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def config(self):
        from test_assistant_settings import SERVICE, AGENT
        return Config(instance_name='unit',voice_service_id=SERVICE,required_agent_id=AGENT,auth_mode='servicenow')
    def request(self,config,**updates):
        query={'instance_name':config.instance_name,'voice_service_id':config.voice_service_id,'auth_token':'private.opaque.jwt'}
        query.update(updates)
        return SimpleNamespace(query=query,headers={'Origin':config.instance_url},remote='127.0.0.1')
    def http(self,data,status=200):
        encoded=json.dumps(data).encode()
        class Content:
            def __init__(self): self.data=encoded
            async def read(self,count):
                value=self.data[:count]; self.data=self.data[count:]; return value
        class Reply:
            headers={}
            def __init__(self): self.status=status; self.content=Content()
            async def __aenter__(self): return self
            async def __aexit__(self,*args): return False
        class Client:
            def __init__(self): self.posts=[]
            def post(self,url,**kwargs): self.posts.append(kwargs); return Reply()
        return Client()
    async def test_native_browser_requests_fresh_bound_projection_with_existing_jwt(self):
        from test_assistant_settings import authorized_settings
        from assistant_settings import CallSettings
        config=self.config(); data=authorized_settings(); http=self.http(data)
        first=await authorize(self.request(config),config,http,with_settings=True)
        self.assertIsInstance(first,CallSettings)
        self.assertEqual(http.posts[0]['json'],{'serviceId':config.voice_service_id,'clientApp':'admin_test','assistantSettingsVersion':1})
        self.assertEqual(http.posts[0]['headers']['Authorization'],'Bearer private.opaque.jwt')
        self.assertEqual(http.posts[0]['headers'].get('Accept-Encoding'),'identity')
        self.assertIs(http.posts[0].get('auto_decompress'),False)
        first.select_language('English please')
        second=await authorize(self.request(config),config,self.http(data),with_settings=True)
        self.assertIsNot(first,second)
        self.assertEqual(second.language,'de-DE')
        self.assertNotIn('private.opaque.jwt',str(first.snapshot()))
    async def test_browser_projection_missing_wrong_service_oversized_and_denied_are_closed(self):
        from test_assistant_settings import authorized_settings
        config=self.config()
        wrong=authorized_settings(); wrong['result']['assistant_settings']['service_id']='f'*32
        oversized=authorized_settings(); oversized['result']['assistant_settings']['prompt']['systemMessage']='x'*40000
        for data,status in [({'result':[config.required_agent_id]},200),(wrong,200),(oversized,200),(authorized_settings(),401)]:
            self.assertFalse(await authorize(self.request(config),config,self.http(data,status),with_settings=True))
        for query in [{'auth_token':'invalid'},{'instance_name':'other'},{'voice_service_id':'f'*32}]:
            http=self.http(authorized_settings())
            self.assertFalse(await authorize(self.request(config,**query),config,http,with_settings=True))
            self.assertEqual(http.posts,[])
        request=self.request(config); request.headers={'Origin':'https://other.service-now.com'}
        http=self.http(authorized_settings())
        self.assertFalse(await authorize(request,config,http,with_settings=True))
        self.assertEqual(http.posts,[])

    async def test_browser_dtmf_choice_is_explicit_unsupported_before_peer_allocation(self):
        from test_assistant_settings import authorized_settings
        from assistant_settings import CallSettings
        from unittest.mock import AsyncMock, patch
        from native_bridge import create_app
        config=self.config(); data=authorized_settings()
        data['result']['assistant_settings']['language_selection']['mode']='dtmf'
        settings=CallSettings.from_authorized_response(data,config.voice_service_id,config.required_agent_id)
        with patch('native_bridge.authorize',new=AsyncMock(return_value=settings)),patch('native_bridge.NativeCall') as allocate:
            client=TestClient(TestServer(create_app(config)))
            await client.start_server()
            try:
                response=await client.get('/webrtc/connect/agent_operator')
                self.assertEqual(response.status,501)
                self.assertIn('unsupported',await response.text())
                allocate.assert_not_called()
            finally: await client.close()

if __name__=='__main__': unittest.main()
