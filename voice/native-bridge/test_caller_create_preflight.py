"""Original-caller access checks with synthetic transports only; no live HTTP."""
import asyncio
from contextlib import ExitStack
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import aiohttp
from aiohttp import web

from assistant_settings import CallSettings
import native_bridge
import sdk_admission
from sdk_deployment import SDKDeploymentPolicy
import sdk_sessions
from test_assistant_settings import authorized_settings

try:
    import caller_create_preflight as preflight
except ModuleNotFoundError as error:
    if error.name != 'caller_create_preflight':
        raise
    preflight = None


INSTANCE_NAME = 'soprasteriaassvsdemo14'
INSTANCE = 'https://soprasteriaassvsdemo14.service-now.com'
SERVICE = '8aa131d793f787105c8132d47aba1095'
PROFILE = 'c623e20f93374354e7f2b9fa6aba1081'
AGENT = 'a6337ddf93f787105c8132d47aba1058'
AUTH_URL = INSTANCE + '/api/sn_voice_aia/ai_voice_agent/agents_authorized'
CREATE_URL = INSTANCE + '/api/sn_voice_aia/local_voice_caller/create'
AUTHORIZATION = 'bEaReR synthetic.opaque+original/token=='
MALFORMED_DENIAL = {'result': {'status': 'failure', 'detail': 'Local caller create unavailable'}}


def settings_response(service=SERVICE, profile=PROFILE, agent=AGENT):
    value = authorized_settings()
    value['result']['authorized_agents'] = [agent]
    value['result']['assistant_settings']['service_id'] = service
    value['result']['assistant_settings']['context_profile'] = profile
    return value


class Content:
    def __init__(self, raw):
        self.raw = raw
        self.offset = 0
        self.gate = None
        self.started = asyncio.Event()

    async def read(self, maximum):
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        part = self.raw[self.offset:self.offset + min(maximum, 17)]
        self.offset += len(part)
        return part


class Response:
    def __init__(self, status, body=None, *, raw=None, headers=None,
                 enter_delay=0, exit_error=False, exit_gate=None):
        self.status = status
        self.headers = {'Content-Type': 'application/json'} if headers is None else headers
        self.content = Content(json.dumps(body).encode() if raw is None else raw)
        self.enter_delay = enter_delay
        self.exit_error = exit_error
        self.exit_gate = exit_gate
        self.closed = False
        self.enter_started = asyncio.Event()

    async def __aenter__(self):
        self.enter_started.set()
        if self.enter_delay:
            await asyncio.sleep(self.enter_delay)
        return self

    async def json(self):
        return json.loads(self.content.raw.decode('utf-8'))

    async def __aexit__(self, *_):
        if self.exit_gate is not None:
            await self.exit_gate.wait()
        self.closed = True
        if self.exit_error:
            raise OSError('synthetic private transport detail')
        return False


class Client:
    def __init__(self, url, response, *, exit_error=False, exit_gate=None, post_error=None):
        self.url = url
        self.response = response
        self.exit_error = exit_error
        self.exit_gate = exit_gate
        self.post_error = post_error
        self.calls = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        if self.exit_gate is not None:
            await self.exit_gate.wait()
        self.closed = True
        if self.exit_error:
            raise OSError('synthetic private client detail')
        return False

    def post(self, url, **kwargs):
        if url != self.url:
            raise AssertionError('No other endpoint belongs to this test')
        self.calls.append((url, copy.deepcopy(kwargs)))
        if self.post_error:
            raise self.post_error
        return self.response


class Factory:
    def __init__(self, *clients):
        self.clients = list(clients)
        self.options = []

    def __call__(self, **kwargs):
        self.options.append(kwargs)
        if len(self.options) > len(self.clients):
            raise AssertionError('No additional client or retry is allowed')
        return self.clients[len(self.options) - 1]


def policy(instance=INSTANCE_NAME, service=SERVICE, agent=AGENT):
    return SDKDeploymentPolicy(instance, service, agent, 'https://voice.example.test')


async def admit(factory, *, deployment=None, settings_version=1):
    deployment = deployment or policy()
    return await sdk_admission.admit_sdk_session(
        [('Authorization', AUTHORIZATION), ('Content-Type', 'application/json')],
        b'{"agent_id":"agent_operator"}',
        query_string='instance_name=' + deployment.instance_name + '&receive_data=true',
        policy=deployment, assistant_settings_version=settings_version, http_factory=factory)


class AccessProbeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(preflight, 'The fixed-route caller access probe is missing')

    async def invoke(self, response=None, *, client=None, authorization=AUTHORIZATION):
        client = client or Client(CREATE_URL, response or Response(400, MALFORMED_DENIAL))
        factory = Factory(client)
        result = await preflight.require_caller_create_access(authorization, http_factory=factory)
        return result, client, factory

    async def denied(self, response=None, *, client=None, status=403, authorization=AUTHORIZATION):
        with self.assertRaises(preflight.CallerCreatePreflightDenied) as caught:
            await self.invoke(response, client=client, authorization=authorization)
        self.assertEqual(caught.exception.status, status)
        self.assertEqual(str(caught.exception), 'unauthorized' if status == 401 else 'forbidden')
        self.assertNotIn(AUTHORIZATION, repr(caught.exception))

    async def test_exact_early_malformed_denial_is_access_without_a_real_create(self):
        result, client, factory = await self.invoke()
        self.assertIsNone(result)
        self.assertTrue(client.closed)
        self.assertTrue(client.response.closed)
        self.assertEqual(len(client.calls), 1)
        url, options = client.calls[0]
        self.assertEqual(url, CREATE_URL)
        self.assertEqual(options['data'], b'{}')
        self.assertNotIn('json', options)
        self.assertEqual(options['headers'], {'Authorization': AUTHORIZATION,
            'Content-Type': 'application/json', 'Accept': 'application/json',
            'Accept-Encoding': 'identity'})
        self.assertFalse(options['allow_redirects'])
        self.assertEqual(type(factory.options[0]['cookie_jar']).__name__, 'DummyCookieJar')
        self.assertFalse(factory.options[0]['trust_env'])
        self.assertFalse(factory.options[0]['auto_decompress'])
        self.assertEqual(factory.options[0]['skip_auto_headers'], {'Accept-Encoding'})
        self.assertLessEqual(factory.options[0]['timeout'].total, 10)

    async def test_status_is_not_success_without_the_own_malformed_envelope(self):
        for body in ({}, MALFORMED_DENIAL['result'], {'result': {'status': 'failure'}},
                     {'result': {'status': 'failure', 'detail': 'other'}},
                     {'result': MALFORMED_DENIAL['result'], 'extra': True},
                     {'result': {**MALFORMED_DENIAL['result'], 'extra': True}},
                     {'result': []}, [], None):
            with self.subTest(body=body):
                await self.denied(Response(400, body))

    async def test_only_the_normal_401_and_403_statuses_preserve_their_denial(self):
        for status, expected in ((200, 403), (201, 403), (202, 403), (301, 403),
                                 (302, 403), (401, 401), (403, 403), (404, 403),
                                 (409, 403), (429, 403), (500, 403), (503, 403)):
            with self.subTest(status=status):
                response = Response(status, {'private': AUTHORIZATION})
                await self.denied(response, status=expected)
                self.assertEqual(response.content.offset, 0)

    async def test_duplicate_extra_nonfinite_invalid_utf8_and_oversize_json_are_denied(self):
        raw_values = [b'{"result":{"status":"failure","detail":"Local caller create unavailable",'
                      b'"detail":"Local caller create unavailable"}}',
                      b'{"result":{"status":"failure","detail":"Local caller create unavailable"},'
                      b'"result":{"status":"failure","detail":"Local caller create unavailable"}}',
                      b'{"result":NaN}', b'{"result":Infinity}', b'{"result":-Infinity}',
                      b'{not-json', b'\xff', b'\xef\xbb\xbf' + json.dumps(MALFORMED_DENIAL).encode(),
                      b' ' * 4097 + json.dumps(MALFORMED_DENIAL).encode()]
        for raw in raw_values:
            with self.subTest(length=len(raw)):
                await self.denied(Response(400, raw=raw))

    async def test_non_json_and_encoded_responses_cannot_supply_access(self):
        for headers in ({}, {'Content-Type': 'text/html'}, {'Content-Type': 'application/jsonp'},
                        {'Content-Type': 'application/json; charset=iso-8859-1'},
                        {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'},
                        {'Content-Type': 'application/json', 'Content-Encoding': 'deflate'}):
            with self.subTest(headers=headers):
                await self.denied(Response(400, MALFORMED_DENIAL, headers=headers))

    async def test_either_context_exit_failure_prevents_even_an_exact_400_admission(self):
        await self.denied(Response(400, MALFORMED_DENIAL, exit_error=True))
        await self.denied(client=Client(CREATE_URL, Response(400, MALFORMED_DENIAL), exit_error=True))
        await self.denied(Response(401, {}, exit_error=True))
        await self.denied(client=Client(CREATE_URL, Response(401, {}), exit_error=True))

    async def test_access_waits_for_both_contexts_to_close_normally(self):
        response_gate, client_gate = asyncio.Event(), asyncio.Event()
        response = Response(400, MALFORMED_DENIAL, exit_gate=response_gate)
        client = Client(CREATE_URL, response, exit_gate=client_gate)
        pending = asyncio.create_task(self.invoke(client=client))
        try:
            await asyncio.sleep(0)
            self.assertFalse(pending.done())
            response_gate.set()
            await asyncio.sleep(0)
            self.assertTrue(response.closed)
            self.assertFalse(client.closed)
            self.assertFalse(pending.done())
            client_gate.set()
            await asyncio.wait_for(pending, 1)
        finally:
            response_gate.set()
            client_gate.set()
            await asyncio.gather(pending, return_exceptions=True)

    async def test_missing_or_malformed_original_authority_never_dispatches(self):
        for value in ('', None, 'Basic fixture', ' Bearer fixture', 'Bearer two words',
                      'Bearer fixture\r\nprivate', 'Bearer ' + 'x' * 8186):
            with self.subTest(value_type=type(value).__name__):
                client = Client(CREATE_URL, Response(400, MALFORMED_DENIAL))
                await self.denied(client=client, status=401, authorization=value)
                self.assertEqual(client.calls, [])

    async def test_post_failure_is_denied_without_retry_or_private_error_text(self):
        client = Client(CREATE_URL, Response(400, MALFORMED_DENIAL),
                        post_error=OSError('private credential ' + AUTHORIZATION))
        await self.denied(client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(client.closed)

    async def test_own_deadline_covers_a_blocked_transport_close(self):
        client = Client(CREATE_URL, Response(400, MALFORMED_DENIAL), exit_gate=asyncio.Event())
        with patch.object(preflight, 'REQUEST_TIMEOUT_SECONDS', 0.03):
            await asyncio.wait_for(self.denied(client=client), 1)

    async def test_external_cancellation_propagates_and_does_not_replay(self):
        response = Response(400, MALFORMED_DENIAL, enter_delay=10)
        client = Client(CREATE_URL, response)
        pending = asyncio.create_task(self.invoke(client=client))
        await asyncio.sleep(0)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertTrue(client.closed)
        self.assertEqual(len(client.calls), 1)

    async def test_own_entry_or_body_timeout_also_bounds_the_following_exits(self):
        for phase, blocked_exit in (('entry', 'client'), ('body', 'response'), ('body', 'client')):
            with self.subTest(phase=phase, blocked_exit=blocked_exit):
                gate = asyncio.Event()
                response = Response(400, MALFORMED_DENIAL, enter_delay=10 if phase == 'entry' else 0,
                                    exit_gate=gate if blocked_exit == 'response' else None)
                if phase == 'body':
                    response.content.gate = asyncio.Event()
                client = Client(CREATE_URL, response, exit_gate=gate if blocked_exit == 'client' else None)
                with patch.object(preflight, 'REQUEST_TIMEOUT_SECONDS', 0.03):
                    pending = asyncio.create_task(self.invoke(client=client))
                    try:
                        finished, _ = await asyncio.wait({pending}, timeout=0.15)
                        self.assertIn(pending, finished, 'The consumed timer did not bound teardown')
                        with self.assertRaises(preflight.CallerCreatePreflightDenied):
                            await pending
                    finally:
                        gate.set()
                        if response.content.gate is not None:
                            response.content.gate.set()
                        await asyncio.wait_for(asyncio.gather(pending, return_exceptions=True), 1)


class EntryPreflightTests(unittest.IsolatedAsyncioTestCase):
    def wss(self, *, instance=INSTANCE, service=SERVICE, agent=AGENT):
        instance_name = instance.split('//', 1)[1].split('.', 1)[0]
        config = SimpleNamespace(instance_name=instance_name, instance_url=instance,
            voice_service_id=service, required_agent_id=agent,
            development_token='', auth_mode='servicenow')
        request = SimpleNamespace(query={'instance_name': instance_name,
            'voice_service_id': service, 'auth_token': 'synthetic.opaque+original/token=='},
            headers={'Origin': instance}, remote='127.0.0.1')
        return request, config

    async def test_sdk_metadata_success_does_not_admit_custom_create_401(self):
        metadata = Client(AUTH_URL, Response(200, settings_response()))
        denied = Client(CREATE_URL, Response(401, {'private': 'must not escape'}))
        with self.assertRaises(sdk_admission.AdmissionDenied) as caught:
            await admit(Factory(metadata, denied))
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(caught.exception.public_error, {'error': 'unauthorized'})
        self.assertNotIn(AUTHORIZATION, repr(caught.exception))

    async def test_exact_closed_400_preserves_the_verified_settings_context(self):
        metadata = Client(AUTH_URL, Response(200, settings_response()))
        probe = Client(CREATE_URL, Response(400, MALFORMED_DENIAL))
        context = await admit(Factory(metadata, probe))
        self.assertIsInstance(context.call_settings, CallSettings)
        self.assertEqual(context.call_settings.context_profile, PROFILE)
        self.assertNotIn(AUTHORIZATION, repr(context))
        self.assertEqual(len(probe.calls), 1)

    async def test_other_profiles_services_instances_agents_and_legacy_add_no_probe(self):
        cases = [(policy(), settings_response(profile='1' * 32), 1),
                 (policy(service='2' * 32), settings_response(service='2' * 32), 1),
                 (policy(instance='voice-other'), settings_response(), 1),
                 (policy(agent='3' * 32), settings_response(agent='3' * 32), 1),
                 (policy(), {'result': [AGENT]}, None)]
        for deployment, body, version in cases:
            with self.subTest(instance=deployment.instance_name, version=version):
                metadata = Client(deployment.authorization_url, Response(200, body))
                factory = Factory(metadata)
                result = await admit(factory, deployment=deployment, settings_version=version)
                self.assertEqual(result.assistant_id, deployment.assistant_id)
                self.assertEqual(len(factory.options), 1)

    async def test_sdk_one_deadline_covers_both_authority_and_access_checks(self):
        metadata = Client(AUTH_URL, Response(200, settings_response(), enter_delay=0.08))
        probe = Client(CREATE_URL, Response(400, MALFORMED_DENIAL, enter_delay=0.24))
        with patch.object(sdk_admission, 'AUTHORIZATION_TIMEOUT_SECONDS', 0.2):
            with self.assertRaises(sdk_admission.AdmissionDenied) as caught:
                await asyncio.wait_for(admit(Factory(metadata, probe)), 1)
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(len(probe.calls), 1)
        self.assertTrue(probe.closed)

    async def test_each_sdk_admission_rechecks_access_even_for_the_same_bearer(self):
        first_probe = Client(CREATE_URL, Response(400, MALFORMED_DENIAL))
        second_probe = Client(CREATE_URL, Response(401, {}))
        factory = Factory(Client(AUTH_URL, Response(200, settings_response())), first_probe,
                          Client(AUTH_URL, Response(200, settings_response())), second_probe)
        await admit(factory)
        with self.assertRaises(sdk_admission.AdmissionDenied) as caught:
            await admit(factory)
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual((len(first_probe.calls), len(second_probe.calls)), (1, 1))

    async def test_cancellation_during_sdk_access_does_not_become_an_admitted_context(self):
        metadata = Client(AUTH_URL, Response(200, settings_response()))
        probe = Client(CREATE_URL, Response(400, MALFORMED_DENIAL, enter_delay=10))
        factory = Factory(metadata, probe)
        pending = asyncio.create_task(admit(factory))
        await asyncio.sleep(0)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertTrue(probe.closed)
        self.assertEqual(len(probe.calls), 1)

    async def test_wss_closed_400_uses_an_own_client_and_preserves_fresh_settings(self):
        metadata = Client(AUTH_URL, Response(200, settings_response()))
        probe = Client(CREATE_URL, Response(400, MALFORMED_DENIAL))
        request, config = self.wss()
        factory = Factory(probe)
        with patch.object(aiohttp, 'ClientSession', factory):
            settings = await native_bridge.authorize(request, config, metadata, with_settings=True)
        self.assertIsInstance(settings, CallSettings)
        self.assertEqual(settings.context_profile, PROFILE)
        self.assertTrue(metadata.response.closed)
        self.assertTrue(probe.closed)
        self.assertEqual(len(metadata.calls), 1)
        self.assertEqual(len(probe.calls), 1)
        self.assertEqual(probe.calls[0][1]['headers']['Authorization'],
                         'Bearer synthetic.opaque+original/token==')
        self.assertEqual(type(factory.options[0]['cookie_jar']).__name__, 'DummyCookieJar')

    async def test_wss_unrelated_settings_and_legacy_authority_do_not_send_the_probe(self):
        cases = [(INSTANCE, SERVICE, AGENT, settings_response(profile='1' * 32), True),
                 ('https://voice-other.service-now.com', SERVICE, AGENT, settings_response(), True),
                 (INSTANCE, '2' * 32, AGENT, settings_response(service='2' * 32), True),
                 (INSTANCE, SERVICE, '3' * 32, settings_response(agent='3' * 32), True),
                 (INSTANCE, SERVICE, AGENT, {'result': [AGENT]}, False)]
        for instance, service, agent, body, with_settings in cases:
            with self.subTest(instance=instance, with_settings=with_settings):
                request, config = self.wss(instance=instance, service=service, agent=agent)
                metadata = Client(instance + '/api/sn_voice_aia/ai_voice_agent/agents_authorized',
                                  Response(200, body))
                factory = Factory()
                with patch.object(aiohttp, 'ClientSession', factory):
                    result = await native_bridge.authorize(request, config, metadata,
                                                           with_settings=with_settings)
                self.assertIsNot(result, False)
                self.assertEqual(factory.options, [])

    async def test_wss_one_deadline_covers_both_checks_instead_of_two_budgets(self):
        metadata = Client(AUTH_URL, Response(200, settings_response(), enter_delay=0.08))
        probe = Client(CREATE_URL, Response(400, MALFORMED_DENIAL, enter_delay=0.24))
        request, config = self.wss()
        with patch.object(aiohttp, 'ClientSession', Factory(probe)), \
                patch.object(native_bridge, 'AUTHORIZATION_TIMEOUT_SECONDS', 0.2):
            result = await asyncio.wait_for(native_bridge.authorize(
                request, config, metadata, with_settings=True), 1)
        self.assertIs(result, False)
        self.assertEqual(len(probe.calls), 1)
        self.assertTrue(probe.closed)

    async def test_cancellation_during_wss_access_propagates_without_admission(self):
        metadata = Client(AUTH_URL, Response(200, settings_response()))
        probe = Client(CREATE_URL, Response(400, MALFORMED_DENIAL, enter_delay=10))
        request, config = self.wss()
        with patch.object(aiohttp, 'ClientSession', Factory(probe)):
            pending = asyncio.create_task(native_bridge.authorize(
                request, config, metadata, with_settings=True))
            await asyncio.sleep(0)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
        self.assertTrue(probe.closed)
        self.assertEqual(len(probe.calls), 1)

    async def assert_budget_with_blocked_exit(self, entry, phase, blocked_exit, *, cancel=False):
        gate = asyncio.Event()
        response = Response(400, MALFORMED_DENIAL, enter_delay=10 if phase == 'entry' else 0,
                            exit_gate=gate if blocked_exit == 'response' else None)
        if phase == 'body':
            response.content.gate = asyncio.Event()
        probe = Client(CREATE_URL, response, exit_gate=gate if blocked_exit == 'client' else None)
        metadata = Client(AUTH_URL, Response(200, settings_response(), enter_delay=0.03))
        existing_tasks = asyncio.all_tasks()
        budget = 0.8 if cancel else 0.12
        with ExitStack() as patches:
            patches.enter_context(patch.object(preflight, 'REQUEST_TIMEOUT_SECONDS', 0.8))
            patches.enter_context(patch.object(sdk_admission, 'AUTHORIZATION_TIMEOUT_SECONDS', budget))
            patches.enter_context(patch.object(native_bridge, 'AUTHORIZATION_TIMEOUT_SECONDS', budget))
            if entry == 'sdk':
                operation = admit(Factory(metadata, probe))
            else:
                request, config = self.wss()
                patches.enter_context(patch.object(aiohttp, 'ClientSession', Factory(probe)))
                operation = native_bridge.authorize(request, config, metadata, with_settings=True)
            pending = asyncio.create_task(operation)
            try:
                entered = response.enter_started if phase == 'entry' else response.content.started
                await asyncio.wait_for(entered.wait(), 0.5)
                if cancel:
                    pending.cancel()
                finished, _ = await asyncio.wait({pending}, timeout=0.3)
                self.assertIn(pending, finished,
                              'A prior timeout/cancel left transport exit outside admission budget')
                if cancel:
                    with self.assertRaises(asyncio.CancelledError):
                        await pending
                elif entry == 'sdk':
                    with self.assertRaises(sdk_admission.AdmissionDenied) as caught:
                        await pending
                    self.assertEqual(caught.exception.status, 403)
                else:
                    self.assertIs(await pending, False)
                await asyncio.sleep(0)
                self.assertEqual(asyncio.all_tasks() - existing_tasks, set(),
                                 'A credential-bearing transport task was left behind')
                self.assertEqual(len(probe.calls), 1)
            finally:
                gate.set()
                if response.content.gate is not None:
                    response.content.gate.set()
                await asyncio.wait_for(asyncio.gather(pending, return_exceptions=True), 1.2)

    async def test_sdk_probe_timeout_cannot_leave_either_exit_outside_the_shared_deadline(self):
        for phase, blocked_exit in (('entry', 'client'), ('body', 'response'), ('body', 'client')):
            with self.subTest(phase=phase, blocked_exit=blocked_exit):
                await self.assert_budget_with_blocked_exit('sdk', phase, blocked_exit)

    async def test_wss_probe_timeout_cannot_leave_either_exit_outside_the_shared_deadline(self):
        for phase, blocked_exit in (('entry', 'client'), ('body', 'response'), ('body', 'client')):
            with self.subTest(phase=phase, blocked_exit=blocked_exit):
                await self.assert_budget_with_blocked_exit('wss', phase, blocked_exit)

    async def test_sdk_external_cancellation_propagates_with_bounded_exits_and_no_orphan(self):
        for phase, blocked_exit in (('entry', 'client'), ('body', 'response'), ('body', 'client')):
            with self.subTest(phase=phase, blocked_exit=blocked_exit):
                await self.assert_budget_with_blocked_exit('sdk', phase, blocked_exit, cancel=True)

    async def test_wss_external_cancellation_propagates_with_bounded_exits_and_no_orphan(self):
        for phase, blocked_exit in (('entry', 'client'), ('body', 'response'), ('body', 'client')):
            with self.subTest(phase=phase, blocked_exit=blocked_exit):
                await self.assert_budget_with_blocked_exit('wss', phase, blocked_exit, cancel=True)

    async def assert_metadata_unwind_is_bounded(self, entry, phase, blocked_exit, *, cancel=False):
        gate = asyncio.Event()
        response = Response(200, settings_response(), enter_delay=10 if phase == 'entry' else 0,
                            exit_gate=gate if blocked_exit == 'response' else None)
        if phase == 'body':
            response.content.gate = asyncio.Event()
        metadata = Client(AUTH_URL, response, exit_gate=gate if blocked_exit == 'client' else None)
        budget = 0.8 if cancel else 0.08
        existing_tasks = asyncio.all_tasks()
        with ExitStack() as patches:
            patches.enter_context(patch.object(sdk_admission, 'AUTHORIZATION_TIMEOUT_SECONDS', budget))
            patches.enter_context(patch.object(native_bridge, 'AUTHORIZATION_TIMEOUT_SECONDS', budget))
            if entry == 'sdk':
                factory = Factory(metadata)
                operation = admit(factory)
            else:
                factory = Factory()
                patches.enter_context(patch.object(aiohttp, 'ClientSession', factory))
                request, config = self.wss()
                operation = native_bridge.authorize(request, config, metadata, with_settings=True)
            pending = asyncio.create_task(operation)
            try:
                entered = response.enter_started if phase == 'entry' else response.content.started
                await asyncio.wait_for(entered.wait(), 0.5)
                if cancel:
                    pending.cancel()
                finished, _ = await asyncio.wait({pending}, timeout=0.3)
                self.assertIn(pending, finished, 'The initial metadata exit escaped the shared deadline')
                if cancel:
                    with self.assertRaises(asyncio.CancelledError):
                        await pending
                elif entry == 'sdk':
                    with self.assertRaises(sdk_admission.AdmissionDenied):
                        await pending
                else:
                    self.assertIs(await pending, False)
                self.assertEqual(len(factory.options), 1 if entry == 'sdk' else 0)
                await asyncio.sleep(0)
                self.assertEqual(asyncio.all_tasks() - existing_tasks, set())
            finally:
                gate.set()
                if response.content.gate is not None:
                    response.content.gate.set()
                await asyncio.wait_for(asyncio.gather(pending, return_exceptions=True), 1)

    async def test_initial_metadata_timeout_cannot_stall_admission_unwind_either(self):
        for entry, phase, blocked_exit in (('sdk', 'entry', 'client'), ('sdk', 'body', 'response'),
                                           ('sdk', 'body', 'client'), ('wss', 'body', 'response')):
            with self.subTest(entry=entry, phase=phase, blocked_exit=blocked_exit):
                await self.assert_metadata_unwind_is_bounded(entry, phase, blocked_exit)

    async def test_initial_metadata_cancellation_also_has_no_unbounded_exit_or_orphan(self):
        for entry, phase, blocked_exit in (('sdk', 'entry', 'client'), ('sdk', 'body', 'response'),
                                           ('sdk', 'body', 'client'), ('wss', 'body', 'response')):
            with self.subTest(entry=entry, phase=phase, blocked_exit=blocked_exit):
                await self.assert_metadata_unwind_is_bounded(entry, phase, blocked_exit, cancel=True)

    async def test_sdk_real_manager_rejects_before_any_allocation_or_readiness(self):
        metadata = Client(AUTH_URL, Response(200, settings_response()))
        denied = Client(CREATE_URL, Response(401, {}))
        factory = Factory(metadata, denied)
        active = set()
        effects = []

        def forbidden(name):
            effects.append(name)
            self.fail(name + ' ran before caller CREATE admission')

        async def readiness():
            forbidden('readiness/model/ASR')

        async def actual_admission(headers, body, *, query_string):
            return await sdk_admission.admit_sdk_session(headers, body,
                query_string=query_string, policy=deployment,
                assistant_settings_version=1, http_factory=factory)

        deployment = policy()
        config = SimpleNamespace(sdk_policy=deployment, instance_name=INSTANCE_NAME,
            instance_url=INSTANCE, voice_service_id=SERVICE, required_agent_id=AGENT,
            sdk_public_origin=deployment.public_origin, auth_mode='servicenow',
            development_token='', max_call_seconds=1800)
        manager = sdk_sessions.SDKSessionManager(config, active,
            lambda: forbidden('call/peer/audio'), actual_admission,
            context_call_factory=lambda *a, **k: forbidden('context call/peer/audio'),
            before_create=readiness,
            bind_call_authorization=lambda *a: forbidden('cookie/caller binding'))
        manager.managed_turn = SimpleNamespace(ice_servers=lambda *a: forbidden('TURN'))
        manager.relay_runtime = SimpleNamespace(ensure_running=lambda: forbidden('relay'))
        request = SimpleNamespace(raw_headers=[(b'Authorization', AUTHORIZATION.encode()),
            (b'Content-Type', b'application/json')],
            content=Content(b'{"agent_id":"agent_operator"}'), content_length=None,
            rel_url=SimpleNamespace(raw_query_string='instance_name=' + INSTANCE_NAME + '&receive_data=true'))
        with self.assertRaises(sdk_sessions._Rejected) as caught:
            await manager.create(request)
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual((active, manager.sessions, manager.creating, effects), (set(), {}, set(), []))

    async def test_wss_real_handler_rejects_before_capacity_model_turn_peer_or_audio(self):
        metadata = Client(AUTH_URL, Response(200, settings_response()))
        denied = Client(CREATE_URL, Response(401, {}))
        effects = []

        def forbidden(name):
            effects.append(name)
            self.fail(name + ' ran before caller CREATE admission')

        config = native_bridge.Config(instance_name=INSTANCE_NAME, voice_service_id=SERVICE,
            required_agent_id=AGENT, auth_mode='servicenow')
        config.private_managed_turn = SimpleNamespace(enabled=True)
        turn = SimpleNamespace(ice_servers=lambda *a: forbidden('TURN'))
        with ExitStack() as patches:
            patches.enter_context(patch.object(native_bridge, 'ManagedTurnBootstrap', return_value=turn))
            patches.enter_context(patch.object(aiohttp, 'ClientSession', Factory(denied)))
            patches.enter_context(patch.object(native_bridge, 'require_model_ready',
                                               side_effect=lambda *a: forbidden('model readiness')))
            patches.enter_context(patch.object(native_bridge, 'require_asr_ready',
                                               side_effect=lambda *a: forbidden('ASR readiness')))
            patches.enter_context(patch.object(native_bridge, 'NativeCall',
                                               side_effect=lambda *a, **k: forbidden('peer/call')))
            patches.enter_context(patch.object(native_bridge.web, 'WebSocketResponse',
                                               side_effect=lambda *a, **k: forbidden('WebSocket')))
            app = native_bridge.create_app(config,
                speech_factory=lambda *a: forbidden('speech/audio'),
                dialog_factory=lambda: forbidden('dialog'))
            app[native_bridge.HTTP_KEY] = metadata
            request = SimpleNamespace(query={'instance_name': INSTANCE_NAME,
                'voice_service_id': SERVICE, 'auth_token': 'synthetic.opaque+original/token=='},
                headers={'Origin': INSTANCE}, remote='127.0.0.1')
            handler = next(route.handler for route in app.router.routes()
                           if route.method == 'GET' and route.resource.canonical == '/webrtc/connect/agent_operator')
            with self.assertRaises(web.HTTPUnauthorized):
                await handler(request)
            health = next(route.handler for route in app.router.routes()
                          if route.method == 'GET' and route.resource.canonical == '/health')
            response = await health(SimpleNamespace(query={}))
            self.assertEqual(json.loads(response.body)['nativeSessions'], 0)
        self.assertEqual(effects, [])


if __name__ == '__main__':
    unittest.main()
