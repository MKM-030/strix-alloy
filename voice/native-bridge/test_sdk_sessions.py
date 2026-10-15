"""Offline HTTP wire/lifecycle contract tests. No platform or speech traffic."""
import asyncio
from contextlib import suppress
from dataclasses import dataclass
import importlib.util
import json
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

try:
    import sdk_sessions as adapter
except ModuleNotFoundError:
    adapter = None

INSTANCE = 'soprasteriaassvsdemo14'
ASSISTANT = '8aa131d793f787105c8132d47aba1095'
AGENT = 'a6337ddf93f787105c8132d47aba1058'
ORIGIN = 'https://' + INSTANCE + '.service-now.com'
QUERY = '?instance_name=' + INSTANCE + '&receive_data=true'
TOKEN = 'original.opaque.token'
BASE = '/api/webrtc/sessions'
SDP = ('v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n'
       'a=group:BUNDLE 0 1\r\na=msid-semantic:WMS *\r\n'
       'm=audio 5000 UDP/TLS/RTP/SAVPF 111\r\nc=IN IP4 192.0.2.1\r\n'
       'a=mid:0\r\na=sendrecv\r\na=rtcp-mux\r\na=rtpmap:111 opus/48000/2\r\n'
       'a=ice-ufrag:abcd\r\na=ice-pwd:abcdefghijklmnopqrstuvwxyz\r\n'
       'a=candidate:1 1 udp 2122260223 192.0.2.1 5000 typ host\r\n'
       'a=end-of-candidates\r\na=setup:active\r\n'
       'm=application 5000 UDP/DTLS/SCTP webrtc-datachannel\r\n'
       'c=IN IP4 192.0.2.1\r\na=mid:1\r\na=sctp-port:5000\r\n'
       'a=max-message-size:65536\r\na=ice-ufrag:abcd\r\n'
       'a=ice-pwd:abcdefghijklmnopqrstuvwxyz\r\na=setup:active\r\n')
CANDIDATE = {'candidate':'candidate:1 1 udp 2122260223 192.0.2.1 5000 typ host',
             'sdpMid':'0', 'sdpMLineIndex':0}


class Denied(Exception):
    status = 403
    public_error = {'error':'forbidden'}


class FakePeer:
    def __init__(self):
        self.iceGatheringState = 'new'
        self.localDescription = None
        self.remote = []
        self.candidates = []
        self.offer_entered = asyncio.Event()
        self.offer_release = asyncio.Event()
        self.offer_release.set()
        self.failure = False

    async def setRemoteDescription(self, description):
        self.offer_entered.set()
        await self.offer_release.wait()
        if self.failure:
            raise ValueError('private error must not reach HTTP')
        self.remote.append(description)

    async def createAnswer(self):
        return SimpleNamespace(type='answer', sdp=SDP)

    async def setLocalDescription(self, description):
        self.localDescription = description
        self.iceGatheringState = 'complete'

    async def addIceCandidate(self, candidate):
        self.candidates.append(candidate)


class FakeCall:
    def __init__(self):
        self.peer = FakePeer()
        self.input_ended = asyncio.Event()
        self.turns_settled = asyncio.Event()
        self.turns_settled.set()
        self.close_complete = asyncio.Event()
        self.close_entered = asyncio.Event()
        self.close_release = asyncio.Event()
        self.close_release.set()
        self.worker_started = asyncio.Event()
        self.tasks = set()
        self.closed = False
        self.input_lost = False
        self.close_count = self.process_count = 0

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def process_turns(self):
        self.process_count += 1
        self.worker_started.set()
        await asyncio.Event().wait()

    async def close(self):
        self.close_count += 1
        self.close_entered.set()
        if self.input_lost:
            await self.turns_settled.wait()
        await self.close_release.wait()
        self.closed = True
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        self.close_complete.set()


class SDKHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(adapter, 'SDK HTTP adapter is missing')
        self.active, self.calls, self.admissions = set(), [], []
        self.admission_entered = asyncio.Event()
        self.admission_release = asyncio.Event()
        self.admission_release.set()
        self.denied = False
        self.context = SimpleNamespace(instance_url=ORIGIN, assistant_id=ASSISTANT,
            voice_agent_id=AGENT, sdk_agent_id='agent_operator', receive_data=True)
        self.config = SimpleNamespace(instance_name=INSTANCE, instance_url=ORIGIN,
            voice_service_id=ASSISTANT, required_agent_id=AGENT,
            auth_mode='servicenow', development_token='', max_call_seconds=1800)
        async def admit(headers, body, *, query_string):
            self.admissions.append((headers, body, query_string))
            self.admission_entered.set()
            await self.admission_release.wait()
            if self.denied:
                raise Denied()
            return self.context
        def make_call():
            call = FakeCall()
            self.calls.append(call)
            return call
        self.app = web.Application()
        self.manager = adapter.register_sdk_routes(self.app, self.config, self.active, make_call, admit)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.patches = [patch.object(adapter, '_session_description',
                                      lambda sdp, kind: SimpleNamespace(sdp=sdp, type=kind)),
                        patch.object(adapter, '_ice_candidate', lambda value: dict(value))]
        for item in self.patches:
            item.start()

    async def asyncTearDown(self):
        if adapter is None:
            return
        for call in getattr(self, 'calls', []):
            call.close_release.set()
            call.peer.offer_release.set()
            call.turns_settled.set()
        if hasattr(self, 'client'):
            await self.client.close()
        for item in getattr(self, 'patches', []):
            item.stop()

    def headers(self, token=TOKEN, **extra):
        return {'Authorization':'Bearer ' + token, **extra}

    async def create(self, **kwargs):
        return await self.client.post(BASE + QUERY, json={'agent_id':'agent_operator'},
                                      headers=self.headers(), **kwargs)

    async def session(self):
        response = await self.create()
        self.assertEqual(response.status, 201, await response.text())
        return (await response.json())['session_id']

    async def offer(self, session_id):
        return await self.client.post(BASE + '/' + session_id + '/offer',
            headers=self.headers(), json={'type':'offer','sdp':SDP})

    async def test_exact_create_wire_and_raw_admission_input(self):
        response = await self.create()
        self.assertEqual(response.status, 201)
        data = await response.json()
        self.assertEqual(set(data), {'session_id','agent_id','created_at','iceServers','endpoint_url'})
        self.assertRegex(data['session_id'], r'^[0-9a-f]{32}$')
        self.assertEqual(data['agent_id'], 'agent_operator')
        self.assertIsInstance(data['created_at'], str)
        self.assertEqual(data['iceServers'], [{'urls':['stun:stun.l.google.com:19302']}])
        self.assertIsNone(data['endpoint_url'])
        self.assertNotIn('Set-Cookie', response.headers)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        headers, body, query = self.admissions[0]
        self.assertIsInstance(headers, list)
        self.assertTrue(all(isinstance(x, tuple) and len(x)==2 for x in headers))
        self.assertEqual(json.loads(body), {'agent_id':'agent_operator'})
        self.assertEqual(query, QUERY[1:])
        self.assertEqual(self.calls[0].process_count, 0)
        self.assertNotIn(TOKEN, repr(self.manager.sessions))

    async def test_denial_precedes_call_allocation(self):
        self.denied = True
        response = await self.create()
        self.assertEqual(response.status, 403)
        self.assertEqual(await response.json(), {'error':'forbidden'})
        self.assertEqual(self.calls, [])
        self.assertFalse(self.active)

    async def test_fixed_config_gate_and_verified_context(self):
        self.config.development_token = 'do-not-authorize-sdk'
        response = await self.create()
        self.assertEqual(response.status, 403)
        self.assertEqual(self.admissions, [])
        self.assertEqual(self.calls, [])

    async def test_all_configuration_pins_are_required(self):
        for name,value in [('auth_mode','deny'),('instance_name','other'),
                           ('instance_url','https://other.example'),
                           ('voice_service_id','0'*32),('required_agent_id','0'*32),
                           ('max_call_seconds',float('inf'))]:
            original = getattr(self.config,name)
            setattr(self.config,name,value)
            with self.subTest(name=name):
                self.assertEqual((await self.create()).status,403)
            setattr(self.config,name,original)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.admissions,[])

    async def test_verified_context_is_rechecked_before_allocation(self):
        self.context.assistant_id = '0'*32
        self.assertEqual((await self.create()).status,403)
        self.assertEqual(self.calls,[])
        self.assertFalse(self.active)

    async def test_create_duplicate_auth_rejected_before_platform_admission(self):
        response = await self.client.post(BASE+QUERY, json={'agent_id':'agent_operator'},
            headers=[('Authorization','Bearer '+TOKEN),('Authorization','Bearer '+TOKEN)])
        self.assertEqual(response.status,401)
        self.assertEqual(self.admissions,[])
        self.assertEqual(self.calls,[])

    async def test_capacity_is_atomic_after_authorization_await(self):
        self.admission_release.clear()
        first = asyncio.create_task(self.create())
        second = asyncio.create_task(self.create())
        await self.admission_entered.wait()
        await asyncio.sleep(0)
        self.assertFalse(self.active)
        self.admission_release.set()
        results = await asyncio.gather(first, second)
        self.assertEqual(sorted(x.status for x in results), [201,503])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.active), 1)

    async def test_existing_browser_call_owns_shared_capacity(self):
        browser = object()
        self.active.add(browser)
        response = await self.create()
        self.assertEqual(response.status, 503)
        self.assertEqual(self.calls, [])
        self.active.discard(browser)

    async def test_flat_offer_nested_answer_and_single_worker(self):
        sid = await self.session()
        response = await self.offer(sid)
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual(await response.json(), {'sdp':{'type':'answer','sdp':SDP}})
        await self.calls[0].worker_started.wait()
        response = await self.offer(sid)
        self.assertEqual(response.status, 409)
        self.assertEqual(len(self.calls[0].peer.remote), 1)
        self.assertEqual(self.calls[0].process_count, 1)

    async def test_preoffer_candidates_are_queued_and_flushed_after_offer(self):
        sid = await self.session()
        path = BASE + '/' + sid
        response = await self.client.post(path + '/candidate', headers=self.headers(), json=CANDIDATE)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.calls[0].peer.candidates, [])
        response = await self.offer(sid)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.calls[0].peer.candidates, [CANDIDATE])
        response = await self.client.get(path + '/candidates', headers=self.headers())
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {'candidates':[]})

    async def test_followups_require_bound_bearer_and_no_query(self):
        sid = await self.session()
        path = BASE + '/' + sid + '/candidates'
        for headers, suffix, status in [(self.headers('wrong'), '',404), ({},'',401),
                                        (self.headers(), '?auth_token=secret',400),
                                        (self.headers(Origin='https://evil.example'),'',403),
                                        (self.headers(Cookie='session=confused'),'',401)]:
            with self.subTest(headers=headers, suffix=suffix):
                response = await self.client.get(path + suffix, headers=headers)
                self.assertEqual(response.status, status)
        response = await self.client.get(BASE + '/00000000000000000000000000000000/candidates', headers=self.headers())
        self.assertEqual(response.status, 404)

    async def test_duplicate_authorization_and_origin_denied(self):
        sid = await self.session()
        path = BASE + '/' + sid + '/candidates'
        for extra, status in [('Authorization',401), ('Origin',400)]:
            headers = [('Authorization','Bearer '+TOKEN), ('Origin',ORIGIN),
                       (extra, 'Bearer '+TOKEN if extra == 'Authorization' else ORIGIN)]
            response = await self.client.get(path, headers=headers)
            self.assertEqual(response.status, status)

    async def test_strict_offer_and_candidate_payloads(self):
        sid = await self.session()
        for data in [{'type':'offer','sdp':{'sdp':SDP}}, {'type':'answer','sdp':SDP},
                     {'type':'offer','sdp':SDP,'extra':True}]:
            response = await self.client.post(BASE+'/'+sid+'/offer', headers=self.headers(), json=data)
            self.assertEqual(response.status, 400)
        response = await self.client.post(BASE+'/'+sid+'/offer', headers=self.headers(**{'Content-Type':'application/json'}),
            data='{"type":"offer","type":"offer","sdp":"v=0\\r\\n"}')
        self.assertEqual(response.status,400)
        for data in [{**CANDIDATE,'sdpMLineIndex':True}, {**CANDIDATE,'candidate':'x'*4097},
                     {'candidate':CANDIDATE}, {**CANDIDATE,'sdpMid':None}]:
            response = await self.client.post(BASE+'/'+sid+'/candidate', headers=self.headers(), json=data)
            self.assertEqual(response.status,400)
        self.assertEqual(self.calls[0].peer.remote, [])

    async def test_request_body_is_bounded_before_admission(self):
        response = await self.client.post(BASE+QUERY, headers=self.headers(**{'Content-Type':'application/json'}),
            data=b'x'*32769)
        self.assertEqual(response.status,413)
        self.assertEqual(self.admissions, [])

    async def test_candidate_queue_is_bounded(self):
        sid = await self.session()
        for _ in range(adapter.MAX_PENDING_CANDIDATES):
            response = await self.client.post(BASE+'/'+sid+'/candidate',headers=self.headers(),json=CANDIDATE)
            self.assertEqual(response.status,200)
        response = await self.client.post(BASE+'/'+sid+'/candidate',headers=self.headers(),json=CANDIDATE)
        self.assertEqual(response.status,429)

    async def test_offer_failure_cleans_call_without_private_error(self):
        sid = await self.session()
        self.calls[0].peer.failure = True
        response = await self.offer(sid)
        self.assertEqual(response.status,400)
        self.assertNotIn('private', await response.text())
        await self.calls[0].close_complete.wait()
        await asyncio.sleep(0)
        self.assertFalse(self.active)
        self.assertEqual(self.calls[0].process_count,0)

    async def test_delete_waits_for_close_complete_before_capacity_release(self):
        sid = await self.session()
        call = self.calls[0]
        call.close_release.clear()
        deleting = asyncio.create_task(self.client.delete(BASE+'/'+sid,headers=self.headers()))
        await call.close_entered.wait()
        self.assertIn(call,self.active)
        response = await self.create()
        self.assertEqual(response.status,503)
        call.close_release.set()
        response = await deleting
        self.assertEqual(response.status,204)
        self.assertFalse(self.active)
        response = await self.client.delete(BASE+'/'+sid,headers=self.headers())
        self.assertEqual(response.status,204)
        response = await self.client.delete(BASE+'/'+sid,headers=self.headers('wrong'))
        self.assertEqual(response.status,404)
        self.assertEqual(call.close_count,1)

    async def test_input_loss_waits_for_submitted_turn_settlement(self):
        sid = await self.session()
        self.assertEqual((await self.offer(sid)).status,200)
        call = self.calls[0]
        call.input_lost = True
        call.turns_settled.clear()
        call.input_ended.set()
        await asyncio.sleep(.01)
        self.assertIn(call,self.active)
        self.assertFalse(call.close_complete.is_set())
        call.turns_settled.set()
        await asyncio.wait_for(call.close_complete.wait(),1)
        await asyncio.sleep(0)
        self.assertNotIn(call,self.active)

    async def test_pending_handshake_expires(self):
        with patch.object(adapter,'HANDSHAKE_SECONDS',.02):
            sid = await self.session()
        call = self.calls[0]
        await asyncio.wait_for(call.close_complete.wait(),1)
        await asyncio.sleep(0)
        self.assertNotIn(call,self.active)
        self.assertEqual((await self.offer(sid)).status,410)

    async def test_call_deadline_closes_offered_session(self):
        self.config.max_call_seconds = .05
        sid = await self.session()
        self.assertEqual((await self.offer(sid)).status,200)
        await asyncio.wait_for(self.calls[0].close_complete.wait(),1)
        await asyncio.sleep(0)
        self.assertFalse(self.active)

    async def test_shutdown_awaits_sdk_close(self):
        sid = await self.session()
        call = self.calls[0]
        call.close_release.clear()
        closing = asyncio.create_task(self.manager.shutdown())
        await call.close_entered.wait()
        self.assertFalse(closing.done())
        self.assertIn(call,self.active)
        call.close_release.set()
        await closing
        self.assertFalse(self.active)
        self.assertEqual((await self.create()).status,503)

    async def test_cancellation_of_delete_does_not_orphan_close(self):
        sid = await self.session()
        call = self.calls[0]
        call.close_release.clear()
        deleting = asyncio.create_task(self.client.delete(BASE+'/'+sid,headers=self.headers()))
        await call.close_entered.wait()
        deleting.cancel()
        with suppress(asyncio.CancelledError):
            await deleting
        self.assertIn(call,self.active)
        call.close_release.set()
        await asyncio.wait_for(call.close_complete.wait(),1)
        await asyncio.sleep(.01)
        self.assertFalse(self.active)

    async def test_delete_returns_202_while_submitted_turn_is_settling(self):
        sid = await self.session()
        call = self.calls[0]
        call.input_lost = True
        call.turns_settled.clear()
        response = await asyncio.wait_for(self.client.delete(BASE+'/'+sid,headers=self.headers()),1)
        self.assertEqual(response.status,202)
        self.assertIn(call,self.active)
        self.assertFalse(call.close_complete.is_set())
        call.turns_settled.set()
        await asyncio.wait_for(call.close_complete.wait(),1)
        await asyncio.sleep(0)
        self.assertFalse(self.active)

    async def test_delete_during_offer_fences_worker_start(self):
        sid = await self.session()
        call = self.calls[0]
        call.peer.offer_release.clear()
        offering = asyncio.create_task(self.offer(sid))
        await call.peer.offer_entered.wait()
        response = await self.client.delete(BASE+'/'+sid,headers=self.headers())
        self.assertIn(response.status,(202,204))
        await asyncio.wait_for(call.close_complete.wait(),1)
        call.peer.offer_release.set()
        with suppress(Exception,asyncio.CancelledError):
            await offering
        self.assertEqual(call.process_count,0)
        self.assertFalse(self.active)

    async def test_concurrent_duplicate_offers_negotiate_once(self):
        sid = await self.session()
        call = self.calls[0]
        call.peer.offer_release.clear()
        first = asyncio.create_task(self.offer(sid))
        await call.peer.offer_entered.wait()
        second = asyncio.create_task(self.offer(sid))
        await asyncio.sleep(0)
        call.peer.offer_release.set()
        responses = await asyncio.gather(first,second)
        self.assertEqual(sorted(x.status for x in responses),[200,409])
        await call.worker_started.wait()
        self.assertEqual(call.process_count,1)

    async def test_shutdown_during_admission_cannot_allocate_call(self):
        self.admission_release.clear()
        creating = asyncio.create_task(self.create())
        await self.admission_entered.wait()
        await self.manager.shutdown()
        self.admission_release.set()
        self.assertEqual((await creating).status,503)
        self.assertEqual(self.calls,[])

    async def test_encoded_query_is_preserved(self):
        from yarl import URL
        raw = 'instance_name='+INSTANCE+'&receive_data=%74rue'
        response = await self.client.post(URL(BASE+'?'+raw,encoded=True),
            headers=self.headers(),json={'agent_id':'agent_operator'})
        self.assertEqual(response.status,201)
        self.assertEqual(self.admissions[0][2],raw)

    async def test_unready_candidate_poll_is_not_empty_success(self):
        sid = await self.session()
        response = await self.client.get(BASE+'/'+sid+'/candidates',headers=self.headers())
        self.assertEqual(response.status,409)

    async def test_offer_timeout_owns_cleanup(self):
        sid = await self.session()
        call = self.calls[0]
        call.peer.offer_release.clear()
        with patch.object(adapter,'OFFER_SECONDS',.02):
            response = await self.offer(sid)
        self.assertEqual(response.status,400)
        await asyncio.wait_for(call.close_complete.wait(),1)
        await asyncio.sleep(0)
        self.assertFalse(self.active)
        self.assertEqual(call.process_count,0)

    async def test_incomplete_ice_and_oversized_answer_are_never_published(self):
        sid = await self.session()
        call = self.calls[0]
        async def oversized(description):
            call.peer.iceGatheringState='complete'
            call.peer.localDescription=SimpleNamespace(type='answer',sdp='v=0\r\n'+'x'*8192)
        call.peer.setLocalDescription=oversized
        self.assertEqual((await self.offer(sid)).status,400)
        await asyncio.wait_for(call.close_complete.wait(),1)
        await asyncio.sleep(0)
        self.assertEqual(call.process_count,0)
        self.assertFalse(self.active)

    async def test_sdk_answer_validation_checks_section_attributes(self):
        validate = getattr(adapter,'_sdk_answer_compatible',lambda sdp:False)
        self.assertTrue(validate(SDP),'dual media SDP fixture must satisfy SDK validator')
        for invalid in [SDP+'a=ice-options:trickle\r\n',
                SDP.replace('a=sctp-port:5000','a=sctpmap:5000 webrtc-datachannel 65535'),
                SDP.replace('a=rtpmap:111 opus','a=rtpmap:111 imaginary'),
                SDP.replace('a=mid:0','a=mid:0\r\nb=AS:511'),
                SDP.replace('a=mid:0','a=mid:0\r\na=ssrc:1 cname:x\r\na=ssrc:2 cname:y\r\na=ssrc:3 cname:z'),
                SDP.replace('m=audio','m=video'),
                'v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n']:
            with self.subTest(invalid=invalid[:40]):
                self.assertFalse(validate(invalid))

    async def test_sdk_guard_rejects_malformed_media_and_unadvertised_payload(self):
        for invalid in [SDP.replace('a=rtpmap:111 opus','a=rtpmap:112 opus'),
                SDP.replace('m=audio 5000 UDP/TLS/RTP/SAVPF 111','m=audio'),
                SDP.replace('m=application 5000 UDP/DTLS/SCTP webrtc-datachannel','m=application')]:
            with self.subTest(invalid=invalid[:40]):
                self.assertFalse(adapter._sdk_answer_compatible(invalid))

    async def test_sdk_guard_returns_false_for_invalid_unicode_and_large_bandwidth(self):
        for invalid in [SDP.replace('s=-','s=\ud800'),
                SDP.replace('a=mid:0','a=mid:0\r\nb=AS:'+'9'*4400)]:
            with self.subTest(kind='unicode' if '\ud800' in invalid else 'bandwidth'):
                try:
                    accepted = adapter._sdk_answer_compatible(invalid)
                except (UnicodeError,ValueError) as error:
                    self.fail('Guard raised '+type(error).__name__+' instead of returning False')
                self.assertFalse(accepted)


@unittest.skipUnless(importlib.util.find_spec('aiortc'), 'aiortc is not installed; no packages installed for this candidate')
class RealAiortcTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_audio_and_data_answer_embeds_candidates_and_passes_sdk_bounds(self):
        from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection
        self.assertIsNotNone(adapter)
        # Host ICE only: no STUN, TURN, platform, ASR or TTS network request.
        client = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        server = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        try:
            client.addTransceiver('audio',direction='sendrecv')
            client.createDataChannel('transcripts')
            server.addTrack(AudioStreamTrack())
            await client.setLocalDescription(await client.createOffer())
            await server.setRemoteDescription(adapter._session_description(client.localDescription.sdp,'offer'))
            await server.setLocalDescription(await server.createAnswer())
            self.assertEqual(server.iceGatheringState,'complete')
            self.assertIn('a=candidate:',server.localDescription.sdp)
            self.assertEqual(server.localDescription.sdp.count('m='),2)
            self.assertTrue(adapter._sdk_answer_compatible(server.localDescription.sdp))
            await client.setRemoteDescription(adapter._session_description(server.localDescription.sdp,'answer'))
            async with asyncio.timeout(10):
                while client.connectionState != 'connected' or server.connectionState != 'connected':
                    await asyncio.sleep(.01)
        finally:
            await client.close()
            await server.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
