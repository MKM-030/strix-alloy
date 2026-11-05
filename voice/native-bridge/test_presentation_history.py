"""CPU-only optional history boundary and finite publisher checks."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_duplex as duplex
from test_native_duplex import FakeCall
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from voice.bridge import Bridge, Settings, Conversation, ConversationBinding
from voice.caller_binding import CALLER_CREATE_PATH, CALLER_SERVICE_ID, CALLER_AGENT_ID, CALLER_PROFILE_ID
from native_bridge import Dialog, Config


def receipt(event, request_id='e'*32):
    return dict(status='success', state='presentation_history_stored', requestId=request_id,
        conversationId='c'*32, sequence=event['sequence'], eventId=event['event_id'],
        textSha256=event['text_sha256'], stored=True, hostEmitted=True, heard=False, promptIncluded=False)


def load_history():
    path = Path(__file__).resolve().parents[1] / 'presentation_history.py'
    assert path.is_file(), 'missing optional presentation history implementation'
    spec = importlib.util.spec_from_file_location('test_presentation_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PresentationContractTests(unittest.IsolatedAsyncioTestCase):
    def event(self):
        return dict(version=1, kind='local_conversation_history', local_output_state='host_emitted',
            native_request_binding='unavailable', owner_id='a'*32, event_id='b'*32, sequence=1,
            caller_turn_id='c'*32, original_asr_sha256='d'*64, output_epoch=1,
            task_revision=1, playback_generation=0, text='Mir fehlen noch Datum und Führungskraft.',
            text_sha256=hashlib.sha256('Mir fehlen noch Datum und Führungskraft.'.encode()).hexdigest(),
            accepted_samples=960, emitted_samples=960)

    async def test_dto_rejects_business_authority_partial_and_unknown_fields(self):
        h=load_history();event=self.event();self.assertEqual(h.validate_event(event),event)
        for change in ({'heard':True},{'native_request_binding':'current'}, {'emitted_samples':1},
                       {'sequence':17},{'owner_id':'other'},{'text_sha256':'0'*64},
                       {'text':'x'*2001},{'caller_turn_id':None},{'sequence':True}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                h.validate_event(dict(event,**change))

    async def test_exactly_one_thousand_astral_pairs_fit_two_thousand_utf16_units(self):
        h=load_history();text='\U0001f600'*1000
        event=dict(self.event(),text=text,text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())
        self.assertEqual(h.validate_event(event),event)

    async def test_one_thousand_and_one_astral_pairs_exceed_utf16_limit(self):
        h=load_history();text='\U0001f600'*1001
        event=dict(self.event(),text=text,text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())
        with self.assertRaises(ValueError):h.validate_event(event)

    async def test_maximum_escaped_event_with_full_metadata_fits_existing_json_wire_limit(self):
        h=load_history()
        for text in ('\U0001f600'*1000,'\x01'*2000):
            with self.subTest(utf8_bytes=len(text.encode('utf-8'))):
                event=dict(self.event(),text=text,text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                    sequence=16,output_epoch=2147483647,task_revision=2147483647,
                    playback_generation=2147483647,accepted_samples=43200000,emitted_samples=43200000)
                h.validate_event(event)
                payload=dict(operation='presentation_history_store',requestId='e'*32,
                    appInboundId='scc-local-voice',clientSessionId='f'*32,userId='voice-'+'f'*32,
                    callerUserId='1'*32,conversationBinding=dict(source='servicenow_create_conversation',
                        conversationId='2'*32,creationMessageId='3'*32,createRequestId='4'*32,interactionId='5'*32),
                    event=event,grantNonce='a9'*32)
                self.assertLessEqual(len(json.dumps(text,ensure_ascii=True).encode('utf-8')),12002)
                self.assertLessEqual(len(json.dumps(payload,ensure_ascii=True).encode('utf-8')),16384)

    async def test_outbox_attempts_once_and_stops_only_optional_lane_on_uncertainty(self):
        h=load_history();outbox=h.PresentationOutbox('a'*32);seen=[]
        async def fail(event):seen.append(event);raise RuntimeError('private details')
        self.assertTrue(outbox.offer(self.event()))
        self.assertFalse(outbox.offer(self.event()))
        await outbox.run(fail)
        self.assertEqual(len(seen),1);self.assertTrue(outbox.disabled)
        self.assertFalse(outbox.offer(dict(self.event(),sequence=2,event_id='e'*32)))

    async def test_outbox_close_cancels_pending_publication(self):
        h=load_history();outbox=h.PresentationOutbox('a'*32);entered=asyncio.Event()
        async def wait(event):entered.set();await asyncio.Event().wait()
        outbox.offer(self.event());task=asyncio.create_task(outbox.run(wait))
        await entered.wait();outbox.close();task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        self.assertTrue(outbox.disabled)

    async def test_only_exact_true_acknowledges_outbox_publication(self):
        for result in (None,0,1,'ok',{},False):
            with self.subTest(result=result):
                h=load_history();outbox=h.PresentationOutbox('a'*32);seen=[]
                async def publish(event):seen.append(event);return result
                outbox.offer(self.event());outbox.offer(dict(self.event(),sequence=2,event_id='e'*32))
                task=asyncio.create_task(outbox.run(publish))
                try:
                    await asyncio.sleep(.01)
                    self.assertTrue(outbox.disabled)
                    self.assertEqual(len(seen),1)
                finally:
                    task.cancel();await asyncio.gather(task,return_exceptions=True)

    async def test_sixteen_slots_are_finite_and_never_reused(self):
        h=load_history();outbox=h.PresentationOutbox('a'*32)
        for sequence in range(1,17):
            self.assertTrue(outbox.offer(dict(self.event(),sequence=sequence,event_id=f'{sequence:032x}')))
        self.assertFalse(outbox.offer(dict(self.event(),sequence=17)))
        self.assertEqual(outbox.sequence,16);outbox.close()

    async def test_unavailable_optional_publisher_adds_no_production_warning_or_business_work(self):
        call=FakeCall();call.dialog.native_owner_id='a'*32
        async def publish(event):return False
        lane=duplex.NativeDuplex(call,presentation_publisher=publish)
        with patch.object(duplex.LOG,'warning') as warning:
            running=asyncio.create_task(lane.run())
            try:
                lane._presentation_outbox.offer(self.event())
                await asyncio.sleep(.02)
                self.assertTrue(lane._presentation_outbox.disabled)
                self.assertFalse(running.done());self.assertEqual(call.dialog.calls,[])
                warning.assert_not_called()
            finally:
                running.cancel();await asyncio.gather(running,return_exceptions=True);await lane.close()

    async def test_only_complete_original_local_speech_publishes_after_drain(self):
        published=[]
        async def publish(event):published.append(event);return True
        call=FakeCall();call.dialog.native_owner_id='a'*32
        lane=duplex.NativeDuplex(call,presentation_publisher=publish)
        original=(0,'Welche Angaben fehlen?',3,'c'*32,0)
        item=duplex._Output('Noch Datum und Führungskraft.',original,lane.epoch,lane.task_revision,None,'conversation')
        state=lane._begin_speech(item)
        state['lease']=duplex._SpeechLease(item,call.playback.generation,lane.epoch,None,None)
        call.playback.put(b'\1\0'*960,call.playback.generation)
        worker=asyncio.create_task(lane._presentation_outbox.run(publish))
        try:
            lane._finish_speech(state,complete=True)
            await asyncio.sleep(0);self.assertEqual(published,[])
            call.playback.read(1920);lane._update_speech_cursor();lane._update_speech_cursor()
            await asyncio.sleep(0)
            self.assertEqual(len(published),1)
            self.assertEqual(published[0]['caller_turn_id'],'c'*32)
            self.assertEqual(published[0]['original_asr_sha256'],hashlib.sha256(original[1].encode()).hexdigest())
            self.assertEqual(published[0]['native_request_binding'],'unavailable')
            self.assertEqual(call.dialog.calls,[])
        finally:
            worker.cancel();await asyncio.gather(worker,return_exceptions=True);await lane.close()

    async def test_default_disabled_and_nonlocal_speech_never_allocates_history(self):
        call=FakeCall();lane=duplex.NativeDuplex(call)
        self.assertIsNone(lane._presentation_outbox)
        await lane.close()
        for kind in ('backend','backend_control','confirmation_ack','greeting','processing'):
            async def publish(event):self.fail('nonlocal speech published')
            call=FakeCall();call.dialog.native_owner_id='a'*32
            lane=duplex.NativeDuplex(call,presentation_publisher=publish)
            item=duplex._Output('Vollständige echte Antwort.',None,1,1,None,kind)
            state=lane._begin_speech(item);state['lease']=duplex._SpeechLease(item,0,1,None,None)
            call.playback.put(b'\1\0'*960,0);call.playback.read(1920);lane._finish_speech(state,complete=True)
            self.assertEqual(lane._presentation_outbox.sequence,0)
            await lane.close()

    async def test_interrupted_partial_or_obsolete_local_lease_is_never_published(self):
        for reason in ('partial','interrupted','closed','generation','no_lease'):
            async def publish(event):self.fail('unproved complete speech published')
            call=FakeCall();call.dialog.native_owner_id='a'*32
            lane=duplex.NativeDuplex(call,presentation_publisher=publish)
            item=duplex._Output('Die lokale Antwort.',None,1,1,None,'conversation')
            state=lane._begin_speech(item);state['lease']=duplex._SpeechLease(item,0,1,None,None)
            call.playback.put(b'\1\0'*960,0)
            call.playback.read(960 if reason=='partial' else 1920)
            if reason=='interrupted':state['interrupted']=True
            if reason=='closed':call.closing=True
            if reason=='generation':call.playback.interrupt()
            if reason=='no_lease':state['lease']=None
            lane._finish_speech(state,complete=True)
            self.assertEqual(lane._presentation_outbox.sequence,0,reason)
            await lane.close()


class PresentationTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent=[];self.bad=False
        async def receive(request):
            payload=await request.json();self.sent.append(payload)
            value=receipt(payload['event'],payload['requestId'])
            if self.bad=='wrapper':return web.json_response({'status':'failure','result':value})
            if self.bad:value['heard']=True
            return web.json_response({'result':value})
        fake=web.Application();fake.router.add_post('/api/global/scc_voice_context/updates',receive)
        self.bot=TestServer(fake);await self.bot.start_server()
        self.bridge=Bridge(Settings(instance_url='https://example.invalid',user_id='owned-provider-user',email='test@example.invalid',presentation_history_enabled=True,
            caller_binding_service_id=CALLER_SERVICE_ID,caller_binding_agent_id=CALLER_AGENT_ID,
            caller_create_api_path=CALLER_CREATE_PATH),'provider-secret','audio','callback')
        self.bridge.bot_url=str(self.bot.make_url('/api/bot'))
        self.client=TestClient(TestServer(self.bridge.ui_app()),cookie_jar=CookieJar(unsafe=True));await self.client.start_server()
        self.bridge.origin=str(self.client.make_url('/')).rstrip('/')
        state=await(await self.client.get('/api/session')).json()
        self.headers={'Origin':self.bridge.origin,'X-CSRF-Token':state['csrf']}
        self.session=next(iter(self.bridge.sessions.values()))
        s=self.session;s.started=True;s.user_id='voice-'+s.sid;s.caller_user_id='1'*32;s.caller_email='test@example.invalid'
        s.conversation_binding=ConversationBinding('c'*32,'d'*32,'e'*32)
        s.voice_context={'voice_assistant':CALLER_SERVICE_ID,'global_context_profile':CALLER_PROFILE_ID}
        # This transport fixture represents an already corroborated private grant.
        s.presentation_provider_user_id='voice-'+'b'*32
        s.presentation_nonce='a9'*32
        s.presentation_deadline=__import__('time').monotonic()+60
        s.presentation_identity=self.bridge.owned_cleanup_identity(s)

    async def asyncTearDown(self):
        await self.client.close();await self.bot.close()

    def event(self):return PresentationContractTests().event()

    async def post(self,event=None,headers=None):
        return await self.client.post('/api/presentation-history',json=event or self.event(),headers=headers or self.headers)

    async def test_disabled_route_performs_no_external_request(self):
        self.bridge.settings.presentation_history_enabled=False
        response=await self.post();self.assertEqual(response.status,404);self.assertEqual(self.sent,[])
        self.assertFalse(Settings().presentation_history_enabled)

    async def test_without_exact_attested_private_nonce_no_guest_publication(self):
        self.session.presentation_nonce=''
        response=await self.post()
        self.assertFalse((await response.json())['stored']);self.assertEqual(self.sent,[])
        self.assertFalse(self.session.failed)

    async def test_grant_ready_during_business_bootstrap_does_not_disable_history(self):
        self.session.bootstrap_stage='waiting_input'
        self.session.pending_action='START_CREATED_CONVERSATION'
        response=await self.post()
        self.assertTrue((await response.json())['stored'])
        self.assertFalse(self.session.presentation_disabled)
        self.assertEqual(self.session.bootstrap_stage,'waiting_input')

    async def test_only_optional_publication_waits_for_pending_private_grant(self):
        self.session.presentation_nonce=''
        release=asyncio.Event()
        async def attest():
            await release.wait()
            self.session.presentation_nonce='a9'*32
        task=asyncio.create_task(attest());self.session.presentation_task=task
        publishing=asyncio.create_task(self.post())
        await asyncio.sleep(.01)
        self.assertFalse(publishing.done());self.assertEqual(self.sent,[])
        release.set();response=await publishing;await task
        self.session.presentation_task=None
        self.assertTrue((await response.json())['stored']);self.assertEqual(len(self.sent),1)

    async def test_expired_or_drifted_grant_is_erased_without_dispatch(self):
        self.session.presentation_deadline=0
        response=await self.post()
        self.assertFalse((await response.json())['stored'])
        self.assertFalse(self.session.presentation_nonce);self.assertEqual(self.sent,[])

    async def test_separate_history_receipt_preserves_original_backend_state(self):
        s=self.session;s.busy=True;s.requests.append('original-business');s.pending_action='MESSAGE'
        s.pending_since=__import__('time').monotonic()
        response=await self.post();self.assertEqual(response.status,200)
        self.assertTrue((await response.json())['stored']);self.assertEqual(len(self.sent),1)
        value=self.sent[0];self.assertEqual(value['operation'],'presentation_history_store')
        self.assertEqual(value['grantNonce'],'a9'*32)
        self.assertEqual(value['providerContextUserId'],'voice-'+'b'*32)
        self.assertEqual(value['userId'],s.user_id)
        self.assertEqual(value['clientSessionId'],s.sid)
        self.assertEqual(value['callerUserId'],s.caller_user_id);self.assertEqual(value['event'],self.event())
        self.assertNotIn('message',value);self.assertNotIn('caller_updates',value)
        self.assertTrue(s.busy);self.assertEqual(list(s.requests),['original-business'])
        self.assertEqual(s.pending_action,'MESSAGE');self.assertFalse(s.failed)

    async def test_uncertain_receipt_disables_only_history_and_never_retries(self):
        self.bad=True
        response=await self.post();self.assertFalse((await response.json())['stored'])
        self.assertFalse(self.session.failed);self.assertFalse(self.session.ended)
        response=await self.post();self.assertFalse((await response.json())['stored']);self.assertEqual(len(self.sent),1)

    async def test_failure_wrapper_cannot_be_promoted_by_a_success_shaped_nested_receipt(self):
        self.bad='wrapper'
        response=await self.post();self.assertFalse((await response.json())['stored'])
        self.assertFalse(self.session.failed)

    async def test_owner_sequence_profile_csrf_and_schema_refused_without_dispatch(self):
        for change in ({'sequence':2},{'heard':True},{'emitted_samples':2}):
            response=await self.post(dict(self.event(),**change));self.assertEqual(response.status,400)
        self.session.voice_context['global_context_profile']='f'*32
        response=await self.post();self.assertEqual(response.status,409)
        response=await self.post(headers={'Origin':self.bridge.origin,'X-CSRF-Token':'wrong'});self.assertEqual(response.status,403)
        self.assertEqual(self.sent,[])

    async def test_later_owner_or_duplicate_slot_cannot_replace_stored_history(self):
        self.assertTrue((await(await self.post()).json())['stored'])
        for value in (self.event(),dict(self.event(),sequence=2,owner_id='f'*32)):
            response=await self.post(value);self.assertEqual(response.status,400)
        self.assertEqual(len(self.sent),1)
        self.assertFalse(self.session.failed)

    async def test_provider_user_must_match_the_same_original_caller_create_session(self):
        self.session.user_id='different-provider-user'
        response=await self.post();self.assertEqual(response.status,409)
        self.assertEqual(self.sent,[])

    async def test_dialog_default_disabled_and_exact_receipt_without_business_mutation(self):
        from types import SimpleNamespace
        self.assertFalse(Config().presentation_history_enabled)
        with self.assertRaises(ValueError):Config(presentation_history_enabled=1)
        dialog=Dialog.__new__(Dialog);dialog.config=SimpleNamespace(presentation_history_enabled=False)
        dialog.http=object();dialog.csrf='csrf';dialog.must_reset=False;dialog.metadata={'conversation_id':'c'*32}
        events=[]
        async def request(method,path,**kwargs):events.append((method,path,kwargs));return receipt(kwargs['json'])
        dialog.request=request
        self.assertFalse(await dialog.publish_presentation_history(self.event()));self.assertEqual(events,[])
        dialog.config.presentation_history_enabled=True
        self.assertTrue(await dialog.publish_presentation_history(self.event()))
        self.assertEqual(events[0][:2],('POST','/api/presentation-history'))


class PublicationBudgetTests(unittest.IsolatedAsyncioTestCase):
    """In-process fake transport: no HTTP, native service or model calls."""
    async def asyncSetUp(self):
        self.bridge=Bridge(Settings(instance_url='https://example.invalid',user_id='owned-provider-user',
            email='test@example.invalid',presentation_history_enabled=True,
            caller_binding_service_id=CALLER_SERVICE_ID,caller_binding_agent_id=CALLER_AGENT_ID,
            caller_create_api_path=CALLER_CREATE_PATH),'provider-secret','audio','callback')
        s=self.session=Conversation();self.bridge.sessions[s.sid]=s
        s.started=True;s.user_id='voice-'+s.sid;s.caller_user_id='1'*32
        s.conversation_binding=ConversationBinding('c'*32,'d'*32,'e'*32)
        s.voice_context={'voice_assistant':CALLER_SERVICE_ID,'global_context_profile':CALLER_PROFILE_ID}
        s.presentation_provider_user_id='voice-'+'b'*32
        s.presentation_nonce='a9'*32;s.presentation_deadline=time.monotonic()+60
        s.presentation_identity=self.bridge.owned_cleanup_identity(s)
        s.busy=True;s.requests.append('original-business');s.pending_action='MESSAGE'
        s.bootstrap_stage='waiting_input';s.cleanup_state='owned'
        self.event=PresentationContractTests().event()
        self.bridge.json=AsyncMock(return_value=self.event)
        self.calls=[];self.storage_completed=False;self.storage_cancelled=False;self.storage_delay=0
        self.storage_status=200;self.storage_error=None
        self.storage_response=lambda raw:raw
        owner=self
        class Response:
            @property
            def status(self):return owner.storage_status
            async def __aenter__(self):
                if owner.storage_error is not None:
                    raise owner.storage_error
                return self
            async def __aexit__(self,*args):pass
            @property
            def content(self):return self
            async def iter_chunked(self,size):
                try:await asyncio.sleep(owner.storage_delay)
                except asyncio.CancelledError:
                    owner.storage_cancelled=True;raise
                owner.storage_completed=True
                raw=json.dumps({'result':receipt(owner.event,owner.calls[-1]['json']['requestId'])}).encode()
                yield owner.storage_response(raw)
        def post(url,**kwargs):self.calls.append(kwargs);return Response()
        self.bridge.http=SimpleNamespace(post=post)
        self.request=SimpleNamespace(_voice_session=s)

    def business_state(self):
        s=self.session
        return (s.busy,tuple(s.requests),s.pending_action,s.bootstrap_stage,s.cleanup_state,
            s.sequence,s.failed,s.ending,s.ended,s.conversation_binding)

    async def asyncTearDown(self):
        task=self.session.presentation_task
        self.bridge.retire_presentation(self.session)
        if task:await asyncio.gather(task,return_exceptions=True)

    async def publish(self):
        response=await self.bridge.presentation_history(self.request)
        return json.loads(response.body)

    async def test_non200_store_reports_actual_status_without_reading_body_or_replaying(self):
        self.storage_status=503
        self.storage_response=lambda raw:b'PRIVATE_RESPONSE_BODY'
        before=self.business_state()
        with self.assertLogs('voice-bridge',level='INFO') as logged:
            result=await self.publish()
        lines='\n'.join(logged.output)
        self.assertFalse(result['stored'])
        self.assertIn('kind=store stage=http_status',lines)
        self.assertIn('http_status=503 transport=response_received',lines)
        self.assertFalse(self.storage_completed)
        self.assertNotIn('PRIVATE_RESPONSE_BODY',lines)
        self.assertNotIn('a9'*32,lines)
        self.assertEqual(self.business_state(),before)
        self.assertTrue(self.session.presentation_disabled)
        self.assertFalse((await self.publish())['stored'])
        self.assertEqual(len(self.calls),1)

    async def test_pre_response_store_exception_has_distinct_stage_and_no_exception_text(self):
        self.storage_error=OSError('PRIVATE_TRANSPORT_ERROR')
        before=self.business_state()
        with self.assertLogs('voice-bridge',level='INFO') as logged:
            result=await self.publish()
        lines='\n'.join(logged.output)
        self.assertFalse(result['stored'])
        self.assertIn('kind=store stage=dispatch',lines)
        self.assertIn('http_status=0 transport=before_response',lines)
        self.assertNotIn('PRIVATE_TRANSPORT_ERROR',lines)
        self.assertNotIn('a9'*32,lines)
        self.assertFalse(self.storage_completed)
        self.assertEqual(self.business_state(),before)
        self.assertTrue(self.session.presentation_disabled)
        self.assertFalse((await self.publish())['stored'])
        self.assertEqual(len(self.calls),1)

    async def test_store_diagnostic_normalizes_untrusted_status_and_transport_metadata(self):
        history=load_history()
        for status,transport in ((True,'PRIVATE_TRANSPORT'),(-1,{}),(600,None),('PRIVATE_STATUS',[])):
            with self.subTest(status=status),self.assertLogs('voice-bridge',level='INFO') as logged:
                history._receipt_diagnostic('store','dispatch','c'*32,
                    http_status=status,transport=transport)
            lines='\n'.join(logged.output)
            self.assertIn('http_status=0 transport=unavailable',lines)
            self.assertNotIn('PRIVATE',lines)

    async def test_exact_wire_sequence_forms_preserve_business_state_and_strict_dto(self):
        for token,form in ((b'1.0','decimal'),(b'1e0','exponent')):
            await self.asyncSetUp()
            self.storage_response=lambda raw:raw.replace(b'"sequence": 1,',b'"sequence": '+token+b',')
            before=self.business_state()
            with self.subTest(token=token),self.assertLogs('voice-bridge',level='INFO') as logged:
                result=await self.publish()
            self.assertTrue(result['stored'])
            self.assertIs(type(result['sequence']),int)
            self.assertEqual(self.business_state(),before)
            self.assertEqual(len(self.calls),1)
            self.assertTrue(any('kind=store' in line and 'stage=decoded' in line
                                and form+'=1' in line for line in logged.output))

    async def test_bad_wire_sequences_and_json_retire_once_without_business_changes(self):
        tokens=[b'1.0000000000000000000001',b'1e10000',b'1e-10000',b'0e65',b'0e-65',
                b'9007199254740992',b'NaN',b'Infinity',b'-Infinity',b'true',b'"PRIVATE_NUMBER"',
                b'0',b'-1',b'2.0',b'1.'+b'0'*63]
        changes=[lambda raw,token=token:raw.replace(b'"sequence": 1,',b'"sequence": '+token+b',')
                 for token in tokens]
        changes += [lambda raw:raw.replace(b'"sequence": 1,',b'"sequence": 0,"sequence": 1,'),
                    lambda raw:raw.replace(b'"result":',b'"result":{},"result":'),
                    lambda raw:raw.replace(b'"sequence": 1,',b'"extra": 1,"sequence": 1,'),
                    lambda raw:b' '*16385]
        for change in changes:
            await self.asyncSetUp()
            self.storage_response=change
            before=self.business_state()
            with self.subTest(change=change),self.assertLogs('voice-bridge',level='INFO') as logged:
                result=await self.publish()
            self.assertFalse(result['stored'])
            self.assertTrue(self.session.presentation_disabled)
            self.assertFalse(self.session.presentation_nonce)
            self.assertEqual(self.business_state(),before)
            self.assertEqual(len(self.calls),1)
            self.assertFalse((await self.publish())['stored'])
            self.assertEqual(len(self.calls),1)
            self.assertNotIn('PRIVATE_NUMBER','\n'.join(logged.output))

    async def test_grant_and_store_share_one_two_second_publication_budget(self):
        s=self.session;s.presentation_nonce='';self.storage_delay=1.25
        before=self.business_state()
        async def attest():
            await asyncio.sleep(1.25)
            s.presentation_provider_user_id='voice-'+'b'*32
            s.presentation_nonce='a9'*32
        task=asyncio.create_task(attest());s.presentation_task=task
        started=time.monotonic();result=await self.publish();elapsed=time.monotonic()-started
        self.assertFalse(result['stored'],'Grant wait plus store must not receive two fresh budgets')
        self.assertLess(elapsed,2.3)
        self.assertTrue(s.presentation_disabled);self.assertFalse(s.presentation_nonce)
        self.assertIsNone(s.presentation_task);self.assertTrue(task.done())
        self.assertEqual(len(self.calls),1);self.assertFalse(self.storage_completed)
        self.assertTrue(self.storage_cancelled)
        self.assertGreater(self.calls[0]['timeout'].total,0)
        self.assertLess(self.calls[0]['timeout'].total,1)
        self.assertEqual(self.business_state(),before)
        self.assertFalse((await self.publish())['stored']);self.assertEqual(len(self.calls),1)

    async def test_lock_wait_is_inside_the_same_publication_budget(self):
        s=self.session;before=self.business_state()
        await s.presentation_lock.acquire()
        async def release():
            await asyncio.sleep(2.5)
            s.presentation_lock.release()
        holder=asyncio.create_task(release())
        try:
            started=time.monotonic();result=await self.publish();elapsed=time.monotonic()-started
            self.assertFalse(result['stored'],'Lock waiting must not extend optional publication lifetime')
            self.assertLess(elapsed,2.3);self.assertTrue(s.presentation_lock.locked())
            self.assertTrue(s.presentation_disabled);self.assertFalse(s.presentation_nonce)
            self.assertEqual(self.calls,[]);self.assertEqual(self.business_state(),before)
        finally:
            holder.cancel();await asyncio.gather(holder,return_exceptions=True)
            if s.presentation_lock.locked():s.presentation_lock.release()

    async def test_small_combined_delay_succeeds_with_remaining_transport_budget(self):
        s=self.session;s.presentation_nonce='';self.storage_delay=.01;before=self.business_state()
        async def attest():
            await asyncio.sleep(.01);s.presentation_provider_user_id='voice-'+'b'*32
            s.presentation_nonce='a9'*32
        task=asyncio.create_task(attest());s.presentation_task=task
        result=await self.publish();await task
        self.assertTrue(result['stored']);self.assertFalse(s.presentation_disabled)
        self.assertEqual(len(self.calls),1);self.assertTrue(self.storage_completed)
        self.assertGreater(self.calls[0]['timeout'].total,0)
        self.assertLess(self.calls[0]['timeout'].total,2)
        self.assertEqual(self.business_state(),before)

    async def test_cancellation_while_waiting_for_lock_retires_only_optional_state(self):
        s=self.session;before=self.business_state();await s.presentation_lock.acquire()
        publishing=asyncio.create_task(self.publish())
        try:
            await asyncio.sleep(.01);publishing.cancel()
            with self.assertRaises(asyncio.CancelledError):await publishing
            self.assertTrue(s.presentation_disabled);self.assertFalse(s.presentation_nonce)
            self.assertTrue(s.presentation_lock.locked());self.assertEqual(self.calls,[])
            self.assertEqual(self.business_state(),before)
        finally:s.presentation_lock.release()
