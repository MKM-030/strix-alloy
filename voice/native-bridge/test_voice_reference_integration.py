"""Prepared-handle and SDK callback boundaries without starting the application."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from assistant_settings import CallSettings
from native_bridge import Config, create_app
from sdk_admission import AdmissionDenied
from test_assistant_settings import SERVICE, AGENT, authorized_settings
from test_voice_reference_cache import fixture, TTS, VOICE
from voice_reference_cache import PreparedVoice, ReferenceUnavailable, reference_fingerprint
from voice_reference_runtime import prepare_references


def settings():
    _, descriptor = fixture()
    descriptor['service_id'] = SERVICE
    response = authorized_settings()
    for voice in response['result']['assistant_settings']['tts']['voices'].values():
        voice.update(voice_id=VOICE, tts_config_sys_id=TTS, reference=descriptor)
    return CallSettings.from_authorized_response(response, SERVICE, AGENT)


def prepared(values):
    reference = values['reference']
    digest = reference_fingerprint(reference)
    return PreparedVoice(values['service_id'], values['tts_config_sys_id'], values['voice_id'],
        'snref-'+digest, digest, reference['sha256'], reference['reference_language'], Path('unused.wav'))


class PreparedHandleTests(unittest.IsolatedAsyncioTestCase):
    async def test_admission_prepares_all_locales_without_retaining_credential(self):
        call = settings()
        cache = SimpleNamespace(prepare=AsyncMock(side_effect=lambda **kw:prepared(kw)))
        await prepare_references(cache, call, 'Bearer original-test-caller')
        self.assertEqual([c.kwargs['language'] for c in cache.prepare.call_args_list], ['de-DE','en-US'])
        self.assertEqual({c.kwargs['authorization'] for c in cache.prepare.call_args_list}, {'Bearer original-test-caller'})
        self.assertEqual(set(call._prepared_voices), {'de-de','en-us'})
        self.assertNotIn('original-test-caller', repr(call))
        self.assertNotIn('original-test-caller', repr(call._prepared_voices))

    async def test_selected_language_uses_explicit_alias_and_preserves_native_identity(self):
        call = settings()
        cache = SimpleNamespace(prepare=AsyncMock(side_effect=lambda **kw:prepared(kw)))
        with self.assertRaises(RuntimeError):
            call.tts_context()
        await prepare_references(cache, call, 'Bearer original-test-caller')
        for choice in (None,'English please'):
            if choice:
                call.select_language(choice)
            context = call.tts_context()
            self.assertEqual(context['voice_id'], VOICE)
            self.assertEqual(context['registry_voice_id'], call._prepared_voices[call.language.casefold()].registry_voice_id)
            self.assertNotEqual(context['registry_voice_id'], context['voice_id'])

    async def test_wrong_handle_identity_and_changed_transcript_are_rejected(self):
        call = settings()
        cache = SimpleNamespace(prepare=AsyncMock(side_effect=lambda **kw:prepared(kw)))
        await prepare_references(cache, call, 'Bearer original-test-caller')
        original = call._prepared_voices['de-de']
        for changes in ({'service_id':'e'*32}, {'tts_config_sys_id':'e'*32},
                        {'selected_voice_id':'other'}, {'reference_sha256':'0'*64},
                        {'descriptor_sha256':'0'*64}, {'registry_voice_id':VOICE}):
            call._prepared_voices['de-de'] = replace(original, **changes)
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError):
                    call.tts_context()
        call._prepared_voices['de-de'] = original
        call._projection['tts']['voices']['de-DE']['reference']['reference_text'] += ' Geändert.'
        with self.assertRaises(RuntimeError):
            call.tts_context()

    async def test_preparation_failure_publishes_no_partial_language_handles(self):
        call = settings()
        async def prepare(**values):
            if values['language'] == 'en-US':
                raise ReferenceUnavailable()
            return prepared(values)
        with self.assertRaises(ReferenceUnavailable):
            await prepare_references(SimpleNamespace(prepare=prepare), call, 'Bearer original-test-caller')
        self.assertEqual(call._prepared_voices, {})


class SDKReferenceHookTests(unittest.IsolatedAsyncioTestCase):
    def hook(self, native_admit):
        config = Config(auth_mode='servicenow', instance_name='unit-test',
            voice_service_id=SERVICE, required_agent_id=AGENT, native_sdk_enabled=True,
            sdk_public_origin='https://voice.example.com')
        captured = {}
        def register(app, config, active, make_call, admit_sdk_session, **kwargs):
            captured['admit'] = admit_sdk_session
            captured['prepare'] = kwargs['prepare_context']
        with patch('sdk_admission.admit_sdk_session', native_admit), \
                patch('sdk_sessions.register_sdk_routes', register):
            create_app(config)
        return captured['admit'], captured['prepare'], config

    async def test_sdk_admission_kwargs_and_original_caller_reach_preparer_after_authorization(self):
        call, order = settings(), []
        context = SimpleNamespace(call_settings=call)
        async def admitted(*args, **kwargs):
            order.append('authorized')
            return context
        native = AsyncMock(side_effect=admitted)
        hook, preparation, config = self.hook(native)
        async def prepare(cache, settings, authorization):
            order.append('prepared')
            self.assertIs(settings, call)
            self.assertEqual(authorization, 'Bearer original-test-caller')
        headers = [('AUTHORIZATION','Bearer original-test-caller')]
        with patch('voice_reference_runtime.prepare_references', prepare):
            result = await hook(headers, b'{"agent_id":"agent_operator"}', query_string='instance_name=unit-test&receive_data=true')
            self.assertEqual(order, ['authorized'])
            self.assertIs(await preparation(result, 'Bearer original-test-caller'), context)
        self.assertEqual(order, ['authorized','prepared'])
        self.assertIs(native.call_args.kwargs['policy'], config.sdk_policy)
        self.assertEqual(native.call_args.kwargs['assistant_settings_version'], 1)
        self.assertEqual(native.call_args.kwargs['query_string'], 'instance_name=unit-test&receive_data=true')

    async def test_rejected_sdk_authorization_never_prepares_and_reference_denial_never_returns_context(self):
        native = AsyncMock(side_effect=AdmissionDenied(403))
        hook, preparation, _ = self.hook(native)
        with patch('voice_reference_runtime.prepare_references', AsyncMock()) as prepare:
            with self.assertRaises(AdmissionDenied):
                await hook([('Authorization','Bearer original-test-caller')], b'{}', query_string='x')
            prepare.assert_not_awaited()
        native.side_effect = None
        native.return_value = SimpleNamespace(call_settings=settings())
        with patch('voice_reference_runtime.prepare_references', AsyncMock(side_effect=ReferenceUnavailable())):
            context = await hook([('Authorization','Bearer original-test-caller')], b'{}', query_string='x')
            with self.assertRaises(ReferenceUnavailable):
                await preparation(context, 'Bearer original-test-caller')


if __name__ == '__main__':
    unittest.main()
