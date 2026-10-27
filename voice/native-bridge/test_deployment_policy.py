"""Offline portability/security checks for operator-configured SDK deployments."""
import dataclasses
import importlib
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from native_bridge import Config, create_app
from sdk_admission import AdmissionDenied, VerifiedContext, admit_sdk_session
from sdk_sessions import register_sdk_routes
from test_sdk_admission import FakeHttp, FakeResponse
from test_assistant_settings import authorized_settings

try:
    deployment = importlib.import_module('sdk_deployment')
except ModuleNotFoundError as error:
    if error.name != 'sdk_deployment':
        raise
    deployment = None

FIRST = dict(instance_name='soprasteriaassvsdemo14',
    assistant_id='8aa131d793f787105c8132d47aba1095',
    voice_agent_id='a6337ddf93f787105c8132d47aba1058',
    public_origin='https://strix-alloy.tail7f425a.ts.net')
SECOND = dict(instance_name='community-demo', assistant_id='1'*32,
    voice_agent_id='2'*32, public_origin='https://voice.community.example')
BODY = b'{"agent_id":"agent_operator"}'
HEADERS = [('Authorization', 'Bearer synthetic-first-instance-token'),
           ('Content-Type', 'application/json')]


class FakeCall:
    def __init__(self):
        self.input_ended = asyncio.Event()
        self.turns_settled = asyncio.Event()
        self.close_complete = asyncio.Event()

    async def close(self):
        self.close_complete.set()


class PolicyValidationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(deployment, 'validated deployment policy is missing')

    def test_policy_is_immutable_and_derives_only_the_fixed_platform_auth_path(self):
        policy = deployment.SDKDeploymentPolicy(**SECOND)
        self.assertEqual(policy.instance_url, 'https://community-demo.service-now.com')
        self.assertEqual(policy.authorization_url,
            policy.instance_url+'/api/sn_voice_aia/ai_voice_agent/agents_authorized')
        self.assertEqual(policy.sdk_agent_id, 'agent_operator')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            policy.public_origin = FIRST['public_origin']

    def test_instance_and_allowlist_ids_are_bounded_and_canonical(self):
        for field, values in {
            'instance_name': ['', None, 'Demo', '-demo', 'demo-', 'a'*64,
                'https://evil.example', 'evil.example', 'a/b', 'a@b', 'démo'],
            'assistant_id': ['', None, 'a'*31, 'a'*33, 'A'*32, '*'],
            'voice_agent_id': ['', None, 'a'*31, 'a'*33, 'A'*32, '*'],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    deployment.SDKDeploymentPolicy(**{**SECOND, field:value})

    def test_public_origin_rejects_noncanonical_or_nonpublic_destinations(self):
        values = ['', None, 'http://voice.example.com', 'https://user:secret@voice.example.com',
            'https://voice.example.com/', 'https://voice.example.com/path',
            'https://voice.example.com?token=secret', 'https://voice.example.com#fragment',
            'https://localhost', 'https://127.0.0.1', 'https://[::1]',
            'https://192.168.1.1', 'https://voice.local', 'https://voice.internal',
            'https://127.0.0x1', 'https://0x7f.0x0.0x0.0x1', 'https://192.168.0x1.0x1',
            'https://voice.example.com:0', 'https://voice.example.com:65536',
            'https://voice.example.com:8443', 'https://voice.example.com:443',
            'https://VOICE.example.com', 'https://voice.example.com.',
            'https://voice.example.com\n', 'https://vöice.example.com', 'https://'+'a'*254]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                deployment.SDKDeploymentPolicy(**{**SECOND, 'public_origin':value})

    def test_config_has_no_implicit_demo_policy_and_requires_explicit_opt_in(self):
        config = Config()
        self.assertFalse(config.native_sdk_enabled)
        self.assertIsNone(config.sdk_policy)
        for values in ({'native_sdk_enabled':True},
                {'sdk_public_origin':SECOND['public_origin']},
                {'native_sdk_enabled':True, 'auth_mode':'servicenow',
                 'voice_service_id':SECOND['assistant_id'],
                 'required_agent_id':SECOND['voice_agent_id']},
                {'native_sdk_enabled':True, 'auth_mode':'servicenow',
                 'voice_service_id':SECOND['assistant_id'],
                 'required_agent_id':SECOND['voice_agent_id'],
                 'sdk_public_origin':SECOND['public_origin']}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Config(**values)

    def test_config_rejects_contradictory_auth_and_invalid_duration(self):
        values = dict(instance_name=SECOND['instance_name'],
            voice_service_id=SECOND['assistant_id'], required_agent_id=SECOND['voice_agent_id'],
            sdk_public_origin=SECOND['public_origin'], native_sdk_enabled=True,
            auth_mode='servicenow')
        for changes in ({'auth_mode':'deny'}, {'development_token':'secret'},
                {'max_call_seconds':float('inf')}, {'max_call_seconds':True},
                {'max_call_seconds':10**1000},
                {'max_call_seconds':0}, {'max_call_seconds':3601}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Config(**{**values, **changes})
        config = Config(**values)
        self.assertEqual(config.sdk_policy, deployment.SDKDeploymentPolicy(**SECOND))


class ConfiguredAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(deployment, 'validated deployment policy is missing')
        self.first = deployment.SDKDeploymentPolicy(**FIRST)
        self.second = deployment.SDKDeploymentPolicy(**SECOND)
        self.query = 'instance_name=community-demo&receive_data=true&voice_service_id='+'1'*32

    async def test_missing_policy_denies_before_http(self):
        http = FakeHttp()
        with self.assertRaises(AdmissionDenied) as caught:
            await admit_sdk_session(HEADERS, BODY, query_string=self.query, http_factory=http.factory)
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(http.calls, [])

    async def test_second_instance_requires_its_own_platform_authorization(self):
        http = FakeHttp(FakeResponse(payload={'result':['2'*32]}))
        context = await admit_sdk_session(HEADERS, BODY, query_string=self.query,
            policy=self.second, http_factory=http.factory)
        self.assertEqual(context, VerifiedContext(self.second.instance_url,'1'*32,'2'*32,
                                                'agent_operator',True))
        self.assertEqual(http.calls[0][0], self.second.authorization_url)
        self.assertEqual(http.calls[0][1]['json'], {'serviceId':'1'*32})
        self.assertEqual(http.calls[0][1]['headers']['Authorization'], HEADERS[0][1])
        rejected = FakeHttp(FakeResponse(status=401))
        with self.assertRaises(AdmissionDenied) as caught:
            await admit_sdk_session(HEADERS, BODY, query_string=self.query,
                policy=self.second, http_factory=rejected.factory)
        self.assertEqual(caught.exception.status,401)
        self.assertEqual(rejected.calls[0][0],self.second.authorization_url)

    async def test_first_instance_query_origin_and_voice_agent_fail_for_second(self):
        for query, headers, response in (
            (self.query.replace('community-demo',FIRST['instance_name']), HEADERS, None),
            (self.query, HEADERS+[('Origin',self.first.instance_url)], None),
            (self.query.replace('1'*32,FIRST['assistant_id']), HEADERS, None),
            (self.query, HEADERS, FakeResponse(payload={'result':[FIRST['voice_agent_id']]}))):
            http = FakeHttp(response)
            with self.subTest(query=query,headers=headers), self.assertRaises(AdmissionDenied) as caught:
                await admit_sdk_session(headers,BODY,query_string=query,
                    policy=self.second,http_factory=http.factory)
            self.assertEqual(caught.exception.status,403)
            self.assertEqual(len(http.calls),1 if response else 0)


class ConfiguredSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(deployment, 'validated deployment policy is missing')
        self.policy = deployment.SDKDeploymentPolicy(**SECOND)
        self.config = SimpleNamespace(instance_name=self.policy.instance_name,
            instance_url=self.policy.instance_url, voice_service_id=self.policy.assistant_id,
            required_agent_id=self.policy.voice_agent_id, sdk_policy=self.policy,
            auth_mode='servicenow', development_token='', max_call_seconds=30)
        self.calls, self.active = [], set()
        self.context = VerifiedContext(self.policy.instance_url,self.policy.assistant_id,
            self.policy.voice_agent_id,'agent_operator',True)
        async def admit(*args, **kwargs):
            return self.context
        def make_call():
            call = FakeCall()
            self.calls.append(call)
            return call
        app = web.Application()
        self.manager = register_sdk_routes(app,self.config,self.active,make_call,admit)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def create(self, headers=None):
        return await self.client.post('/api/webrtc/sessions?instance_name=community-demo&receive_data=true',
            json={'agent_id':'agent_operator'},headers=dict(HEADERS if headers is None else headers))

    async def test_second_instance_rejects_first_context_and_origin_before_allocation(self):
        first = deployment.SDKDeploymentPolicy(**FIRST)
        response = await self.create(HEADERS+[('Origin',first.instance_url)])
        self.assertEqual(response.status,403)
        self.context = VerifiedContext(first.instance_url,first.assistant_id,
            first.voice_agent_id,'agent_operator',True)
        self.assertEqual((await self.create()).status,403)
        self.assertEqual(self.calls,[])

    async def test_endpoint_and_session_origin_come_from_startup_policy(self):
        response = await self.create(HEADERS+[('Host','attacker.invalid'),
            ('Forwarded','host=attacker.invalid;proto=http'),('X-Forwarded-Host','attacker.invalid')])
        self.assertEqual(response.status, 200)
        session = await response.json()
        self.assertEqual(session['endpoint_url'],SECOND['public_origin'])
        path = '/api/webrtc/sessions/'+session['session_id']+'/candidates'
        response = await self.client.get(path,headers=dict(HEADERS+[('Origin',
            deployment.SDKDeploymentPolicy(**FIRST).instance_url)]))
        self.assertEqual(response.status,403)
        response = await self.client.get(path,headers=dict(HEADERS+[('Origin',self.policy.instance_url)]))
        self.assertEqual(response.status,409)  # Correctly bound, no offer submitted.

    async def test_replacing_startup_policy_cannot_rebind_existing_manager(self):
        self.config.sdk_policy = deployment.SDKDeploymentPolicy(**FIRST)
        self.assertEqual((await self.create()).status,403)
        self.assertEqual(self.calls,[])


class ConfiguredBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(deployment, 'validated deployment policy is missing')
        self.config = Config(instance_name=SECOND['instance_name'],
            voice_service_id=SECOND['assistant_id'], required_agent_id=SECOND['voice_agent_id'],
            sdk_public_origin=SECOND['public_origin'], native_sdk_enabled=True,auth_mode='servicenow')

    async def test_application_binds_same_policy_to_admission_and_response(self):
        payload = authorized_settings()
        payload['result']['authorized_agents'] = [SECOND['voice_agent_id']]
        payload['result']['assistant_settings']['service_id'] = SECOND['assistant_id']
        http = FakeHttp(FakeResponse(payload=payload))
        async def authorize(headers,body,*,query_string,policy,assistant_settings_version):
            self.assertIs(policy,self.config.sdk_policy)
            self.assertEqual(assistant_settings_version,1)
            return await admit_sdk_session(headers,body,query_string=query_string,
                policy=policy,http_factory=http.factory,
                assistant_settings_version=assistant_settings_version)
        with patch('sdk_admission.admit_sdk_session',side_effect=authorize), \
                patch('native_bridge.NativeCall',return_value=FakeCall()):
            client = TestClient(TestServer(create_app(self.config,dialog_factory=lambda:None)))
            await client.start_server()
            try:
                response = await client.post('/api/webrtc/sessions?instance_name=community-demo&receive_data=true',
                    headers=dict(HEADERS+[('Origin',self.config.instance_url)]),json={'agent_id':'agent_operator'})
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())['endpoint_url'],SECOND['public_origin'])
                self.assertEqual(http.calls[0][0],self.config.sdk_policy.authorization_url)
                self.assertEqual(http.calls[0][1]['json'],
                    {'serviceId':SECOND['assistant_id'],'assistantSettingsVersion':1})
            finally:
                await client.close()

    async def test_sdk_create_requires_settings_projection_before_native_allocation(self):
        http = FakeHttp(FakeResponse(payload={'result':[SECOND['voice_agent_id']]}))
        async def authorize(headers,body,*,query_string,policy,assistant_settings_version):
            return await admit_sdk_session(headers,body,query_string=query_string,
                policy=policy,http_factory=http.factory,
                assistant_settings_version=assistant_settings_version)
        with patch('sdk_admission.admit_sdk_session',side_effect=authorize), \
                patch('native_bridge.NativeCall') as native_call:
            client = TestClient(TestServer(create_app(self.config,dialog_factory=lambda:None)))
            await client.start_server()
            try:
                response = await client.post('/api/webrtc/sessions?instance_name=community-demo&receive_data=true',
                    headers=dict(HEADERS),json={'agent_id':'agent_operator'})
                self.assertEqual(response.status,403)
                self.assertEqual(await response.json(),{'error':'forbidden'})
                self.assertEqual(http.calls[0][1]['json'],
                    {'serviceId':SECOND['assistant_id'],'assistantSettingsVersion':1})
                native_call.assert_not_called()
            finally:
                await client.close()

    async def test_private_probe_can_clone_config_with_immutable_policy(self):
        import demo_audio_smoke as demo
        class Captured(Exception):
            pass
        seen = []
        def capture(config,**kwargs):
            seen.append(config)
            raise Captured()
        with patch.object(demo.production,'NativeCall',FakeCall), \
                patch.object(demo.production,'create_app',side_effect=capture):
            try:
                await demo.single_call(self.config,None,None,None,False)
            except Captured:
                pass
            except TypeError as error:
                self.fail('private probe cannot clone SDK deployment config: '+str(error))
        self.assertEqual(len(seen),1)
        self.assertIsNot(seen[0],self.config)
        self.assertEqual(seen[0].sdk_policy,self.config.sdk_policy)
        self.assertTrue(seen[0].development_token)
        self.assertEqual(self.config.development_token,'')


if __name__ == '__main__':
    unittest.main()
