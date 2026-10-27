"""Offline relay ownership, SDK admission and exact peer allowlist regression tests."""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

import mobile_relay as relay
from mobile_relay import MobileRelayConfiguration,MobileRelayRegistry,MobileRelayUnavailable,local_udp_peers
from native_bridge import Config,load_config
from test_sdk_sessions import SDKHTTPTests,FakePeer,BASE,QUERY,TOKEN,SDP


def configuration(directory,**changes):
    values={'url':'turns:relay.example.com:10000?transport=tcp',
        'registry_file':str(Path(directory)/'registry.json'),'relay_address':'192.168.50.2',
        'relay_executable':str(Path(directory)/'relay.exe'),'relay_executable_sha256':'a'*64}
    values.update(changes)
    return MobileRelayConfiguration(**values)


def candidate(ip='192.168.50.2',port=55000,protocol='udp',kind='host',component=1):
    return SimpleNamespace(ip=ip,port=port,protocol=protocol,type=kind,component=component)


def peer_with(candidates,state='completed'):
    gatherer=SimpleNamespace(state=state,getLocalCandidates=lambda:candidates)
    ice=SimpleNamespace(iceGatherer=gatherer)
    dtls=SimpleNamespace(transport=ice)
    endpoint=SimpleNamespace(transport=dtls)
    return SimpleNamespace(getTransceivers=lambda:[SimpleNamespace(sender=endpoint,receiver=endpoint)],
        sctp=SimpleNamespace(transport=dtls))


class ConfigurationTests(unittest.TestCase):
    def test_default_is_disabled_and_private(self):
        self.assertFalse(MobileRelayConfiguration().enabled)
        self.assertEqual(MobileRelayConfiguration().ice_servers(),[])
        self.assertNotIn('relay.example',repr(configuration(tempfile.gettempdir())))

    def test_invalid_private_configuration(self):
        cases=[{'url':'turn:relay.example.com:10000?transport=tcp'},
            {'url':'turns:127.0.0.1:10000?transport=tcp'},
            {'url':'turns:relay.example.com:0?transport=tcp'},
            {'url':'turns:relay.example.com:10000?transport=udp'},
            {'url':'turns:relay.example.com.:10000?transport=tcp'},
            {'registry_file':'relative.json'},{'relay_address':'127.0.0.1'},
            {'relay_address':'::1'},{'relay_address':'0.0.0.0'},{'relay_address':'224.0.0.1'},
            {'relay_executable':'relative.exe'},{'relay_executable_sha256':'invalid'},
            {'listen_address':'0.0.0.0:8872'},{'status_address':'127.0.0.1:8872'},
            {'realm':'invalid realm'}]
        for change in cases:
            with self.subTest(change=change),self.assertRaises(ValueError):configuration(tempfile.gettempdir(),**change)

    def test_enabled_requires_servicenow_native_sdk(self):
        c=configuration(tempfile.gettempdir())
        for args in ({'auth_mode':'deny'}, {'auth_mode':'servicenow','instance_name':'test'},
                     {'auth_mode':'servicenow','instance_name':'test','development_token':'fixture'}):
            with self.assertRaises(ValueError):Config(private_mobile_relay=c,**args)

    def test_inline_configuration_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bridge.json';p.write_text(json.dumps({'private_mobile_relay':{}}))
            with self.assertRaises(ValueError):load_config(p)

    def test_file_requires_exact_keys_and_no_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'relay.json'
            for value in ['{}','[]','{"url":"a","url":"b"}',json.dumps({'token':'secret'})]:
                p.write_text(value)
                with self.assertRaises(ValueError):relay.load_mobile_relay_file(p)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.config=configuration(self.temp.name)
        self.registry=MobileRelayRegistry(self.config)
    def tearDown(self):
        self.registry.close();self.temp.cleanup()
    def read(self):return json.loads(Path(self.config.registry_file).read_text())
    def grant(self,seconds=30):self.registry.register('1'*32,'instance','2'*32,hashlib.sha256(b'opaque-fixture').hexdigest(),seconds)

    def test_exclusive_owner_does_not_clear_live_registry(self):
        self.grant();before=Path(self.config.registry_file).read_bytes()
        with self.assertRaises(MobileRelayUnavailable):MobileRelayRegistry(self.config)
        self.assertEqual(Path(self.config.registry_file).read_bytes(),before)

    def test_cross_process_owner_cannot_clear_live_registry(self):
        self.grant();before=Path(self.config.registry_file).read_bytes()
        code="import sys;sys.path.insert(0,"+repr(str(Path(__file__).parent))+");from mobile_relay import *;c=MobileRelayConfiguration("+repr(self.config.url)+","+repr(self.config.registry_file)+","+repr(self.config.relay_address)+","+repr(self.config.relay_executable)+","+repr(self.config.relay_executable_sha256)+")\ntry:MobileRelayRegistry(c)\nexcept MobileRelayUnavailable:print('LOCKED')\nelse:raise RuntimeError('Second owner accepted')"
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'LOCKED')
        self.assertEqual(Path(self.config.registry_file).read_bytes(),before)

    def test_new_owner_clears_stale_registry_after_close(self):
        self.grant();self.registry.close()
        Path(self.config.registry_file).write_text('{"stale":true}')
        self.registry=MobileRelayRegistry(self.config)
        self.assertEqual(self.read(),{'version':1,'sessions':[]})

    def test_grant_is_hashed_empty_peers_and_bounded(self):
        self.grant();entry=self.read()['sessions'][0]
        self.assertEqual(entry['peers'],[])
        self.assertLessEqual(entry['expires_at'],time.time()+30)
        self.assertEqual(entry['token_sha256'],hashlib.sha256(b'opaque-fixture').hexdigest())
        self.assertNotIn('opaque-fixture',Path(self.config.registry_file).read_text())

    def test_exact_real_host_udp_ipv4_peer_allowlist(self):
        self.grant()
        p=peer_with([candidate(),candidate(),candidate(port=55001),candidate(ip='100.100.10.2'),
            candidate(kind='srflx'),candidate(protocol='tcp'),candidate(ip='::1'),candidate(ip='127.0.0.1'),
            candidate(ip='224.0.0.1'),candidate(port=443),candidate(port=True),candidate(component=2)])
        self.registry.set_peers('1'*32,p)
        self.assertEqual(self.read()['sessions'][0]['peers'],[
            {'ip':'100.100.10.2','port':55000},{'ip':'192.168.50.2','port':55000},{'ip':'192.168.50.2','port':55001}])

    def test_absent_relay_address_and_incomplete_gather_rejected(self):
        self.grant()
        for p in [peer_with([candidate(ip='192.168.50.3')]),peer_with([candidate()],state='gathering')]:
            with self.assertRaises(MobileRelayUnavailable):self.registry.set_peers('1'*32,p)
        self.assertEqual(self.read()['sessions'][0]['peers'],[])

    def test_expiry_and_revoke_remove_records(self):
        self.grant()
        with patch.object(relay.time,'time',return_value=time.time()+31):self.registry.prune()
        self.assertEqual(self.read()['sessions'],[])
        self.grant();self.registry.revoke('1'*32);self.assertEqual(self.read()['sessions'],[])

    def test_atomic_failure_removes_stale_allowlist_and_poison_owner(self):
        self.grant()
        with patch.object(relay.os,'replace',side_effect=OSError('fixture')):
            with self.assertRaises(MobileRelayUnavailable):self.registry.revoke('1'*32)
        self.assertFalse(Path(self.config.registry_file).exists())
        with self.assertRaises(MobileRelayUnavailable):self.grant()
        self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))


class MobileSDKTests(unittest.IsolatedAsyncioTestCase):
    headers=SDKHTTPTests.headers
    create=SDKHTTPTests.create
    session=SDKHTTPTests.session
    offer=SDKHTTPTests.offer
    async def asyncSetUp(self):
        await SDKHTTPTests.asyncSetUp(self)
        self.temp=tempfile.TemporaryDirectory();self.relay_config=configuration(self.temp.name)
        self.manager.relay_registry=MobileRelayRegistry(self.relay_config)
    async def asyncTearDown(self):
        await SDKHTTPTests.asyncTearDown(self)
        self.temp.cleanup()
    def read(self):return json.loads(Path(self.relay_config.registry_file).read_text())
    def bind(self):
        p=peer_with([candidate()]);self.calls[0].peer.getTransceivers=p.getTransceivers
        self.calls[0].peer.sctp=p.sctp
    async def settle(self):
        for _ in range(30):
            if not self.active:return
            await asyncio.sleep(.01)
        self.fail('Call capacity remained reserved after cleanup')

    async def test_denied_and_malformed_auth_never_grant(self):
        self.denied=True
        self.assertEqual((await self.create()).status,403)
        self.denied=False
        response=await self.client.post(BASE+QUERY,json={'agent_id':'agent_operator'},headers={'Authorization':'bad'})
        self.assertEqual(response.status,401)
        self.assertEqual(self.read()['sessions'],[]);self.assertEqual(self.calls,[])

    async def test_capacity_rejection_never_grants(self):
        sentinel=object();self.active.add(sentinel)
        self.assertEqual((await self.create()).status,503)
        self.assertEqual(self.read()['sessions'],[]);self.assertEqual(self.calls,[])
        self.active.remove(sentinel)

    async def test_create_uses_sdk_turn_contract_and_gathered_peers_before_answer(self):
        response=await self.create();self.assertEqual(response.status,200);value=await response.json();sid=value['session_id']
        self.assertEqual(value['iceServers'],[{'urls':['stun:stun.l.google.com:19302']},
            {'urls':['turns:relay.example.com:10000?transport=tcp']}])
        entry=self.read()['sessions'][0];self.assertEqual(entry['id'],sid)
        self.assertEqual(entry['token_sha256'],hashlib.sha256(TOKEN.encode()).hexdigest())
        self.assertEqual(entry['peers'],[]);self.assertNotIn(TOKEN,Path(self.relay_config.registry_file).read_text())
        self.bind();self.assertEqual((await self.offer(sid)).status,200)
        self.assertEqual(self.read()['sessions'][0]['peers'],[{'ip':'192.168.50.2','port':55000}])

    async def test_session_deadline_revokes_registry(self):
        self.config.max_call_seconds=.03
        await self.session()
        await asyncio.sleep(.08)
        self.assertEqual(self.read()['sessions'],[])
        await self.settle()

    async def test_offer_atomic_failure_returns_503_and_revokes(self):
        sid=await self.session();self.bind()
        with patch.object(relay.os,'replace',side_effect=OSError('fixture')):
            self.assertEqual((await self.offer(sid)).status,503)
        await self.settle();self.assertFalse(Path(self.relay_config.registry_file).exists())

    async def test_delete_revokes_before_slow_call_cleanup(self):
        sid=await self.session();self.calls[0].close_release.clear()
        response=await self.client.delete(BASE+'/'+sid,headers=self.headers())
        self.assertEqual(response.status,202);self.assertEqual(self.read()['sessions'],[])
        self.assertFalse(self.calls[0].close_complete.is_set());self.calls[0].close_release.set();await self.settle()

    async def test_create_atomic_failure_returns_503_without_leaked_capacity(self):
        with patch.object(relay.os,'replace',side_effect=OSError('fixture')):
            self.assertEqual((await self.create()).status,503)
        await self.settle();self.assertFalse(Path(self.relay_config.registry_file).exists())

    async def test_offer_missing_bound_address_is_503_and_revokes(self):
        sid=await self.session();self.bind();self.manager.relay_registry.config=configuration(self.temp.name,relay_address='192.168.50.3')
        self.assertEqual((await self.offer(sid)).status,503)
        await self.settle();self.assertEqual(self.read()['sessions'],[])

    async def test_double_io_revocation_failure_synchronously_aborts_owned_relay(self):
        sid=await self.session();self.bind();self.assertEqual((await self.offer(sid)).status,200)
        runtime=Mock();self.manager.relay_runtime=runtime
        with patch.object(relay.os,'replace',side_effect=OSError('fixture')),patch.object(Path,'unlink',side_effect=OSError('fixture')):
            self.manager._begin_close(self.manager.sessions[sid])
            runtime.abort.assert_called_once()
            self.assertTrue(self.manager.stopping)
        self.manager.relay_runtime=None
        await self.settle()


if __name__=='__main__':unittest.main()
