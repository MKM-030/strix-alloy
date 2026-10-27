"""Host-only TURN configuration contract; no real relay, platform, or speech traffic."""
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from aiortc import RTCPeerConnection
from aiortc.rtcicetransport import connection_kwargs
import native_bridge
from sdk_admission import _VerifiedSettingsContext
from assistant_settings import CallSettings

try:
    host_ice = importlib.import_module('host_ice')
except ModuleNotFoundError:
    host_ice = None

STUN = 'stun:stun.l.google.com:19302'
ENV = {'TEST_RELAY_USER':'fixture-user', 'TEST_RELAY_PASSWORD':'fixture-password'}


def private_payload(url='turn:relay.invalid:3478?transport=udp'):
    return {'turn_servers':[{'url':url, 'username_env':'TEST_RELAY_USER',
                             'credential_env':'TEST_RELAY_PASSWORD'}]}


class _Dialog:
    async def close(self):
        pass


class _Speech:
    async def synthesize(self,text):
        raise AssertionError('Session creation must not synthesize')
        yield b''


def authorized_settings():
    return {'result': {'version':1,'authorized_agents':['a'*32], 'assistant_settings': {
        'version':1,'service_id':'8'*32,'context_profile':'4'*32,'language':'de-DE',
        'language_selection': {'enabled':False,'dtmf_enabled':False,'mode':'voice',
            'languages':[{'code':'de-DE','display_name':'Deutsch','language_selection_prompt':'',
                'dtmf_language_selection_prompt':'','trigger_phrases':[], 'secondary_language_prompt':''}]},
        'tts': {'voice_profile':'test-profile','voices':{'de-DE':{'voice_id':'test-voice','voice_gender':'female'}}},
        'key_terms':{'de-DE':[]},'prompt':{'systemMessage':'Test only.','introduction':'Test.'},
        'vad':{'confidence':0.75,'min_volume':0.03,'start_secs':0.12,'stop_secs':0.8},
        'behavior':{}}}}


class HostIceConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(host_ice, 'Private host ICE configuration is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / 'private-ice.json'
        self.config_path = self.root / 'bridge.json'

    def load(self, payload=None, env=None):
        self.private.write_text(json.dumps(payload if payload is not None else private_payload()),encoding='utf-8')
        with patch.dict(os.environ, ENV if env is None else env, clear=True):
            return host_ice.load_host_ice_file(self.private)

    def test_default_preserves_exact_fixed_stun(self):
        servers = host_ice.HostIceConfiguration().servers()
        self.assertEqual(len(servers),1)
        self.assertEqual(servers[0].urls,[STUN])
        self.assertIsNone(servers[0].username)
        self.assertIsNone(servers[0].credential)
        self.assertEqual(connection_kwargs(servers),{'stun_server':('stun.l.google.com',19302)})

    def test_supported_turn_transports_reach_installed_aiortc(self):
        for url,port,transport,tls in [
            ('turn:relay.invalid',3478,'udp',False),
            ('turn:relay.invalid:443?transport=tcp',443,'tcp',False),
            ('turns:relay.invalid',5349,'tcp',True),
            ('turns:relay.invalid:443?transport=tcp',443,'tcp',True)]:
            with self.subTest(url=url):
                configuration=self.load(private_payload(url))
                result=connection_kwargs(configuration.servers())
                self.assertEqual(result['turn_server'],('relay.invalid',port))
                self.assertEqual(result['turn_transport'],transport)
                self.assertEqual(result['turn_ssl'],tls)
                self.assertEqual(result['turn_username'],ENV['TEST_RELAY_USER'])
                self.assertEqual(result['turn_password'],ENV['TEST_RELAY_PASSWORD'])

    def test_invalid_urls_are_rejected_before_aiortc_can_ignore_them(self):
        for url in ['', 'stun:relay.invalid', 'stuns:relay.invalid',
                    'turns:relay.invalid?transport=udp','turn:relay.invalid?transport=TLS',
                    'turn://relay.invalid','turn:user:secret@relay.invalid',
                    'turn:relay.invalid..','turn:relay.invalid...', 'turn:relay.invalid/path','turn:relay.invalid#fragment',
                    'turn:relay.invalid?transport=udp&transport=tcp',
                    'turn:relay.invalid?other=udp','turn:relay.invalid:0',
                    'turn:relay.invalid:65536','turn:[::1]:3478',
                    'turn:relay.invalid\n','turn:bad host','TURN:relay.invalid']:
            with self.subTest(url=url):
                with self.assertRaises(ValueError) as rejected:
                    self.load(private_payload(url))
                self.assertNotIn('relay.invalid',str(rejected.exception))
                self.assertNotIn('secret',str(rejected.exception))

    def test_multiple_turn_servers_and_unknown_or_inline_keys_fail_closed(self):
        valid=private_payload()
        payloads=[{'turn_servers':[]}, {'turn_servers':valid['turn_servers']*2},
                  {'turn_servers':valid['turn_servers'],'extra':True},
                  {'turn_servers':[{**valid['turn_servers'][0],'credential':'inline-secret'}]},
                  {'turn_servers':[{**valid['turn_servers'][0],'urls':['turn:relay.invalid']}]},
                  {'iceServers':valid['turn_servers']}]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):self.load(payload)
        self.private.write_text('{"turn_servers":[],"turn_servers":[]}',encoding='utf-8')
        with self.assertRaises(ValueError):host_ice.load_host_ice_file(self.private)

    def test_environment_values_are_required_bounded_and_never_echoed(self):
        for env in [{}, {'TEST_RELAY_USER':'x','TEST_RELAY_PASSWORD':''},
                    {'TEST_RELAY_USER':'x','TEST_RELAY_PASSWORD':'secret\nvalue'},
                    {'TEST_RELAY_USER':'x','TEST_RELAY_PASSWORD':'x'*4097}]:
            with self.subTest(keys=sorted(env)):
                with self.assertRaises(ValueError) as rejected:self.load(env=env)
                self.assertNotIn('secret',str(rejected.exception))
        payload=private_payload()
        payload['turn_servers'][0]['credential_env']='INVALID-NAME'
        with self.assertRaises(ValueError):self.load(payload)

    def test_missing_malformed_and_oversized_files_have_sanitized_errors(self):
        for data in [b'{not-json',b' '*16385,b'\xff']:
            self.private.write_bytes(data)
            with self.assertRaises(ValueError) as rejected:host_ice.load_host_ice_file(self.private)
            self.assertNotIn(str(self.private),str(rejected.exception))
        with self.assertRaises(ValueError):host_ice.load_host_ice_file(self.root/'missing.json')

    def test_resolved_secrets_are_not_reprs_and_objects_cannot_mutate_shared_servers(self):
        configuration=self.load()
        config=native_bridge.Config(private_host_ice=configuration)
        self.assertNotIn(ENV['TEST_RELAY_PASSWORD'],repr(config)+repr(configuration))
        self.assertNotIn(ENV['TEST_RELAY_USER'],repr(config)+repr(configuration))
        first=configuration.servers()
        first[1].credential='changed'
        first[0].urls.append('stun:changed.invalid')
        self.assertEqual(configuration.servers()[1].credential,ENV['TEST_RELAY_PASSWORD'])
        self.assertEqual(configuration.servers()[0].urls,[STUN])
        with self.assertRaises((AttributeError,TypeError)):configuration.turn_url='turn:changed.invalid'

    def test_startup_file_is_relative_to_bridge_config_and_snapshot_survives_replace(self):
        self.private.write_text(json.dumps(private_payload()),encoding='utf-8')
        self.config_path.write_text(json.dumps({'host_ice_config_file':self.private.name}),encoding='utf-8')
        loader=getattr(native_bridge,'load_config',None)
        self.assertTrue(callable(loader),'Startup config must support a private host ICE file')
        with patch.dict(os.environ,ENV,clear=True):config=loader(self.config_path)
        self.private.unlink()
        with patch.dict(os.environ,{},clear=True):cloned=replace(config,greeting='changed')
        self.assertIs(cloned.private_host_ice,config.private_host_ice)
        self.assertEqual(cloned.private_host_ice.servers()[1].credential,ENV['TEST_RELAY_PASSWORD'])
        self.config_path.write_text('{"private_host_ice":{}}',encoding='utf-8')
        with self.assertRaises(ValueError):loader(self.config_path)


class HostIceSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_turn_reaches_native_sdk_peer_without_public_dto_or_health_changes(self):
        self.assertIsNotNone(host_ice,'Private host ICE configuration is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            private=Path(directory)/'ice.json'
            private.write_text(json.dumps(private_payload()),encoding='utf-8')
            with patch.dict(os.environ,ENV,clear=True):host=host_ice.load_host_ice_file(private)
        config=native_bridge.Config(instance_name='voice-example',auth_mode='servicenow',
            sdk_public_origin='https://voice.example.invalid',
            voice_service_id='8'*32,
            required_agent_id='a'*32,
            native_sdk_enabled=True,private_host_ice=host)
        payload=authorized_settings()
        payload['result']['authorized_agents']=[config.required_agent_id]
        payload['result']['assistant_settings']['service_id']=config.voice_service_id
        settings=CallSettings.from_authorized_response(payload,config.voice_service_id,config.required_agent_id)
        async def grant(*args,**kwargs):
            return _VerifiedSettingsContext(config.instance_url,config.voice_service_id,
                config.required_agent_id,'agent_operator',True,settings)
        with patch('sdk_admission.admit_sdk_session',side_effect=grant), \
             patch('native_bridge.RTCPeerConnection',wraps=RTCPeerConnection) as peer_factory:
            client=TestClient(TestServer(native_bridge.create_app(config,
                speech_factory=lambda http:_Speech(),dialog_factory=_Dialog)))
            await client.start_server()
            try:
                headers={'Authorization':'Bearer host-relay-offline-fixture'}
                response=await client.post('/api/webrtc/sessions?instance_name='+config.instance_name+
                    '&receive_data=true&voice_service_id='+config.voice_service_id,
                    headers=headers,json={'agent_id':'agent_operator'})
                self.assertEqual(response.status,200)
                body=await response.json()
                self.assertEqual(body['iceServers'],[{'urls':[STUN]}])
                self.assertEqual(set(body),{'session_id','agent_id','created_at','iceServers','endpoint_url'})
                actual=connection_kwargs(peer_factory.call_args.args[0].iceServers)
                self.assertEqual(actual['turn_password'],ENV['TEST_RELAY_PASSWORD'])
                health=await (await client.get('/health')).json()
                text=json.dumps(body)+json.dumps(health)
                for forbidden in ['relay.invalid',ENV['TEST_RELAY_USER'],ENV['TEST_RELAY_PASSWORD'],
                                  'host_ice','relay_ready','relayReady']:
                    self.assertNotIn(forbidden,text)
                response=await client.delete('/api/webrtc/sessions/'+body['session_id'],headers=headers)
                self.assertIn(response.status,(202,204))
            finally:
                await client.close()

if __name__=='__main__':unittest.main()
