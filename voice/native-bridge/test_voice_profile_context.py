"""Trusted native assistant profile binding; local HTTP only, no inference."""
import sys
from pathlib import Path
import unittest
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from assistant_settings import CallSettings
from test_assistant_settings import authorized_settings, SERVICE, AGENT, PROFILE
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings


class VoiceProfileContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent=[]
        async def receive(request):
            self.sent.append(await request.json())
            return web.json_response({'status':'success'})
        app=web.Application(); app.router.add_post('/bot',receive)
        self.bot=TestServer(app); await self.bot.start_server()
        self.bridge=Bridge(Settings(instance_url='https://instance.example.test',user_id='fixture',
            defer_start_until_message=True),'unit-bot','unit-audio','unit-callback')
        self.bridge.bot_url=str(self.bot.make_url('/bot'))
        self.ui=TestClient(TestServer(self.bridge.ui_app()),cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin=str(self.ui.make_url('/')).rstrip('/')
        info=await (await self.ui.get('/api/session')).json()
        self.headers={'Origin':self.bridge.origin,'X-CSRF-Token':info['csrf']}
        self.context=CallSettings.from_authorized_response(authorized_settings(),SERVICE,AGENT).native_context()
    async def asyncTearDown(self):
        await self.ui.close(); await self.bot.close()
    async def post(self,path,value):
        return await self.ui.post(path,json=value,headers=self.headers)
    async def creation_ready(self):
        session=next(iter(self.bridge.sessions.values()))
        self.bridge.consume(session,{'body':[{'uiType':'ActionMsg','actionType':'CreateConversation'}]})
        task=self.bridge.queue_start_created(session,self.sent[0]['requestId'])
        await task
        self.bridge.consume(session,{'body':[{'uiType':'InputText'}]})
    async def test_six_proven_fields_reach_native_creation_and_real_user_turn(self):
        self.bridge.settings.defer_start_until_message=False
        self.assertEqual((await self.post('/api/start',{'voice_context':self.context})).status,202)
        self.assertEqual(self.sent[0]['action'],'CREATE_CONVERSATION')
        self.assertEqual(self.sent[0]['contextVariables']['global_context_profile'],PROFILE)
        self.assertEqual(self.sent[0]['contextVariables'],self.context)
        await self.creation_ready()
        self.assertEqual((await self.post('/api/message',{'text':'Actual user intent','voice_context':self.context})).status,202)
        self.assertEqual(self.sent[2]['contextVariables'],self.context)
        self.assertEqual(self.sent[2]['message']['text'],'Actual user intent')
        self.assertNotIn('global_deployment_id',self.sent[2]['contextVariables'])
    async def test_profile_is_guid_validated_and_arbitrary_route_fields_rejected(self):
        for value in ('wrong','A'*32,'1'*31,True,None):
            with self.subTest(kind=type(value).__name__):
                self.assertEqual((await self.post('/api/start',{'voice_context':dict(self.context,global_context_profile=value)})).status,400)
        self.assertEqual((await self.post('/api/start',{'voice_context':dict(self.context,global_deployment_id='a'*32)})).status,400)
        self.assertFalse(next(iter(self.bridge.sessions.values())).started)
        self.assertEqual(self.sent,[])
    async def test_profile_cannot_change_or_disappear_after_conversation_start(self):
        self.assertEqual((await self.post('/api/start',{'voice_context':self.context})).status,202)
        await self.creation_ready()
        altered=dict(self.context,global_context_profile='f'*32)
        removed={key:value for key,value in self.context.items() if key!='global_context_profile'}
        for candidate in (altered,removed):
            self.assertEqual((await self.post('/api/message',{'text':'Real input','voice_context':candidate})).status,400)
        self.assertEqual(len(self.sent),2)
        self.assertEqual(next(iter(self.bridge.sessions.values())).voice_context,self.context)
        self.assertEqual((await self.post('/api/message',{'text':'Real input'})).status,202)
        self.assertEqual(self.sent[2]['contextVariables'],self.context)
    async def test_language_switch_preserves_the_same_assistant_profile_binding(self):
        self.assertEqual((await self.post('/api/start',{'voice_context':self.context})).status,202)
        await self.creation_ready()
        changed=dict(self.context,interaction_requester_session_language='en-US',interaction_user_language='en-US',requester_session_language='en-US')
        self.assertEqual((await self.post('/api/message',{'text':'English please','voice_context':changed})).status,202)
        self.assertEqual(self.sent[2]['contextVariables']['global_context_profile'],PROFILE)
        self.assertEqual(self.sent[2]['contextVariables']['voice_assistant'],SERVICE)
        self.assertEqual(self.sent[2]['contextVariables']['requester_session_language'],'en-US')
    async def test_legacy_five_field_context_remains_supported_without_midcall_profile_change(self):
        legacy={key:value for key,value in self.context.items() if key!='global_context_profile'}
        self.assertEqual((await self.post('/api/start',{'voice_context':legacy})).status,202)
        self.assertEqual((await self.post('/api/message',{'text':'Legacy input','voice_context':self.context})).status,400)
        self.assertEqual((await self.post('/api/message',{'text':'Legacy input','voice_context':legacy})).status,202)
        self.assertEqual(self.sent[0]['contextVariables'],legacy)


if __name__=='__main__': unittest.main()
