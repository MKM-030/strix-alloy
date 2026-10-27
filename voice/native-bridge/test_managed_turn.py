"""Offline managed TURN security, HTTP and local session lifecycle contracts."""
import asyncio
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import aiohttp
import managed_turn as mt
from managed_turn import ManagedTurnConfiguration,ManagedTurnBootstrap,ManagedTurnUnavailable
from native_bridge import Config,load_config
from mobile_relay import MobileRelayConfiguration
import test_sdk_sessions as sdk_test
from test_sdk_sessions import INSTANCE,ASSISTANT,AGENT,TOKEN,BASE,QUERY

MAIN='aivoiceservice-prod-main-amer.sncapps.service-now.com'
REGION='aivoiceservice-prod-main-ycg.sncapps.service-now.com'
TURN='aivoiceservice-prod-turn-ycg.sncapps.service-now.com'
URL='turns:'+TURN+':443?transport=tcp'


def config():
    return ManagedTurnConfiguration('https://'+MAIN,(MAIN,REGION),(TURN,))


def payload(**changes):
    result={'session_id':'fixture_metadata_123','endpoint_url':REGION,
            'iceServers':[{'urls':[URL],'username':'remote-private-username','credential':'remote-private-credential'}]}
    result.update(changes)
    return result


class Response:
    def __init__(self,data=None,*,status=200,content_type='application/json',raw=None,block=None):
        self.status=status
        self.headers={'Content-Type':content_type}
        self.raw=raw if raw is not None else json.dumps(data or {}).encode()
        self.offset=0
        self.content=self
        self.block=block
        self.entered=asyncio.Event()
        self.exited=False
    async def __aenter__(self):
        self.entered.set()
        if self.block is not None:await self.block.wait()
        return self
    async def __aexit__(self,*args):self.exited=True
    async def read(self,n):
        chunk=self.raw[self.offset:self.offset+n]
        self.offset+=len(chunk)
        return chunk


class HTTP:
    def __init__(self,post=None,delete=None):
        self.post_response=post or Response(payload())
        self.delete_response=delete or Response()
        self.calls=[]
        self.factory_args=None
        self.closed=False
    def factory(self,**kwargs):self.factory_args=kwargs;return self
    async def __aenter__(self):return self
    async def __aexit__(self,*args):self.closed=True
    def post(self,url,**kwargs):self.calls.append(('POST',url,kwargs));return self.post_response
    def delete(self,url,**kwargs):self.calls.append(('DELETE',url,kwargs));return self.delete_response
    def bootstrap(self):return ManagedTurnBootstrap(config(),session_factory=self.factory)


class ConfigurationTests(unittest.TestCase):
    def test_default_disabled_private_and_invalid_destinations(self):
        self.assertFalse(ManagedTurnConfiguration().enabled)
        self.assertNotIn(MAIN,repr(config()))
        for origin,hosts in [
            ('http://'+MAIN,(MAIN,)),('https://'+MAIN+':444',(MAIN,)),
            ('https://'+MAIN+'/',(MAIN,)),('https://'+MAIN+'/api',(MAIN,)),
            ('https://'+MAIN+'?token=bad',(MAIN,)),('https://user@'+MAIN,(MAIN,)),
            ('https://'+MAIN+'.evil.example',(MAIN+'.evil.example',)),
            ('https://127.0.0.1',('127.0.0.1',)),('https://'+MAIN,(REGION,)),
            ('https://'+MAIN,(MAIN,MAIN)),('https://'+MAIN,([MAIN],))]:
            with self.subTest(origin=origin,hosts=hosts),self.assertRaises(ValueError):
                ManagedTurnConfiguration(origin,hosts,(TURN,))
        with self.assertRaises(ValueError):ManagedTurnConfiguration(None,(MAIN,),())

    def test_private_file_schema_and_no_inline_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'managed.json'
            invalid=['{}','[]','{"base_origin":"a","base_origin":"b"}',
                     json.dumps({'token':'must-not-be-supported'}),'x'*17000]
            for raw in invalid:
                file.write_text(raw)
                with self.assertRaises(ValueError):mt.load_managed_turn_file(file)
            raw={'base_origin':'https://'+MAIN,'signaling_hosts':[MAIN,REGION],'turn_hosts':[TURN]}
            file.write_text(json.dumps(raw))
            self.assertEqual(mt.load_managed_turn_file(file),config())
            bridge=Path(d)/'bridge.json'
            bridge.write_text(json.dumps({'private_managed_turn':raw}))
            with self.assertRaises(ValueError):load_config(bridge)
            bridge.write_text(json.dumps({'instance_name':INSTANCE,'voice_service_id':ASSISTANT,
                'required_agent_id':AGENT,'auth_mode':'servicenow','native_sdk_enabled':True,
                'sdk_public_origin':'https://relay.example.com','managed_turn_config_file':'managed.json'}))
            loaded=load_config(bridge)
            self.assertEqual(loaded.private_managed_turn,config())
            self.assertNotIn(MAIN,repr(loaded))

    def test_enabled_requires_native_oauth_and_excludes_private_relay(self):
        for args in ({},{'auth_mode':'servicenow','instance_name':'test'},
                     {'native_sdk_enabled':True,'auth_mode':'servicenow','development_token':'fixture'}):
            with self.assertRaises(ValueError):Config(private_managed_turn=config(),**args)
        with tempfile.TemporaryDirectory() as d:
            local=MobileRelayConfiguration(url='turns:relay.example.com:10000?transport=tcp',
                registry_file=str(Path(d)/'registry.json'),relay_address='192.168.50.2',
                relay_executable=str(Path(d)/'relay.exe'),relay_executable_sha256='a'*64)
            with self.assertRaises(ValueError):
                Config(private_managed_turn=config(),private_mobile_relay=local,
                    auth_mode='servicenow',native_sdk_enabled=True,instance_name=INSTANCE,
                    voice_service_id=ASSISTANT,required_agent_id=AGENT,sdk_public_origin='https://relay.example.com')


class BootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_only_create_exact_regional_delete_and_private_credentials(self):
        http=HTTP();bootstrap=http.bootstrap()
        result=await bootstrap.ice_servers(TOKEN,INSTANCE,ASSISTANT)
        self.assertEqual(result,[{'urls':[URL]}])
        self.assertEqual([c[:2] for c in http.calls],[('POST','https://'+MAIN+BASE),
            ('DELETE','https://'+REGION+BASE+'/fixture_metadata_123')])
        create=http.calls[0][2]
        self.assertEqual(create['params'],{'instance_name':INSTANCE,'voice_service_id':ASSISTANT,'receive_data':'true'})
        self.assertEqual(create['json'],{'agent_id':'agent_operator'})
        self.assertEqual(create['headers']['Authorization'],'Bearer '+TOKEN)
        for call in http.calls:self.assertFalse(call[2]['allow_redirects'])
        self.assertFalse(http.factory_args['trust_env'])
        self.assertFalse(http.factory_args['auto_decompress'])
        self.assertIsInstance(http.factory_args['cookie_jar'],aiohttp.DummyCookieJar)
        self.assertTrue(http.closed)
        self.assertEqual(set(vars(bootstrap)),{'config','_session_factory'})
        self.assertNotIn(TOKEN,json.dumps(result)+repr(bootstrap)+repr(bootstrap.config))
        self.assertNotIn('remote-private',json.dumps(result))

    async def test_delete_404_is_terminal_but_failure_rejects_bootstrap(self):
        for status in (200,204,404):
            http=HTTP(delete=Response(status=status))
            self.assertEqual(await http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT),[{'urls':[URL]}])
        for status in (301,401,500):
            http=HTTP(delete=Response(status=status))
            with self.assertRaises(ManagedTurnUnavailable):await http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT)
            self.assertTrue(http.closed)

    async def test_redirect_auth_and_invalid_response_rejected_without_guessed_delete(self):
        cases=[Response(status=301),Response(status=401),Response(content_type='text/html'),
            Response(raw=b'{' ),Response(raw=b'{"session_id":"a","session_id":"b"}'),
            Response(raw=b'x'*65537),Response(payload(session_id='../secret'))]
        for response in cases:
            with self.subTest(status=response.status,bytes=len(response.raw)):
                http=HTTP(post=response)
                with self.assertRaises(ManagedTurnUnavailable) as caught:
                    await http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT)
                self.assertEqual([x[0] for x in http.calls],['POST'])
                self.assertNotIn(TOKEN,str(caught.exception))
                self.assertTrue(http.closed)

    async def test_invalid_endpoint_cleanup_stays_on_approved_base(self):
        for endpoint in ['https://evil.example','https://'+REGION+':444',
                         'https://'+REGION+'/api','http://'+REGION,'https://user@'+REGION,None]:
            with self.subTest(endpoint=endpoint):
                http=HTTP(post=Response(payload(endpoint_url=endpoint)))
                with self.assertRaises(ManagedTurnUnavailable):await http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT)
                self.assertEqual(http.calls[1][1],'https://'+MAIN+BASE+'/fixture_metadata_123')

    async def test_invalid_ice_destinations_fail_after_regional_cleanup(self):
        for url in ['turns:evil.example:443?transport=tcp','turn:'+TURN+':443?transport=tcp',
                    'turns:'+TURN+':10000?transport=tcp','turns:'+TURN+':443?transport=udp',
                    URL+'&token=private']:
            http=HTTP(post=Response(payload(iceServers=[{'urls':[url]}])))
            with self.assertRaises(ManagedTurnUnavailable):await http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT)
            self.assertEqual(http.calls[1][1],'https://'+REGION+BASE+'/fixture_metadata_123')

    async def test_create_timeout_closes_client_and_does_not_retry(self):
        response=Response(payload(),block=asyncio.Event());http=HTTP(post=response)
        with patch.object(mt,'CREATE_SECONDS',.02),self.assertRaises(ManagedTurnUnavailable):
            await http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT)
        self.assertEqual(len(http.calls),1)
        self.assertTrue(http.closed)

    async def test_known_id_cleanup_finishes_before_cancellation_propagates(self):
        release=asyncio.Event();delete=Response(block=release);http=HTTP(delete=delete)
        task=asyncio.create_task(http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT))
        await asyncio.wait_for(delete.entered.wait(),1)
        task.cancel();await asyncio.sleep(0)
        self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):await asyncio.wait_for(task,1)
        self.assertTrue(delete.exited)
        self.assertTrue(http.closed)
        self.assertEqual(len(http.calls),2)

    async def test_cleanup_timeout_is_bounded_and_fails_closed(self):
        http=HTTP(delete=Response(block=asyncio.Event()))
        with patch.object(mt,'DELETE_SECONDS',.02),self.assertRaises(ManagedTurnUnavailable):
            await asyncio.wait_for(http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT),1)
        self.assertTrue(http.closed)

    async def test_invalid_inputs_do_not_open_client(self):
        for token,instance,service in [('bad\nheader',INSTANCE,ASSISTANT),(TOKEN,'other.example',ASSISTANT),
                                      (TOKEN,INSTANCE,'../bad')]:
            http=HTTP()
            with self.assertRaises(ManagedTurnUnavailable):await http.bootstrap().ice_servers(token,instance,service)
            self.assertIsNone(http.factory_args)


class EndpointDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    """Catch missing, misleading, or secret-bearing endpoint rejection logs."""
    async def rejected_flags(self,endpoint):
        http=HTTP(post=Response(payload(endpoint_url=endpoint)))
        with self.assertLogs('managed_turn',level='WARNING') as logged:
            with self.assertRaises(ManagedTurnUnavailable):
                await http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT)
        events=[record for record in logged.records
                if record.msg.startswith('Managed TURN stage=endpoint_rejected ')]
        self.assertEqual(len(events),1,'Expected exactly one bounded endpoint rejection event')
        flags=ast.literal_eval(events[0].getMessage().split('endpoint_rejected ',1)[1])
        self.assertIs(type(flags),dict)
        self.assertTrue(all(type(value) is bool for value in flags.values()))
        self.assertEqual(http.calls[1][1],'https://'+MAIN+BASE+'/fixture_metadata_123')
        output='\n'.join(logged.output)
        for secret in (TOKEN,'diagnostic-private-value',REGION,MAIN,'not-approved.invalid'):
            self.assertNotIn(secret,output)
        return flags

    async def test_unapproved_bare_hostname_is_identified_without_host_disclosure(self):
        # Omitting the endpoint event, or confusing a new host with a malformed URL, fails.
        self.assertEqual(await self.rejected_flags('aivoiceservice-unapproved.sncapps.service-now.com'),{
            'type_valid':True,'length_ok':True,'parsed_ok':True,
            'canonical_origin':False,'bare_host':True,'scheme_ok':True,
            'supported_hostname':True,'allowlisted':False,'netloc_safe':True,
            'path_empty_or_root':True,'has_query':False,'has_fragment':False})

    async def test_rejected_url_flags_distinguish_allowlist_scheme_and_structure(self):
        # Wrong field mapping would misdiagnose a parser issue as configuration drift.
        cases=[
            ('https://'+REGION+'/?diagnostic-private-value',
             {'canonical_origin':False,'scheme_ok':True,'supported_hostname':True,
              'allowlisted':True,'netloc_safe':True,'path_empty_or_root':True,
              'has_query':True,'has_fragment':False}),
            ('http://'+REGION,
             {'canonical_origin':False,'scheme_ok':False,'supported_hostname':True,
              'allowlisted':True,'netloc_safe':True,'path_empty_or_root':True,
              'has_query':False,'has_fragment':False}),
            ('https://diagnostic-private-value@'+REGION+':444/private?diagnostic-private-value#diagnostic-private-value',
             {'canonical_origin':False,'scheme_ok':True,'supported_hostname':True,
              'allowlisted':True,'netloc_safe':False,'path_empty_or_root':False,
              'has_query':True,'has_fragment':True}),
            ('https://not-approved.invalid',
             {'canonical_origin':True,'scheme_ok':True,'supported_hostname':False,
              'allowlisted':False,'netloc_safe':True,'path_empty_or_root':True,
              'has_query':False,'has_fragment':False})]
        for endpoint,expected in cases:
            with self.subTest(kind=expected):
                self.assertEqual(await self.rejected_flags(endpoint),{
                    'type_valid':True,'length_ok':True,'parsed_ok':True,'bare_host':False,
                    **expected})

    async def test_malformed_nonstring_and_oversized_inputs_keep_diagnostic_bounded(self):
        # Diagnostics must not raise a second parse error or serialize the rejected input.
        for endpoint,type_valid,length_ok in [
            ('https://[diagnostic-private-value',True,True),
            (None,False,False),({'diagnostic-private-value':TOKEN},False,False),
            ('https://'+REGION+'/?'+('diagnostic-private-value'*30),True,False)]:
            with self.subTest(type_valid=type_valid,length_ok=length_ok):
                self.assertEqual(await self.rejected_flags(endpoint),{
                    'type_valid':type_valid,'length_ok':length_ok,'parsed_ok':False,
                    'canonical_origin':False,'bare_host':False,'scheme_ok':False,
                    'supported_hostname':False,'allowlisted':False,'netloc_safe':False,
                    'path_empty_or_root':False,'has_query':False,'has_fragment':False})

    async def test_accepted_endpoint_forms_still_succeed_without_rejection_event(self):
        # A diagnostic side effect must not reject or warn on an accepted endpoint form.
        for endpoint in (REGION,'https://'+REGION,'https://'+REGION+'/',
                         'https://'+REGION+':443','https://'+REGION+':443/'):
            with self.subTest(endpoint=endpoint):
                http=HTTP(post=Response(payload(endpoint_url=endpoint)))
                with self.assertNoLogs('managed_turn',level='WARNING'):
                    self.assertEqual(await http.bootstrap().ice_servers(TOKEN,INSTANCE,ASSISTANT),
                                     [{'urls':[URL]}])


class ManagedHostGatheringTests(unittest.IsolatedAsyncioTestCase):
    async def test_managed_host_peer_has_no_redundant_public_stun_gather_branch(self):
        # A public STUN entry makes installed aioice wait for every IPv4 NIC,
        # even after managed TURN is ready. Inspect the actual peer before any I/O.
        from aiortc import RTCConfiguration,RTCPeerConnection
        from aioice.ice import TransportPolicy
        servers=mt.session_host_ice([{'urls':[URL]}],TOKEN,INSTANCE,ASSISTANT)
        peer=RTCPeerConnection(RTCConfiguration(iceServers=servers))
        peer.addTransceiver('audio')
        try:
            connection=peer.getTransceivers()[0].sender.transport.transport.iceGatherer._connection
            self.assertIsNone(connection.stun_server)
            self.assertEqual(connection.turn_server,(TURN,443))
            self.assertEqual(connection.turn_transport,'tcp')
            self.assertTrue(connection.turn_ssl)
            self.assertEqual(connection.turn_username,INSTANCE+':'+ASSISTANT+':'+TOKEN)
            self.assertEqual(connection.turn_password,'oauth')
            self.assertIs(connection._transport_policy,TransportPolicy.ALL)
            self.assertNotIn(TOKEN,repr(servers))
        finally:
            await peer.close()
            mt.clear_session_ice(servers,peer)

    async def test_empty_managed_server_list_retains_existing_stun_fallback(self):
        # An empty optional list must not silently remove the old connectivity path.
        from aiortc import RTCConfiguration,RTCPeerConnection
        servers=mt.session_host_ice([],TOKEN,INSTANCE,ASSISTANT)
        peer=RTCPeerConnection(RTCConfiguration(iceServers=servers))
        peer.addTransceiver('audio')
        try:
            connection=peer.getTransceivers()[0].sender.transport.transport.iceGatherer._connection
            self.assertEqual(connection.stun_server,('stun.l.google.com',19302))
            self.assertIsNone(connection.turn_server)
        finally:
            await peer.close()
            mt.clear_session_ice(servers,peer)


class ManagedSDKTests(unittest.IsolatedAsyncioTestCase):
    headers=sdk_test.SDKHTTPTests.headers
    create=sdk_test.SDKHTTPTests.create
    async def asyncSetUp(self):
        await sdk_test.SDKHTTPTests.asyncSetUp(self)
        self.http=HTTP()
        self.manager.managed_turn=self.http.bootstrap()
        self.host_servers=[]
        def factory(context, *, ice_servers):
            self.host_servers.append(ice_servers)
            return self.manager.make_call()
        self.manager.context_call_factory=factory
    async def asyncTearDown(self):await sdk_test.SDKHTTPTests.asyncTearDown(self)
    async def settle(self):
        for _ in range(50):
            if not self.active:return
            await asyncio.sleep(.01)
        self.fail('Local capacity leaked after failed managed bootstrap')

    async def test_rejected_auth_admission_context_and_capacity_never_reach_cloud(self):
        response=await self.client.post(BASE+QUERY,json={'agent_id':'agent_operator'})
        self.assertEqual(response.status,401)
        self.denied=True;self.assertEqual((await self.create()).status,403);self.denied=False
        original=self.context.assistant_id;self.context.assistant_id='0'*32
        self.assertEqual((await self.create()).status,403);self.context.assistant_id=original
        browser=object();self.active.add(browser)
        self.assertEqual((await self.create()).status,503);self.active.remove(browser)
        self.assertEqual(self.http.calls,[])
        self.assertEqual(self.calls,[])

    async def test_sdk_response_retains_local_signaling_stun_and_no_credentials(self):
        response=await self.create();self.assertEqual(response.status,200,await response.text())
        data=await response.json()
        self.assertEqual(data['endpoint_url'],'https://strix-alloy.tail7f425a.ts.net')
        self.assertEqual(data['iceServers'],[{'urls':['stun:stun.l.google.com:19302']},{'urls':[URL]}])
        self.assertNotEqual(data['session_id'],'fixture_metadata_123')
        self.assertNotIn(TOKEN,json.dumps(data)+repr(self.manager.sessions))
        self.assertEqual(self.calls[0].process_count,0)
        self.assertEqual([x[0] for x in self.http.calls],['POST','DELETE'])
        servers=self.host_servers[0]
        self.assertEqual(servers[0].username,INSTANCE+':'+ASSISTANT+':'+TOKEN)
        self.assertEqual(servers[0].credential,'oauth')
        self.assertNotIn(TOKEN,repr(servers))

    async def test_capacity_reserved_during_bootstrap_and_delete(self):
        release=asyncio.Event();self.http.delete_response=Response(block=release)
        task=asyncio.create_task(self.create())
        await asyncio.wait_for(self.http.delete_response.entered.wait(),1)
        self.assertEqual(len(self.active),1)
        second=await self.create();self.assertEqual(second.status,503)
        self.assertEqual(len(self.calls),0)
        self.assertEqual(len(self.http.calls),2)
        release.set();first=await asyncio.wait_for(task,1);self.assertEqual(first.status,200)

    async def test_failed_delete_returns_503_and_releases_local_capacity(self):
        self.http.delete_response=Response(status=500)
        response=await self.create();self.assertEqual(response.status,503)
        self.assertNotIn(TOKEN,await response.text())
        await self.settle()
        self.assertEqual(self.calls,[])
        self.assertFalse(self.manager.creating)

    async def test_timeout_releases_local_capacity(self):
        self.http.post_response=Response(block=asyncio.Event())
        with patch.object(mt,'CREATE_SECONDS',.02):
            self.assertEqual((await self.create()).status,503)
        await self.settle()
        self.assertTrue(self.http.closed)

    async def test_shutdown_cancels_bootstrap_but_waits_for_known_metadata_cleanup(self):
        release=asyncio.Event();self.http.delete_response=Response(block=release)
        request=asyncio.create_task(self.create())
        await asyncio.wait_for(self.http.delete_response.entered.wait(),1)
        shutdown=asyncio.create_task(self.manager.shutdown())
        await asyncio.sleep(.02)
        self.assertTrue(self.active)
        self.assertFalse(self.http.closed)
        release.set()
        await asyncio.wait_for(shutdown,1)
        await asyncio.gather(request,return_exceptions=True)
        self.assertFalse(self.active)
        self.assertTrue(self.http.closed)
        self.assertEqual(self.calls,[])
        self.assertFalse(self.manager.creating)


    async def test_pending_owner_supports_shared_close_after_shutdown_budget(self):
        import sdk_sessions
        release=asyncio.Event();self.http.delete_response=Response(block=release)
        request=asyncio.create_task(self.create())
        await asyncio.wait_for(self.http.delete_response.entered.wait(),1)
        owner=next(iter(self.active))
        self.assertTrue(callable(owner.close))
        with patch.object(sdk_sessions,'SHUTDOWN_CLEANUP_SECONDS',.01):
            await self.manager.shutdown()
        self.assertIn(owner,self.active)
        close=asyncio.create_task(owner.close())
        await asyncio.sleep(0)
        self.assertFalse(self.http.closed)
        release.set()
        await asyncio.wait_for(close,1)
        await asyncio.gather(request,return_exceptions=True)
        self.assertTrue(self.http.delete_response.exited)
        self.assertFalse(self.active)
        self.assertFalse(self.manager.creating)

    async def test_shutdown_does_not_cancel_known_cleanup_twice(self):
        release=asyncio.Event();self.http.delete_response=Response(block=release)
        request=asyncio.create_task(self.create())
        await asyncio.wait_for(self.http.delete_response.entered.wait(),1)
        operation=next(iter(self.manager.creating))
        operation.cancel()
        await asyncio.sleep(0)
        shutdown=asyncio.create_task(self.manager.shutdown())
        await asyncio.sleep(.01)
        self.assertFalse(self.http.closed)
        self.assertFalse(self.http.delete_response.exited)
        release.set()
        await asyncio.wait_for(shutdown,1)
        await asyncio.gather(request,return_exceptions=True)
        self.assertTrue(self.http.delete_response.exited)
        self.assertFalse(self.active)

    async def test_failed_factory_clears_untransferred_credentials_and_capacity(self):
        captured=[]
        def fail(context, *, ice_servers):
            captured.extend(ice_servers)
            raise ValueError('fixture construction failure')
        self.manager.context_call_factory=fail
        response=await self.create()
        self.assertEqual(response.status,503)
        self.assertFalse(self.active)
        self.assertFalse(self.manager.creating)
        self.assertTrue(all(server.username is None and server.credential is None for server in captured))


class NativeIceTests(unittest.IsolatedAsyncioTestCase):
    async def test_managed_ice_precedes_peer_construction_preserves_settings_and_browser_config(self):
        import native_bridge
        from host_ice import HostIceConfiguration
        from aiortc import RTCPeerConnection
        from aiortc.rtcicetransport import connection_kwargs
        from aiohttp.test_utils import TestClient,TestServer
        from assistant_settings import CallSettings
        from sdk_admission import _VerifiedSettingsContext
        from test_host_ice import authorized_settings,_Speech,_Dialog
        baseline=HostIceConfiguration('turn:host-relay.invalid:3478?transport=udp','old-user','old-password')
        deployment=Config(instance_name=INSTANCE,voice_service_id=ASSISTANT,required_agent_id=AGENT,
            auth_mode='servicenow',native_sdk_enabled=True,sdk_public_origin='https://voice.example.com',
            private_managed_turn=config(),private_host_ice=baseline,greeting='startup greeting')
        projection=authorized_settings()
        projection['result']['authorized_agents']=[AGENT]
        projection['result']['assistant_settings']['service_id']=ASSISTANT
        projection['result']['assistant_settings']['prompt']['introduction']='Hallo aus dem Assistant'
        settings=CallSettings.from_authorized_response(projection,ASSISTANT,AGENT)
        async def admit(*args,**kwargs):
            return _VerifiedSettingsContext(deployment.instance_url,ASSISTANT,AGENT,'agent_operator',True,settings)
        peers=[];ice_configurations=[];calls=[]
        real_native=native_bridge.NativeCall
        def peer_factory(configuration):
            peer=RTCPeerConnection(configuration)
            peers.append(peer);ice_configurations.append(configuration)
            return peer
        def call_factory(*args,**kwargs):
            call=real_native(*args,**kwargs);calls.append(call);return call
        http=HTTP()
        with patch('sdk_admission.admit_sdk_session',side_effect=admit), \
             patch('sdk_sessions.ManagedTurnBootstrap',return_value=http.bootstrap()), \
             patch('native_bridge.RTCPeerConnection',side_effect=peer_factory), \
             patch('native_bridge.NativeCall',side_effect=call_factory):
            client=TestClient(TestServer(native_bridge.create_app(deployment,
                speech_factory=lambda http:_Speech(),dialog_factory=_Dialog)))
            await client.start_server()
            try:
                response=await client.post(BASE+QUERY,headers={'Authorization':'Bearer '+TOKEN},
                                           json={'agent_id':'agent_operator'})
                self.assertEqual(response.status,200,await response.text())
                data=await response.json()
                servers=ice_configurations[0].iceServers
                actual=connection_kwargs(servers)
                self.assertNotIn('stun_server',actual)
                self.assertEqual(actual['turn_username'],INSTANCE+':'+ASSISTANT+':'+TOKEN)
                self.assertEqual(actual['turn_password'],'oauth')
                self.assertEqual(actual['turn_server'],(TURN,443))
                self.assertEqual(actual['turn_transport'],'tcp')
                self.assertTrue(actual['turn_ssl'])
                self.assertIs(calls[0].call_settings,settings)
                self.assertEqual(calls[0].config.greeting,'Hallo aus dem Assistant')
                self.assertEqual(deployment.greeting,'startup greeting')
                self.assertIs(deployment.private_host_ice,baseline)
                self.assertNotIn(TOKEN,json.dumps(data)+repr(deployment)+repr(servers))
                connection=peers[0].getTransceivers()[0].sender.transport.transport.iceGatherer._connection
                # Installed aioice.close() leaves CandidatePair protocol refs behind.
                # A closed call must also discard that stale credential owner.
                connection._check_list.append(object())
                connection._early_checks.append(object())
                await client.delete(BASE+'/'+data['session_id'],headers={'Authorization':'Bearer '+TOKEN})
                await asyncio.wait_for(calls[0].close_complete.wait(),1)
                self.assertIsNone(connection.turn_username)
                self.assertIsNone(connection.turn_password)
                self.assertEqual(connection._check_list,[])
                self.assertEqual(connection._early_checks,[])
                self.assertEqual(calls[0]._session_ice_servers,[])
                # Browser/default calls still resolve their original host-only ICE.
                browser=real_native(deployment,_Speech(),_Dialog(),settings)
                try:
                    self.assertEqual(connection_kwargs(ice_configurations[1].iceServers)['turn_username'],'old-user')
                    self.assertEqual(baseline.servers()[1].credential,'old-password')
                finally:await browser.close()
            finally:await client.close()


if __name__=='__main__':unittest.main()
