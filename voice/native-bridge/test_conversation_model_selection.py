"""CPU-only frozen native model selection and tools-free local generation."""
import asyncio
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

import assistant_settings
import local_llm_socket
import native_duplex
import native_bridge
import sdk_admission
from sdk_deployment import SDKDeploymentPolicy
import test_wss_authorization as wss_fixture
import test_sdk_assistant_settings as sdk_fixture
from test_sdk_admission import FakeHttp, FakeResponse, ASSISTANT, VOICE_AGENT
from test_native_duplex import FakeCall
from test_assistant_settings import authorized_settings, SERVICE, AGENT
from test_local_llm_fixed_routes import HTTP, DIRECT_CHAT, DIRECT_MODELS, wire_context


def descriptor():
    return dict(version=1, status='selected',
        capability_id='aca5634f4312121038520464dbb8f236',
        definition_config_id='1' * 32, definition_id='2' * 32,
        prompt_binding_id='3' * 32, prompt_id='4' * 32, model_config_id='5' * 32,
        provider_mapping_id='6' * 32, provider_id='7' * 32, implementation_id='8' * 32,
        model_identifier='halogen-v2', binding_sha256='9' * 64)


class ConversationSelectionTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, selection, *, opt_in=True):
        data = authorized_settings()
        if selection is not None:
            data['result']['conversation_model'] = selection
        return assistant_settings.CallSettings.from_authorized_response(data, SERVICE, AGENT,
            conversation_model_version=1 if opt_in else None)

    async def test_descriptor_is_frozen_and_detached_from_response_and_language(self):
        value = descriptor()
        settings = self.settings(value)
        self.assertTrue(settings.conversation_model_required)
        self.assertEqual(settings.conversation_model.model_identifier, 'halogen-v2')
        value['model_identifier'] = 'other-model'
        settings.select_language('English please')
        self.assertEqual(settings.conversation_model.model_identifier, 'halogen-v2')
        with self.assertRaises(FrozenInstanceError):
            settings.conversation_model.model_identifier = 'other-model'
        self.assertNotIn('conversation_model', settings.snapshot())
        self.assertNotIn('conversation_model', settings.native_context())

    async def test_legacy_v1_ignores_unrequested_descriptor_and_keeps_presentation(self):
        settings = self.settings(descriptor(), opt_in=False)
        self.assertFalse(settings.conversation_model_required)
        self.assertIsNone(settings.conversation_model)
        self.assertEqual(settings.introduction, 'Guten Tag.')

    async def test_missing_unavailable_or_malformed_descriptor_disables_only_optional_model(self):
        cases = [None, {'version': 1, 'status': 'unavailable'}, {},
            dict(descriptor(), version=True), dict(descriptor(), version=2),
            dict(descriptor(), extra='PRIVATE'), dict(descriptor(), capability_id='a' * 32),
            dict(descriptor(), model_identifier='Display Name'), dict(descriptor(), binding_sha256='bad'),
            dict(descriptor(), provider_mapping_id=True)]
        for value in cases:
            with self.subTest(value=value):
                settings = self.settings(value)
                self.assertTrue(settings.conversation_model_required)
                self.assertIsNone(settings.conversation_model)
                self.assertEqual(settings.service_id, SERVICE)
                self.assertEqual(settings.introduction, 'Guten Tag.')

    async def test_unavailable_selection_never_opens_optional_transport(self):
        settings = self.settings(None)
        with patch.object(native_duplex, 'prepare_conversation_dependencies',
                          side_effect=AssertionError('No transport dependencies required')):
            with self.assertRaises(RuntimeError):
                await native_duplex.open_conversation('', 'call', 1,
                    controller_url=DIRECT_CHAT, controller_token_file='C:/fixture-token', call_settings=settings)

    async def test_selected_id_is_forwarded_through_real_conversation_factory(self):
        settings = self.settings(descriptor())
        captured = []
        class Socket:
            def __init__(self, url, token, **kwargs):
                captured.append((url, token, kwargs))
        class Adapter:
            def __init__(self, factory, **kwargs):
                self.source = factory()
        class Dialogue:
            def __init__(self, adapter):
                self.adapter = adapter
            async def start(self, *args):
                pass
            async def close(self):
                pass
        with patch.object(native_duplex, 'prepare_conversation_dependencies',
                          return_value=(Adapter, Socket, Dialogue)):
            await native_duplex.open_conversation('', 'call', 1,
                controller_url=DIRECT_CHAT, controller_token_file='C:/fixture-token', call_settings=settings)
        self.assertEqual(captured, [(DIRECT_CHAT, 'C:/fixture-token', {'expected_model': 'halogen-v2'})])

    async def socket_turns(self, models):
        http = HTTP(DIRECT_CHAT, DIRECT_MODELS)
        source = local_llm_socket.LocalTextSocket(DIRECT_CHAT, 'C:/fixture-token',
                                                http=http, expected_model='halogen-v2')
        try:
            with patch.object(local_llm_socket, '_token', return_value='synthetic-token'):
                await source.send_json(dict(type='session.start', mode='text', system_prompt='Rules'))
                await source.send_json(dict(type='session.update', system_prompt_patch=wire_context()))
                for model in models:
                    http.model = model
                    await source.send_json(dict(type='input.text', text='Echte Frage.'))
                    await asyncio.wait_for(source._task, 1)
            events = []
            while not source.events.empty():
                events.append(source.events.get_nowait())
            return http, events
        finally:
            await source.close()

    async def test_matching_selection_uses_existing_one_lookup_and_tools_free_inference(self):
        http, events = await self.socket_turns(['halogen-v2'])
        self.assertEqual(http.requests, [('GET', DIRECT_MODELS), ('POST', DIRECT_CHAT)])
        self.assertEqual(http.bodies[0]['model'], 'halogen-v2')
        self.assertNotIn('tools', http.bodies[0])
        self.assertTrue(any(item['type'] == 'response.text.done' for item in events))

    async def test_mid_call_model_change_disables_optional_inference_without_fallback_or_retry(self):
        http, events = await self.socket_turns(['halogen-v2', 'other-model', 'halogen-v2'])
        self.assertEqual(http.requests, [('GET', DIRECT_MODELS), ('POST', DIRECT_CHAT), ('GET', DIRECT_MODELS)])
        self.assertEqual(len(http.bodies), 1)
        self.assertEqual(len([item for item in events if item['type'] == 'error']), 2)

    async def test_initial_mismatch_makes_no_inference_request(self):
        http, events = await self.socket_turns(['different-case-Halogen-v2'])
        self.assertEqual(http.requests, [('GET', DIRECT_MODELS)])
        self.assertEqual(http.bodies, [])
        self.assertTrue(any(item['type'] == 'error' for item in events))

    async def test_unavailable_optional_selection_preserves_original_business_delivery(self):
        call = FakeCall()
        call.call_settings = self.settings(None)
        call.config.conversation_http_url = DIRECT_CHAT
        call.config.conversation_token_file = 'C:/fixture-token'
        lane = native_duplex.NativeDuplex(call)
        running = asyncio.create_task(lane.run())
        try:
            with patch.object(native_duplex, 'prepare_conversation_dependencies',
                              side_effect=AssertionError('Unavailable selection cannot open a model')):
                call.feed('Bitte verarbeite meine Originalangabe.')
                self.assertEqual(await asyncio.wait_for(call.dialog.started.get(), 1),
                                 'Bitte verarbeite meine Originalangabe.')
                async with asyncio.timeout(1):
                    while not lane._model_failed:
                        await asyncio.sleep(.001)
            self.assertEqual(call.dialog.calls, ['Bitte verarbeite meine Originalangabe.'])
            self.assertFalse(call.failed)
            self.assertFalse(running.done())
        finally:
            call.closed = True
            running.cancel()
            await asyncio.gather(running, return_exceptions=True)
            await lane.close()


class ConversationSelectionAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_admission_opts_in_and_retains_frozen_model(self):
        payload = authorized_settings()
        payload['result']['conversation_model'] = descriptor()
        http = wss_fixture.Http(wss_fixture.Response(payload=payload))
        fixture = wss_fixture.WssAuthorizationTests()
        config = fixture.config(conversation_http_url=DIRECT_CHAT, conversation_ws_url='')
        settings = await native_bridge.authorize(fixture.request(), config, http, with_settings=True)
        self.assertEqual(http.calls[0][1]['json']['conversationModelVersion'], 1)
        self.assertTrue(settings.conversation_model_required)
        self.assertEqual(settings.conversation_model.model_identifier, 'halogen-v2')

    async def test_browser_older_server_keeps_business_settings_but_cannot_fallback(self):
        http = wss_fixture.Http(wss_fixture.Response(payload=authorized_settings()))
        fixture = wss_fixture.WssAuthorizationTests()
        config = fixture.config(conversation_http_url=DIRECT_CHAT)
        settings = await native_bridge.authorize(fixture.request(), config, http, with_settings=True)
        self.assertIsInstance(settings, assistant_settings.CallSettings)
        self.assertTrue(settings.conversation_model_required)
        self.assertIsNone(settings.conversation_model)

    async def test_sdk_admission_opts_in_and_freezes_same_descriptor(self):
        payload = sdk_fixture.authorized_projection()
        payload['result']['conversation_model'] = descriptor()
        http = FakeHttp(FakeResponse(payload=payload))
        policy = SDKDeploymentPolicy(sdk_fixture.INSTANCE, ASSISTANT, VOICE_AGENT,
                                     'https://voice.example.com')
        context = await sdk_admission.admit_sdk_session(
            [('Authorization', 'Bearer synthetic-descriptor-token'), ('Content-Type', 'application/json')],
            b'{"agent_id":"agent_operator"}', query_string=sdk_fixture.QUERY, policy=policy,
            http_factory=http.factory, assistant_settings_version=1, conversation_model_version=1)
        self.assertEqual(http.calls[0][1]['json'],
            {'serviceId': ASSISTANT, 'assistantSettingsVersion': 1, 'conversationModelVersion': 1})
        self.assertTrue(context.call_settings.conversation_model_required)
        self.assertEqual(context.call_settings.conversation_model.model_identifier, 'halogen-v2')

    async def test_sdk_application_enables_opt_in_for_the_shared_call_factory(self):
        config = native_bridge.Config(conversation_http_url=DIRECT_CHAT,
            conversation_transport='controller-text',
            conversation_token_file='C:/synthetic-descriptor-token', native_sdk_enabled=True,
            instance_name='voice-fixture', voice_service_id=SERVICE, required_agent_id=AGENT,
            sdk_public_origin='https://voice.example.com', auth_mode='servicenow')
        with patch('sdk_sessions.register_sdk_routes') as register:
            native_bridge.create_app(config, dialog_factory=lambda: None)
        admission = register.call_args.args[4]
        self.assertEqual(admission.keywords['assistant_settings_version'], 1)
        self.assertEqual(admission.keywords['conversation_model_version'], 1)
