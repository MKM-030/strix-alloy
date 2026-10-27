"""Offline assistant-settings admission and SDK allocation integration tests."""
import asyncio
import dataclasses
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from assistant_settings import CallSettings
import sdk_admission as admission
import sdk_sessions as sessions
from sdk_deployment import SDKDeploymentPolicy
from test_sdk_admission import ASSISTANT, VOICE_AGENT, FakeHttp, FakeResponse
from test_sdk_sessions import FakeCall

INSTANCE = 'soprasteriaassvsdemo14'
ORIGIN = 'https://' + INSTANCE + '.service-now.com'
PROFILE = '11111111111111111111111111111111'
QUERY = 'instance_name=' + INSTANCE + '&receive_data=true'
TOKEN = 'fixture-assistant-settings-oauth'


def authorized_projection():
    settings = {
        'version': 1, 'service_id': ASSISTANT, 'context_profile': PROFILE,
        'language': 'en',
        'language_selection': {
            'enabled': True, 'dtmf_enabled': False, 'mode': 'voice',
            'languages': [
                {'code': 'en', 'display_name': 'English',
                 'language_selection_prompt': '', 'dtmf_language_selection_prompt': '',
                 'trigger_phrases': ['English please'], 'secondary_language_prompt': None},
                {'code': 'de', 'display_name': 'German',
                 'language_selection_prompt': '', 'dtmf_language_selection_prompt': '',
                 'trigger_phrases': ['Bitte Deutsch'], 'secondary_language_prompt': 'Deutsch'}]},
        'tts': {'voice_profile': '', 'voices': {}},
        'key_terms': {'en': [], 'de': []},
        'prompt': {'systemMessage': 'Policy', 'introduction': 'Hi'},
        'vad': {'confidence': .7, 'min_volume': .5, 'start_secs': .1, 'stop_secs': .2},
        'behavior': {'max_call_duration_in_minutes': '5'}}
    return {'result': {'authorized_agents': [VOICE_AGENT], 'assistant_settings': settings}}


class SettingsAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.headers = [('Authorization', 'Bearer ' + TOKEN),
                        ('Content-Type', 'application/json')]
        self.body = b'{"agent_id":"agent_operator"}'
        self.policy = SDKDeploymentPolicy(INSTANCE, ASSISTANT, VOICE_AGENT,
                                          'https://voice.example.com')

    async def admit(self, payload=None, **options):
        http = FakeHttp(FakeResponse(payload=authorized_projection() if payload is None else payload))
        context = await admission.admit_sdk_session(
            options.pop('headers', self.headers), options.pop('body', self.body),
            query_string=options.pop('query_string', QUERY), policy=self.policy,
            http_factory=http.factory, assistant_settings_version=1, **options)
        return context, http

    async def test_versioned_authorization_requests_projection_and_retains_validated_settings(self):
        context, http = await self.admit()
        self.assertEqual(http.calls[0][1]['json'],
                         {'serviceId': ASSISTANT, 'assistantSettingsVersion': 1})
        self.assertEqual(http.calls[0][1]['headers']['Authorization'], 'Bearer ' + TOKEN)
        self.assertIsInstance(context, admission.VerifiedContext)
        self.assertIsNotNone(context.call_settings)
        self.assertNotIn(TOKEN, repr(context))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            context.call_settings = None

    async def test_each_admission_has_an_independent_settings_snapshot(self):
        first, _ = await self.admit()
        second, _ = await self.admit()
        self.assertIsNot(first.call_settings, second.call_settings)

    async def test_versioned_authorization_rejects_legacy_missing_and_wrong_bound_settings(self):
        wrong = authorized_projection()
        wrong['result']['assistant_settings']['service_id'] = '0' * 32
        no_agent = authorized_projection()
        no_agent['result']['authorized_agents'] = []
        missing = authorized_projection()
        del missing['result']['assistant_settings']
        for payload in ({'result': [VOICE_AGENT]}, missing, wrong, no_agent):
            with self.subTest(payload=payload):
                with self.assertRaises(admission.AdmissionDenied) as caught:
                    await self.admit(payload)
                self.assertEqual(caught.exception.status, 403)
                self.assertEqual(caught.exception.public_error, {'error': 'forbidden'})

    async def test_versioned_authorization_keeps_request_guards_before_http(self):
        cases = [({'headers': self.headers + [('Cookie', 'session=confused')]}, 401),
                 ({'headers': self.headers + [('Authorization', 'Bearer duplicate')]}, 401),
                 ({'headers': self.headers + [('Origin', 'https://evil.example')]}, 403),
                 ({'query_string': QUERY + '&auth_token=private'}, 400),
                 ({'body': b'{"agent_id":"different"}'}, 403)]
        for options, status in cases:
            http = FakeHttp(FakeResponse(payload=authorized_projection()))
            with self.subTest(options=options):
                with self.assertRaises(admission.AdmissionDenied) as caught:
                    await admission.admit_sdk_session(
                        options.get('headers', self.headers), options.get('body', self.body),
                        query_string=options.get('query_string', QUERY), policy=self.policy,
                        http_factory=http.factory, assistant_settings_version=1)
                self.assertEqual(caught.exception.status, status)
                self.assertEqual(http.calls, [])

    async def test_unsupported_projection_versions_fail_before_platform(self):
        for version in (True, 0, 2, '1'):
            http = FakeHttp()
            with self.subTest(version=version):
                with self.assertRaises(admission.AdmissionDenied) as caught:
                    await admission.admit_sdk_session(self.headers, self.body,
                        query_string=QUERY, policy=self.policy, http_factory=http.factory,
                        assistant_settings_version=version)
                self.assertEqual(caught.exception.status, 403)
                self.assertEqual(http.calls, [])

    async def test_projection_response_still_has_strict_size_and_json_bounds(self):
        for raw in (b'x' * 32769, b'{"result":null,"result":null}', b'{"result":NaN}'):
            http = FakeHttp(FakeResponse(raw=raw))
            with self.subTest(raw_length=len(raw)):
                with self.assertRaises(admission.AdmissionDenied) as caught:
                    await admission.admit_sdk_session(self.headers, self.body,
                        query_string=QUERY, policy=self.policy, http_factory=http.factory,
                        assistant_settings_version=1)
                self.assertEqual(caught.exception.status, 403)


class SettingsSessionFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.active, self.calls, self.factory_contexts = set(), [], []
        self.settings = object()
        self.context = SimpleNamespace(instance_url=ORIGIN, assistant_id=ASSISTANT,
            voice_agent_id=VOICE_AGENT, sdk_agent_id='agent_operator',
            receive_data=True, call_settings=self.settings)
        self.config = SimpleNamespace(instance_name=INSTANCE, instance_url=ORIGIN,
            voice_service_id=ASSISTANT, required_agent_id=VOICE_AGENT,
            auth_mode='servicenow', development_token='', max_call_seconds=1800)
        self.config.sdk_policy = SDKDeploymentPolicy(INSTANCE, ASSISTANT, VOICE_AGENT,
                                                     'https://voice.example.com')
        self.call_duration = 300
        async def admit(headers, body, *, query_string):
            return self.context
        def legacy_factory():
            self.fail('Context factory must own configured call allocation')
        def context_factory(context):
            self.factory_contexts.append(context)
            call = FakeCall()
            call.config = SimpleNamespace(max_call_seconds=self.call_duration)
            self.calls.append(call)
            return call
        self.app = web.Application()
        self.manager = sessions.register_sdk_routes(self.app, self.config, self.active,
            legacy_factory, admit, context_call_factory=context_factory)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        if hasattr(self, 'client'):
            await self.client.close()

    async def create(self):
        return await self.client.post(sessions.BASE + '?' + QUERY,
            headers={'Authorization': 'Bearer ' + TOKEN}, json={'agent_id': 'agent_operator'})

    async def test_verified_context_reaches_factory_without_exposing_settings_on_wire(self):
        response = await self.create()
        self.assertEqual(response.status, 200, await response.text())
        payload = await response.json()
        self.assertEqual(self.factory_contexts, [self.context])
        self.assertIs(self.factory_contexts[0].call_settings, self.settings)
        self.assertEqual(set(payload),
                         {'session_id', 'agent_id', 'created_at', 'iceServers', 'endpoint_url'})
        self.assertIn(self.calls[0], self.active)

    async def test_unsupported_language_selection_returns_explicit_501_before_allocation(self):
        self.context.call_settings = SimpleNamespace(unsupported_language_selection=True)
        response = await self.create()
        self.assertEqual(response.status,501)
        self.assertEqual(await response.json(),{'error':'assistant_settings_unsupported'})
        self.assertEqual(self.factory_contexts,[])
        self.assertEqual(self.calls,[])
        self.assertEqual(self.manager.sessions,{})
        self.assertFalse(self.active)

    async def test_multilanguage_dtmf_projection_is_rejected_before_allocation(self):
        payload = authorized_projection()
        payload['result']['assistant_settings']['language_selection']['mode'] = ' DTMF '
        self.context.call_settings = CallSettings.from_authorized_response(payload,ASSISTANT,VOICE_AGENT)
        response = await self.create()
        self.assertEqual(response.status,501)
        self.assertEqual(await response.json(),{'error':'assistant_settings_unsupported'})
        self.assertEqual(self.factory_contexts,[])
        self.assertFalse(self.active)

    async def test_single_language_dtmf_projection_still_allocates(self):
        payload = authorized_projection()
        projection = payload['result']['assistant_settings']
        projection['language_selection']['mode'] = 'dtmf'
        projection['language_selection']['languages'] = projection['language_selection']['languages'][:1]
        projection['key_terms'] = {'en':[]}
        self.context.call_settings = CallSettings.from_authorized_response(payload,ASSISTANT,VOICE_AGENT)
        response = await self.create()
        self.assertEqual(response.status,200,await response.text())
        self.assertEqual(self.factory_contexts,[self.context])

    async def test_context_binding_is_checked_before_unsupported_settings(self):
        self.context.call_settings = SimpleNamespace(unsupported_language_selection=True)
        self.context.assistant_id = '0' * 32
        response = await self.create()
        self.assertEqual(response.status,403)
        self.assertEqual(await response.json(),{'error':'forbidden'})
        self.assertEqual(self.factory_contexts,[])

    async def test_supported_language_selection_keeps_context_factory_contract(self):
        self.context.call_settings = SimpleNamespace(unsupported_language_selection=False)
        response = await self.create()
        self.assertEqual(response.status,200,await response.text())
        self.assertEqual(self.factory_contexts,[self.context])

    async def test_shared_capacity_prevents_context_factory_allocation(self):
        browser_call = object()
        self.active.add(browser_call)
        response = await self.create()
        self.assertEqual(response.status, 503)
        self.assertEqual(self.factory_contexts, [])
        self.assertEqual(self.calls, [])
        self.active.remove(browser_call)

    async def test_context_is_rechecked_before_context_factory(self):
        self.context.assistant_id = '0' * 32
        response = await self.create()
        self.assertEqual(response.status, 403)
        self.assertEqual(self.factory_contexts, [])
        self.assertEqual(self.calls, [])

    async def test_session_deadline_uses_validated_per_call_duration(self):
        with patch.object(sessions, 'time', SimpleNamespace(monotonic=lambda: 100.0)):
            response = await self.create()
            self.assertEqual(response.status, 200, await response.text())
            sid = (await response.json())['session_id']
            self.assertEqual(self.manager.sessions[sid].deadline, 400.0)

    async def test_shutdown_reports_unresolved_cleanup_and_retains_owned_close(self):
        response = await self.create()
        self.assertEqual(response.status,200,await response.text())
        sid = (await response.json())['session_id']
        session = self.manager.sessions[sid]
        call = self.calls[0]
        call.close_release.clear()
        try:
            deleting = await self.client.delete(sessions.BASE + '/' + sid,
                headers={'Authorization':'Bearer ' + TOKEN})
            self.assertEqual(deleting.status,202)
            await asyncio.wait_for(call.close_entered.wait(),1)
            with patch.object(sessions,'SHUTDOWN_CLEANUP_SECONDS',.01,create=True):
                with self.assertLogs('sdk_sessions',level='WARNING') as logs:
                    try:
                        await asyncio.wait_for(self.manager.shutdown(),.2)
                    except TimeoutError:
                        self.fail('SDK shutdown exceeded its bounded cleanup wait')
            self.assertTrue(self.manager.stopping)
            self.assertIn(call,self.active)
            self.assertFalse(call.close_complete.is_set())
            self.assertFalse(session.close_task.done())
            self.assertIn('unresolved=1',logs.output[0])
            self.assertEqual(call.close_count,1)
        finally:
            call.close_release.set()
            await asyncio.wait_for(call.close_complete.wait(),1)
            await session.close_task
        self.assertNotIn(call,self.active)
        self.assertEqual(call.close_count,1)

    async def test_invalid_or_longer_call_duration_cannot_expand_startup_budget(self):
        for duration in (True, -1, 0, 1801, float('nan'), float('inf'), '300'):
            self.call_duration = duration
            with self.subTest(duration=duration), \
                    patch.object(sessions, 'time', SimpleNamespace(monotonic=lambda: 100.0)):
                response = await self.create()
                self.assertEqual(response.status, 200, await response.text())
                sid = (await response.json())['session_id']
                session = self.manager.sessions[sid]
                self.assertEqual(session.deadline, 1900.0)
                await self.manager.shutdown()
                self.manager.stopping = False


if __name__ == '__main__':
    unittest.main(verbosity=2)
