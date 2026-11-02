"""Both admitted transports hand only their original credential to bootstrap."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer
import native_bridge
from native_bridge import Config, create_app
from assistant_settings import CallSettings
from test_assistant_settings import authorized_settings, SERVICE, AGENT
from test_sdk_sessions import FakeCall

INSTANCE='soprasteriaassvsdemo14'
TOKEN='original.voice.credential'


class CallerTransportTests(unittest.IsolatedAsyncioTestCase):
    async def client(self, *, sdk=False, missing_dialog_binder=False):
        self.calls=[];owner=self
        class Call(FakeCall):
            def __init__(self,config,speech,dialog,**kwargs):
                super().__init__();self.config=config;self.dialog=dialog;self.call_id='c'*12;self.close_task=None
                owner.calls.append(self)
            async def close(self):
                if hasattr(self.dialog,'shutdown'):await self.dialog.shutdown()
                await super().close()
        settings=CallSettings.from_authorized_response(authorized_settings(),SERVICE,AGENT)
        context=SimpleNamespace(instance_url='https://'+INSTANCE+'.service-now.com',assistant_id=SERVICE,
            voice_agent_id=AGENT,sdk_agent_id='agent_operator',receive_data=True,call_settings=settings)
        self.enterContext(patch('native_bridge.authorize',AsyncMock(return_value=settings)))
        self.enterContext(patch('native_bridge.require_model_ready',AsyncMock()))
        self.enterContext(patch('native_bridge.require_asr_ready',AsyncMock()))
        self.enterContext(patch('native_bridge.NativeCall',Call))
        self.enterContext(patch('sdk_admission.admit_sdk_session',AsyncMock(return_value=context)))
        config=Config(instance_name=INSTANCE,voice_service_id=SERVICE,required_agent_id=AGENT,
            auth_mode='servicenow',native_sdk_enabled=sdk,sdk_public_origin='https://voice.example.test')
        client=TestClient(TestServer(create_app(config,speech_factory=lambda _:object(),
            dialog_factory=(lambda:object()) if missing_dialog_binder else None)))
        await client.start_server();self.addAsyncCleanup(client.close)
        return client

    async def test_websocket_original_query_bearer_reaches_same_private_dialog(self):
        client=await self.client()
        ws=await client.ws_connect('/webrtc/connect/agent_operator?auth_token='+TOKEN)
        bootstrap=self.calls[0].dialog._caller_bootstrap
        self.assertIsNotNone(bootstrap)
        self.assertEqual(bootstrap.take(),'Bearer '+TOKEN)
        self.assertNotIn(TOKEN,repr(self.calls[0].dialog.__dict__))
        await ws.close()
        await asyncio.wait_for(self.calls[0].close_complete.wait(),1)
        self.assertIsNone(self.calls[0].dialog._caller_bootstrap)

    async def test_http_original_header_bearer_is_retired_when_no_offer_arrives(self):
        client=await self.client(sdk=True)
        response=await client.post('/api/webrtc/sessions?instance_name='+INSTANCE+'&receive_data=true',
            json={'agent_id':'agent_operator'},headers={'Authorization':'Bearer '+TOKEN})
        self.assertEqual(response.status,200,await response.text())
        data=await response.json()
        self.assertNotIn(TOKEN,str(data))
        self.assertIsNotNone(self.calls[0].dialog._caller_bootstrap)
        response=await client.delete('/api/webrtc/sessions/'+data['session_id'],
            headers={'Authorization':'Bearer '+TOKEN})
        self.assertIn(response.status,(200,202,204))
        await asyncio.wait_for(self.calls[0].close_complete.wait(),1)
        self.assertIsNone(self.calls[0].dialog._caller_bootstrap)
        self.assertEqual((await (await client.get('/health')).json())['nativeSessions'],0)

    async def test_missing_real_dialog_binder_refuses_before_websocket_upgrade_and_closes(self):
        client=await self.client(missing_dialog_binder=True)
        response=await client.get('/webrtc/connect/agent_operator?auth_token='+TOKEN)
        self.assertEqual(response.status,503)
        self.assertNotIn(TOKEN,await response.text())
        self.assertTrue(self.calls[0].close_complete.is_set())


if __name__=='__main__':unittest.main()
