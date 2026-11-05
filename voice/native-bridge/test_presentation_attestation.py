"""Model-free private attestation lifetime, wire and owned CREATE checks."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice import bridge, caller_binding as caller, presentation_history as history
from voice.tests import test_local_caller_create as owned
from voice.tests import test_native_caller_authority as wire

PATH = '/api/global/scc_voice_context/updates'
PURPOSE = (caller.CALLER_INSTANCE_URL+PATH, 'attest_presentation_history_v1')
TOKEN = wire.TOKEN
NONCE = 'a9' * 32


def request():
    return dict(operation='attest_presentation_history_v1', requestId='1'*32,
        appInboundId='scc-local-voice', clientSessionId='2'*32, userId='voice-'+'2'*32,
        callerUserId='3'*32, conversationBinding=dict(source='servicenow_create_conversation',
            conversationId='4'*32, creationMessageId='5'*32, createRequestId='6'*32,
            interactionId='7'*32), nonceSha256=hashlib.sha256(NONCE.encode()).hexdigest(), maxAgeSeconds=1800)


def receipt(value):
    return dict(status='success', state='presentation_history_grant_attested',
        requestId=value['requestId'], conversationId=value['conversationBinding']['conversationId'],
        nonceSha256=value['nonceSha256'], issuedAtMs=12345,
        expiresAtMs=12345+value['maxAgeSeconds']*1000, attested=True,
        scope='presentation_metadata_only', businessAuthority=False)


class LeaseTests(unittest.IsolatedAsyncioTestCase):
    def delegate(self, ticket, owner):
        method = getattr(ticket, 'delegate_presentation', None)
        self.assertTrue(callable(method), 'Explicit one-use presentation sublease is required')
        return method(owner)

    async def test_exactly_one_sublease_survives_primary_take_with_original_deadline(self):
        owner=object();ticket=caller.CallerBootstrapCredential(TOKEN, seconds=1)
        self.addCleanup(ticket.clear)
        lease=self.delegate(ticket,owner);self.addCleanup(lease.clear)
        primary=ticket.take()
        self.assertFalse(ticket.available)
        self.assertTrue(lease.available)
        with self.assertRaises(ValueError):self.delegate(ticket,owner)
        value, remaining, deadline=lease.take(owner,PURPOSE)
        self.assertEqual(value,TOKEN);self.assertEqual(deadline,primary[2])
        self.assertLessEqual(remaining,primary[1]);self.assertFalse(lease.available)
        with self.assertRaises(ValueError):lease.take(owner,PURPOSE)
        self.assertNotIn(TOKEN,repr(lease));self.assertNotIn(TOKEN,repr(ticket))

    async def test_clear_expiry_cross_owner_wrong_purpose_and_duplicate_refused(self):
        for reason in ('clear','expiry','owner','purpose','duplicate'):
            with self.subTest(reason=reason):
                owner=object();ticket=caller.CallerBootstrapCredential(TOKEN,seconds=.02)
                self.addCleanup(ticket.clear);lease=self.delegate(ticket,owner);self.addCleanup(lease.clear)
                if reason=='clear':lease.clear()
                if reason=='expiry':await asyncio.sleep(.04)
                if reason=='duplicate':
                    with self.assertRaises(ValueError):self.delegate(ticket,owner)
                    lease.take(owner,PURPOSE)
                with self.assertRaises(ValueError):
                    lease.take(object() if reason=='owner' else owner, (caller.CALLER_INSTANCE_URL+'/elsewhere', PURPOSE[1]) if reason=='purpose' else PURPOSE)
                self.assertFalse(lease.available)
        for take in (False,True):
            ticket=caller.CallerBootstrapCredential(TOKEN,seconds=1)
            if take:ticket.take()
            else:ticket.clear()
            with self.assertRaises(ValueError):self.delegate(ticket,object())

    async def test_purpose_binds_exact_url_and_operation_and_is_destructive_on_mismatch(self):
        self.assertEqual(caller.PRESENTATION_GRANT_PATH,PATH)
        self.assertEqual(getattr(caller,'PRESENTATION_GRANT_PURPOSE',None),PURPOSE)
        for purpose in (PATH, PURPOSE[0], (PURPOSE[0],'presentation_history_store'),
                (caller.CALLER_INSTANCE_URL+'/api/global/scc_voice_context/presentation-grants',PURPOSE[1]),
                ('https://other.invalid'+PATH,PURPOSE[1]), (PURPOSE[0]+'#'+PURPOSE[1],PURPOSE[1])):
            with self.subTest(purpose=purpose):
                owner=object();ticket=caller.CallerBootstrapCredential(TOKEN,seconds=1)
                self.addCleanup(ticket.clear);lease=self.delegate(ticket,owner);self.addCleanup(lease.clear)
                with self.assertRaises(ValueError):lease.take(owner,purpose)
                self.assertFalse(lease.available)
                with self.assertRaises(ValueError):lease.take(owner,PURPOSE)


class GrantWireTests(unittest.IsolatedAsyncioTestCase):
    factory=wire.NativeAuthorityWireTests.factory

    async def invoke(self, value=None, *, options=None, body=None, **kwargs):
        self.sent=[]
        method=getattr(history,'issue_presentation_grant',None)
        self.assertTrue(callable(method), 'Fixed authenticated attestation transport is required')
        value=request() if value is None else value
        factory=self.factory(raw=json.dumps(body if body is not None else {'result':receipt(value)}).encode(),**(options or {}))
        def copied(**options):
            http=factory(**options);post=http.post
            def send(url,**options):
                options['headers']=dict(options['headers']);return post(url,**options)
            http.post=send;return http
        return await method(caller.CALLER_INSTANCE_URL,'provider-secret',TOKEN,value,http_factory=copied,**kwargs)

    async def test_exact_contract_fixed_origin_new_cookie_free_session_and_skewed_native_clock(self):
        self.assertEqual(await self.invoke(timeout_seconds=.5),receipt(request()))
        self.assertEqual(len(self.sent),1);url,options=self.sent[0]
        self.assertEqual(url,caller.CALLER_INSTANCE_URL+PATH)
        self.assertNotIn('#',url)
        self.assertEqual(options['json'],request());self.assertNotIn(NONCE,json.dumps(options['json']))
        self.assertEqual(options['headers']['Authorization'],TOKEN)
        self.assertEqual(options['headers']['token'],'provider-secret')
        self.assertFalse(options['allow_redirects']);self.assertFalse(self.created[0]['trust_env'])
        self.assertIs(options['ssl'],True)
        self.assertEqual(type(self.created[0]['cookie_jar']).__name__,'DummyCookieJar')
        self.assertLessEqual(self.created[0]['timeout'].total,2)

    async def test_only_exact_positive_receipt_is_accepted(self):
        for key,value in [('attested',1),('businessAuthority',0),('scope','business'),
                ('requestId','f'*32),('nonceSha256','f'*64),('expiresAtMs',1),
                ('issuedAtMs',True),('conversationId','f'*32),('extra','denied')]:
            with self.subTest(key=key):
                bad=dict(receipt(request()),**{key:value})
                with self.assertRaisesRegex(ValueError,'^Presentation history unavailable$'):
                    await self.invoke(body={'result':bad})
                self.assertEqual(len(self.sent),1)
        for body in ({'result':receipt(request()),'status':'failure'},receipt(request())):
            with self.assertRaises(ValueError):await self.invoke(body=body)

    async def test_native_timestamps_must_be_positive_javascript_safe_integers(self):
        for issued in (0,-1,9007199254740992,9007199254740991):
            bad=dict(receipt(request()),issuedAtMs=issued,expiresAtMs=issued+1800000)
            with self.subTest(issued=issued),self.assertRaises(ValueError):
                await self.invoke(body={'result':bad})

    async def test_bad_body_http_encoding_transport_and_timeout_fail_without_retry_or_detail(self):
        for options in ({'status':401},{'status':403},{'status':302},
                {'headers':{'Content-Type':'text/plain'}},
                {'headers':{'Content-Type':'application/json','Content-Encoding':'gzip'}}, {'error':True}):
            with self.subTest(options=options),self.assertRaisesRegex(ValueError,'^Presentation history unavailable$'):
                await self.invoke(options=options)
            self.assertEqual(len(self.sent),1)
        for change in ({'grantNonce':NONCE},{'maxAgeSeconds':True},{'maxAgeSeconds':59},
                {'maxAgeSeconds':3601},{'callerUserId':'guest'},
                {'operation':'presentation_history_store'},{'operation':'attest_presentation_history_v1#updates'}):
            with self.subTest(change=change),self.assertRaises(ValueError):await self.invoke(dict(request(),**change))
            self.assertEqual(self.sent,[])
        with self.assertRaises(ValueError):await self.invoke(timeout_seconds=2.01)
        self.assertEqual(self.sent,[])

    async def test_wrong_origin_oversize_duplicate_json_and_nonfinite_response_are_refused(self):
        for origin in (caller.CALLER_INSTANCE_URL+':443','https://other.invalid',caller.CALLER_INSTANCE_URL+'/extra'):
            factory=self.factory()
            with self.subTest(origin=origin),self.assertRaises(ValueError):
                await history.issue_presentation_grant(origin,'provider-secret',TOKEN,request(),http_factory=factory)
            self.assertEqual(self.sent,[]);self.assertEqual(self.created,[])
        for raw in (b' '*4097, b'{"result":{},"result":{}}', b'{"result":NaN}'):
            with self.subTest(raw=raw[:30]),self.assertRaisesRegex(ValueError,'^Presentation history unavailable$'):
                await history.issue_presentation_grant(caller.CALLER_INSTANCE_URL,'provider-secret',TOKEN,
                    request(),http_factory=self.factory(raw=raw))
            self.assertEqual(len(self.sent),1)

    async def test_transport_timeout_and_cancellation_clear_headers_without_retry(self):
        entered=asyncio.Event();sent=[]
        class NeverBody:
            async def iter_chunked(self,count):
                entered.set();await asyncio.Event().wait();yield b''
        class HTTP:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def post(self,url,**kwargs):
                sent.append(kwargs);reply=wire.Response(b'');reply.content=NeverBody();return reply
        for cancel in (False,True):
            with self.subTest(cancel=cancel):
                entered.clear();sent.clear()
                task=asyncio.create_task(history.issue_presentation_grant(caller.CALLER_INSTANCE_URL,
                    'provider-secret',TOKEN,request(),timeout_seconds=.02,http_factory=lambda **kwargs:HTTP()))
                await asyncio.wait_for(entered.wait(),1)
                if cancel:task.cancel()
                with self.assertRaises(asyncio.CancelledError if cancel else ValueError):await task
                self.assertEqual(len(sent),1);self.assertEqual(sent[0]['headers'],{})


class GrantBridgeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=owned.OwnedCreateBridgeTests.asyncSetUp
    start=owned.OwnedCreateBridgeTests.start
    settle=owned.OwnedCreateBridgeTests.settle

    async def ready(self, *, enabled=True, issuer=None):
        self.bridge.settings.presentation_history_enabled=enabled
        self.issuer=AsyncMock(side_effect=issuer or (lambda *args,**kwargs:receipt(args[3])))
        self.enterContext(patch('voice.bridge.issue_presentation_grant',self.issuer,create=True))
        self.enterContext(patch('voice.bridge.secrets.token_hex',return_value=NONCE))
        self.assertEqual((await self.start()).status,202)
        await self.settle()
        return next(iter(self.bridge.sessions.values()))

    async def finish_attestation(self, session):
        task=getattr(session,'presentation_task',None)
        if task:await asyncio.wait_for(asyncio.shield(task),1)

    async def test_disabled_has_no_lease_nonce_task_or_request(self):
        s=await self.ready(enabled=False)
        self.issuer.assert_not_awaited()
        for name in ('presentation_lease','presentation_task','presentation_nonce'):
            self.assertFalse(getattr(s,name,None))
        self.assertEqual([x.get('action') for x in self.sent],['START_CREATED_CONVERSATION'])

    async def test_private_task_does_not_delay_original_create_refresh_start_or_input(self):
        entered,release=asyncio.Event(),asyncio.Event()
        async def issue(*args,**kwargs):entered.set();await release.wait();return receipt(args[3])
        s=await self.ready(issuer=issue)
        self.assertTrue(entered.is_set(),'Owned CREATE must schedule separate metadata task')
        self.assertEqual([x.get('action') for x in self.sent],['START_CREATED_CONVERSATION'])
        self.refresher.assert_awaited_once();self.assertIsNone(s.caller_bootstrap)
        self.assertIsNone(s.caller_authorization_task)
        self.assertNotIn(TOKEN,repr(s));self.assertNotIn(NONCE,repr(s))
        release.set();await self.finish_attestation(s)
        self.assertEqual(getattr(s,'presentation_nonce',None),NONCE)
        self.assertIsNone(s.presentation_lease);self.assertIsNone(s.presentation_task)
        args=self.issuer.await_args.args
        self.assertEqual(args[2],TOKEN);self.assertEqual(args[3]['conversationBinding'],s.conversation_binding.snapshot())
        self.assertEqual(set(self.creator.await_args.args[4]),{'version','requestId','clientSessionId','clientMessageId'})
        self.assertNotIn(NONCE,json.dumps(s.conversation_binding.snapshot()))
        result=await self.ui.get('/api/events?wait=0',headers=self.headers)
        self.assertNotIn(NONCE,await result.text());self.assertNotIn(TOKEN,await result.text())
        self.assertNotIn(NONCE,json.dumps(s.voice_context));self.assertFalse(s.failed)

    async def test_failure_disables_only_optional_lane(self):
        async def issue(*args,**kwargs):raise ValueError('private details '+TOKEN)
        s=await self.ready(issuer=issue);await self.finish_attestation(s)
        self.assertFalse(getattr(s,'presentation_nonce',None));self.assertTrue(s.presentation_disabled)
        self.assertIsNone(s.presentation_lease);self.assertIsNone(s.presentation_task)
        self.assertFalse(s.failed);self.assertFalse(s.ended)

    async def test_malformed_receipt_never_enables_nonce(self):
        async def issue(*args,**kwargs):return dict(receipt(args[3]),businessAuthority=True)
        s=await self.ready(issuer=issue);await self.finish_attestation(s)
        self.assertFalse(getattr(s,'presentation_nonce',None));self.assertTrue(s.presentation_disabled)

    async def test_end_cancellation_erases_lease_nonce_and_cannot_adopt_late_receipt(self):
        entered=asyncio.Event()
        async def issue(*args,**kwargs):
            entered.set()
            try:await asyncio.Event().wait()
            except asyncio.CancelledError:return receipt(args[3])
        s=await self.ready(issuer=issue);self.assertTrue(entered.is_set())
        task=s.presentation_task
        response=await self.ui.post('/api/end',json={},headers=self.headers)
        self.assertEqual(response.status,202)
        await asyncio.gather(task,return_exceptions=True)
        self.assertFalse(s.presentation_nonce);self.assertIsNone(s.presentation_lease)
        self.assertIsNone(s.presentation_task)

    async def test_owner_or_source_drift_rejects_receipt_without_business_failure(self):
        async def issue(*args,**kwargs):
            self.bridge.settings.instance_url='https://changed.invalid'
            return receipt(args[3])
        s=await self.ready(issuer=issue);await self.finish_attestation(s)
        self.assertFalse(getattr(s,'presentation_nonce',None));self.assertTrue(s.presentation_disabled)

    async def test_original_deadline_timeout_erases_private_task(self):
        entered=asyncio.Event()
        async def issue(*args,**kwargs):entered.set();await asyncio.Event().wait()
        with patch('voice.bridge.CALLER_BOOTSTRAP_SECONDS',.15):s=await self.ready(issuer=issue)
        self.assertTrue(entered.is_set())
        await self.finish_attestation(s)
        self.assertFalse(s.presentation_nonce);self.assertIsNone(s.presentation_lease)
        self.assertIsNone(s.presentation_task);self.assertTrue(s.presentation_disabled)
        self.assertFalse(s.failed)

    async def test_expiry_during_private_nonce_creation_never_dispatches_attestation(self):
        self.bridge.settings.presentation_history_enabled=True
        issuer=AsyncMock(side_effect=lambda *args,**kwargs:receipt(args[3]))
        self.enterContext(patch('voice.bridge.issue_presentation_grant',issuer))
        def generate(size):time.sleep(.16);return NONCE
        self.enterContext(patch('voice.bridge.secrets.token_hex',side_effect=generate))
        with patch('voice.bridge.CALLER_BOOTSTRAP_SECONDS',.12):await self.start()
        await self.settle()
        s=next(iter(self.bridge.sessions.values()));await self.finish_attestation(s)
        issuer.assert_not_awaited()
        self.assertFalse(s.presentation_nonce);self.assertIsNone(s.presentation_lease)

    async def test_secure_control_failure_immediately_revokes_completed_grant(self):
        s=await self.ready();await self.finish_attestation(s)
        self.assertEqual(s.presentation_nonce,NONCE)
        self.bridge.consume(s,{'body':[{'uiType':'InputText','maskType':'SECURE'}]})
        self.assertTrue(s.failed);self.assertFalse(s.presentation_nonce)
        self.assertIsNone(s.presentation_timer)

    async def test_turn_timeout_immediately_revokes_completed_grant(self):
        s=await self.ready();await self.finish_attestation(s)
        s.busy=True;s.pending_since=time.monotonic()-self.bridge.settings.turn_seconds-1
        self.bridge.expire()
        self.assertTrue(s.failed);self.assertFalse(s.presentation_nonce)
        self.assertIsNone(s.presentation_timer)

    async def test_shutdown_cancels_pending_task_and_erases_all_private_state(self):
        async def issue(*args,**kwargs):await asyncio.Event().wait()
        s=await self.ready(issuer=issue);task=s.presentation_task
        await self.ui.close()
        self.assertTrue(task.done());self.assertFalse(s.presentation_nonce)
        self.assertIsNone(s.presentation_lease);self.assertIsNone(s.presentation_task)
        self.assertEqual(self.bridge.presentation_tasks,set())

    async def test_cancelled_optional_task_and_active_expiry_cannot_recreate_grant(self):
        async def issue(*args,**kwargs):await asyncio.Event().wait()
        s=await self.ready(issuer=issue);task=s.presentation_task;task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        self.assertTrue(s.presentation_disabled);self.assertFalse(s.presentation_nonce)
        self.assertIsNone(s.presentation_lease);self.assertIsNone(s.presentation_task)
        self.bridge.queue_presentation_attestation(s,self.bridge.owned_cleanup_identity(s))
        self.assertIsNone(s.presentation_task);self.issuer.assert_awaited_once()

    async def test_invalid_create_retires_delegation_without_issuing_or_changing_create_body(self):
        self.bridge.settings.presentation_history_enabled=True
        issuer=AsyncMock();self.enterContext(patch('voice.bridge.issue_presentation_grant',issuer))
        self.creator.side_effect=ValueError('unavailable')
        self.assertGreaterEqual((await self.start()).status,400)
        s=next(iter(self.bridge.sessions.values()))
        self.assertIsNone(s.presentation_lease);self.assertIsNone(s.presentation_task)
        self.assertFalse(s.presentation_nonce);issuer.assert_not_awaited()
        self.refresher.assert_not_awaited()

    async def test_flag_disabled_during_create_revokes_unused_delegation(self):
        self.bridge.settings.presentation_history_enabled=True
        issuer=AsyncMock();self.enterContext(patch('voice.bridge.issue_presentation_grant',issuer))
        async def create(*args,**kwargs):
            self.bridge.settings.presentation_history_enabled=False
            return owned.created(args[4])
        self.creator.side_effect=create
        await self.start();await self.settle()
        s=next(iter(self.bridge.sessions.values()))
        self.assertIsNone(s.presentation_lease);self.assertIsNone(s.presentation_task)
        issuer.assert_not_awaited();self.refresher.assert_awaited_once()

    async def test_failure_details_and_nonce_never_enter_logs_or_public_projection(self):
        async def issue(*args,**kwargs):raise RuntimeError('sensitive '+TOKEN+' '+NONCE)
        with patch.object(bridge.LOG,'warning') as warning,patch.object(bridge.LOG,'info') as info:
            s=await self.ready(issuer=issue);await self.finish_attestation(s)
        visible=repr(warning.call_args_list)+repr(info.call_args_list)+repr(s)+repr(list(s.events))
        self.assertNotIn(TOKEN,visible);self.assertNotIn(NONCE,visible)

    async def test_ending_create_result_is_cleanup_only_and_never_attests(self):
        self.bridge.settings.presentation_history_enabled=True
        issuer=AsyncMock();self.enterContext(patch('voice.bridge.issue_presentation_grant',issuer))
        async def create(*args,**kwargs):
            next(iter(self.bridge.sessions.values())).ending=True
            return owned.created(args[4])
        self.creator.side_effect=create
        await self.start();await self.settle()
        s=next(iter(self.bridge.sessions.values()))
        self.assertIsNotNone(s.conversation_binding)
        self.assertIsNone(s.presentation_lease);issuer.assert_not_awaited()
        self.refresher.assert_not_awaited()


if __name__=='__main__':unittest.main()
