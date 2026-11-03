"""Synthetic transport only. Fixed diagnostic fields never carry private data."""
import asyncio
import ast
import hashlib
import inspect
import json
import logging
from pathlib import Path
import re
import time
import unittest
from unittest.mock import patch
from voice import caller_binding as authority
from voice import bridge
from voice.tests import test_local_caller_create as fixtures

PRIVATE = 'SYNTHETIC_PRIVATE_PROVIDER_TOKEN_NAME_EMAIL_URL_RESPONSE'


class CreateDiagnostics(unittest.IsolatedAsyncioTestCase):
    def factory(self, *, point='', status=200, headers=None, raw=None):
        self.calls, self.sessions, self.request_headers, self.closed = [], [], None, []
        self.entered = asyncio.Event()
        owner = self
        class Body:
            async def iter_chunked(self, count):
                if point == 'read': raise RuntimeError(PRIVATE)
                if point == 'wait':
                    owner.entered.set()
                    await asyncio.Event().wait()
                yield raw if raw is not None else json.dumps({'result':{'status':'success',
                    'created':fixtures.created(fixtures.REQUEST)}}).encode()
        class Response:
            def __init__(self):
                self.status = status
                self.headers = headers if headers is not None else {'Content-Type':'application/json'}
                self.content = Body()
            async def __aenter__(self):
                if point == 'response_enter': raise RuntimeError(PRIVATE)
                return self
            async def __aexit__(self, *args):
                owner.closed.append('response')
                if point == 'response_exit': raise RuntimeError(PRIVATE)
        class HTTP:
            async def __aenter__(self):
                if point == 'session_enter': raise RuntimeError(PRIVATE)
                return self
            async def __aexit__(self, *args):
                owner.closed.append('client')
                if point == 'session_exit': raise RuntimeError(PRIVATE)
            def post(self, url, **kwargs):
                owner.calls.append((url, kwargs))
                owner.request_headers = kwargs['headers']
                if point == 'post': raise RuntimeError(PRIVATE)
                return Response()
        def factory(**kwargs):
            owner.sessions.append(kwargs)
            if point == 'factory': raise RuntimeError(PRIVATE)
            return HTTP()
        return factory

    async def invoke(self, factory, **extra):
        options = dict(instance_url=fixtures.INSTANCE, api_path=fixtures.PATH,
                       provider_token=PRIVATE, authorization='Bearer '+PRIVATE,
                       request=dict(fixtures.REQUEST), timeout_seconds=1, http_factory=factory)
        options.update(extra)
        return await authority.create_native_caller_conversation(**options)

    def assert_diagnostic(self, capture, stage, status, state):
        self.assertEqual(len(capture.records), 1)
        record = capture.records[0]
        self.assertEqual(record.getMessage(),
            f'Caller CREATE failed stage={stage} http_status={status} dispatch_state={state}')
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.stack_info)
        self.assertNotIn(PRIVATE, repr(record.__dict__))
        for value in (fixtures.INSTANCE, fixtures.PATH, *fixtures.REQUEST.values()):
            if isinstance(value,str): self.assertNotIn(value, record.getMessage())

    async def failed(self, factory, stage, status, state, **extra):
        with self.assertLogs('voice-bridge', logging.WARNING) as capture:
            with self.assertRaisesRegex(ValueError, '^Native caller CREATE unavailable$'):
                await self.invoke(factory, **extra)
        self.assert_diagnostic(capture, stage, status, state)
        self.assertLessEqual(len(self.calls), 1)
        if self.request_headers is not None: self.assertEqual(self.request_headers, {})

    async def test_pre_dispatch_validation_never_opens_http(self):
        await self.failed(self.factory(), 'pre_dispatch_validation', 0, 'not_dispatched',
                          api_path='/'+PRIVATE)
        self.assertEqual(self.sessions, [])

    async def test_client_construction_and_entry_are_pre_dispatch(self):
        for point in ('factory','session_enter'):
            with self.subTest(point=point):
                await self.failed(self.factory(point=point), 'client_open', 0, 'not_dispatched')
                self.assertEqual(self.calls, [])

    async def test_post_and_response_entry_failure_are_uncertain_dispatch(self):
        for point in ('post','response_enter'):
            with self.subTest(point=point):
                await self.failed(self.factory(point=point), 'request_transport', 0, 'may_have_dispatched')

    async def test_non_success_status_is_numeric_only_and_does_not_read_error_body(self):
        for status in (301,401,409,429,500,503):
            with self.subTest(status=status):
                await self.failed(self.factory(point='read', status=status),
                                  'http_status', status, 'response_received')

    async def test_response_encoding_and_type_values_are_never_logged(self):
        await self.failed(self.factory(headers={'Content-Type':'application/json','Content-Encoding':PRIVATE}),
                          'response_encoding',200,'response_received')
        await self.failed(self.factory(headers={'Content-Type':PRIVATE}),
                          'response_type',200,'response_received')

    async def test_body_read_and_limit_stages_erase_headers(self):
        await self.failed(self.factory(point='read'), 'response_read',200,'response_received')
        await self.failed(self.factory(raw=(PRIVATE*5000).encode()),
                          'response_oversize',200,'response_received')

    async def test_json_utf8_duplicate_and_nonfinite_failures_are_one_fixed_stage(self):
        for raw in (PRIVATE.encode(), b'\xff', b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.subTest(raw=raw):
                await self.failed(self.factory(raw=raw),'response_json',200,'response_received')

    async def test_returned_tuple_rejection_has_no_body_or_identity(self):
        await self.failed(self.factory(raw=json.dumps({'result':{'status':PRIVATE}}).encode()),
                          'created_tuple_invalid',200,'response_received')

    async def test_transport_exit_failure_is_distinct_from_successful_json_parse(self):
        for point in ('response_exit','session_exit'):
            with self.subTest(point=point):
                await self.failed(self.factory(point=point),'transport_close',200,'response_received')

    async def test_deadline_remains_bounded_with_one_post_and_header_erasure(self):
        started = time.monotonic()
        await self.failed(self.factory(point='wait'),'response_read',200,'response_received',timeout_seconds=.01)
        self.assertLess(time.monotonic()-started, .5)
        self.assertEqual(len(self.calls),1)

    async def test_cancelled_error_propagates_with_fixed_stage_and_clears_headers(self):
        factory = self.factory(point='wait')
        with self.assertLogs('voice-bridge',logging.WARNING) as capture:
            task = asyncio.create_task(self.invoke(factory))
            await asyncio.wait_for(self.entered.wait(),1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assert_diagnostic(capture,'cancelled',200,'response_received')
        self.assertEqual(self.request_headers,{})
        self.assertEqual(len(self.calls),1)

    async def test_success_has_no_failure_log_and_preserves_wire_boundary(self):
        with self.assertNoLogs('voice-bridge',logging.WARNING):
            self.assertEqual(await self.invoke(self.factory()),fixtures.created(fixtures.REQUEST))
        self.assertEqual(len(self.calls),1)
        url, request = self.calls[0]
        self.assertEqual(url,fixtures.INSTANCE+fixtures.PATH)
        self.assertFalse(request['allow_redirects'])
        self.assertEqual(request['json'],fixtures.REQUEST)
        self.assertEqual(self.request_headers,{})
        self.assertFalse(self.sessions[0]['trust_env'])
        self.assertFalse(self.sessions[0]['auto_decompress'])
        self.assertLessEqual(self.sessions[0]['timeout'].total,1)

    def test_diagnostic_allowlists_and_status_validation_never_format_foreign_values(self):
        log = getattr(authority,'_log_create_failure',None)
        self.assertTrue(callable(log),'fixed diagnostic sanitizer is required')
        for status in (PRIVATE,True,False,99,600,None):
            with self.subTest(status=status),self.assertLogs('voice-bridge',logging.WARNING) as capture:
                log(PRIVATE,status,PRIVATE)
            self.assert_diagnostic(capture,'unexpected',0,'may_have_dispatched')

    async def test_owner_result_changed_is_fixed_without_network_and_retains_session(self):
        settings = bridge.Settings(user_id='fixture', instance_url=fixtures.INSTANCE,
            caller_create_api_path=fixtures.PATH, caller_binding_service_id=authority.CALLER_SERVICE_ID,
            caller_binding_agent_id=authority.CALLER_AGENT_ID)
        service = bridge.Bridge(settings,PRIVATE,PRIVATE,PRIVATE)
        session = bridge.Conversation(sid=fixtures.REQUEST['clientSessionId'],
            user_id='voice-'+fixtures.REQUEST['clientSessionId'],caller_user_id='a'*32,caller_email='old@example.test',
            caller_create_request_id=fixtures.REQUEST['requestId'],bootstrap_stage='creating',
            pending_action='CREATE_CONVERSATION')
        session.requests.append(fixtures.REQUEST['requestId'])
        service.sessions[session.sid] = session
        caller = authority.CallerBinding(session.caller_user_id,session.caller_email)
        source = (settings.instance_url,settings.caller_create_api_path,settings.caller_binding_service_id,
                  settings.caller_binding_agent_id,settings.inbound_id,service.bot_url)
        async def changed(*args,**kwargs):
            session.caller_email = PRIVATE
            return fixtures.created(fixtures.REQUEST)
        with patch.object(bridge,'create_native_caller_conversation',side_effect=changed), \
                self.assertLogs('voice-bridge',logging.WARNING) as capture:
            with self.assertRaisesRegex(ValueError,'^Native caller CREATE changed$'):
                await service.run_owned_create(session,dict(fixtures.REQUEST),caller,{},source,None,
                                                'Bearer '+PRIVATE,time.monotonic()+1)
        self.assert_diagnostic(capture,'owner_result_changed',200,'response_received')
        self.assertIs(service.sessions[session.sid],session)
        self.assertIsNone(session.conversation_binding)
        self.assertFalse(session.ended)

    def test_unchanged_callback_and_authority_functions_remain_equivalent_ast(self):
        # Portable, pinned function digests from reviewed commit 23ad4d4; no
        # ignored private snapshot or Git executable is needed to run this test.
        fixture = Path(__file__).resolve().parent/'fixtures/caller-create-cleanup-ast.json'
        baseline = fixture.read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(baseline.encode('utf-8')).hexdigest(),
                         'd9df0d4819b9d63237e919e9a63e17655589579aee12b2fbb3ab16157b5bfe59')
        reference = json.loads(baseline)
        self.assertEqual(reference['schema'], 1)
        self.assertEqual(reference['source_sha256_crlf'],
                         '31f4c67e316c6b098e582c0cbc50297b56a5be1361c6899ee54910a45991ff84')
        current = Path(bridge.__file__)
        # expire/end/drain_owned_cleanup are intentionally replaced by the
        # tested typed no-create protocol. Keep the original guards for the
        # unchanged callback, credential, success and unknown ownership paths.
        names = {'lifecycle','local_guard','start','reset','retire_caller_bootstrap',
                 'begin_owned_cleanup','owned_cleanup_identity',
                 'owned_cleanup_response','finish_owned_cleanup','callback','send_owned_create'}
        options = {'include_attributes': False}
        # Python 3.13 omits empty fields unless explicitly requested; retain the
        # reviewed Python 3.12 AST representation on either interpreter.
        if 'show_empty' in inspect.signature(ast.dump).parameters:
            options['show_empty'] = True
        def selected(path):
            return {node.name:hashlib.sha256(ast.dump(node,**options).encode('utf-8')).hexdigest()
                    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
                    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names}
        self.assertTrue(names <= set(reference['functions']))
        self.assertEqual({name: reference['functions'][name] for name in names}, selected(current))
