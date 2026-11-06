"""Offline checks for exact native voice binding and local TTS capabilities."""
import asyncio
import copy
import unittest
import json
from types import SimpleNamespace

from assistant_settings import CallSettings
from native_bridge import Config, Speech
from test_assistant_settings import AGENT, SERVICE, authorized_settings


OWN_VOICE = '29bf2c49-f921-4760-8110-aad2aa884839'
OTHER_VOICE = '94424c74-10bb-4c3e-bb25-5a60dc355c28'


def native_config():
    return Config(auth_mode='servicenow', instance_name='unit-test',
                  voice_service_id=SERVICE, required_agent_id=AGENT)


def settings(voice_id=OWN_VOICE):
    response = authorized_settings()
    projection = response['result']['assistant_settings']
    projection['tts']['voice_profile'] = 'Marcel (lokal)'
    projection['tts']['voices']['de-DE']['voice_id'] = voice_id
    projection['tts']['voices']['en-US']['voice_id'] = OTHER_VOICE
    return CallSettings.from_authorized_response(response, SERVICE, AGENT)


class Content:
    async def iter_chunked(self, size):
        await asyncio.sleep(0)
        yield b'\x01\x00' * 24


class EmptyContent:
    async def iter_chunked(self, size):
        if False:
            yield b''


class Response:
    status = 200
    content = Content()

    async def __aenter__(self):
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, *args):
        return False


class HTTP:
    def __init__(self, on_post=None, status=200, empty=False):
        self.requests = []
        self.on_post = on_post
        self.status = status
        self.empty = empty
        self.capability = {'version': 1, 'per_request_language': True,
                           'languages': ['german', 'english']}
        self.gets = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        response = Response()
        remaining = bytearray(json.dumps(self.capability).encode())
        async def read(limit):
            data = bytes(remaining[:limit])
            del remaining[:limit]
            return data
        response.content = SimpleNamespace(read=read)
        return response

    def post(self, url, **kwargs):
        self.requests.append((url, copy.deepcopy(kwargs)))
        if self.on_post:
            self.on_post()
        response = Response()
        response.status = self.status
        if self.empty:
            response.content = EmptyContent()
        return response


async def synthesize(speech, text='Configured greeting'):
    return b''.join([chunk async for chunk in speech.synthesize(text)])


class TTSCallBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_qwen_asr_posts_only_selected_locale_terms(self):
        from test_speech_diagnostics import HTTP as ASRHTTP
        config = SimpleNamespace(asr_backend='qwen3-asr-0.6b', asr_url='http://127.0.0.1:8851/v1/audio/transcriptions',
                                 private_asr_token='test-token')
        call = settings()
        for phrase, expected in ((None, ['SCC', 'Laptop']), ('English please', ['ServiceNow'])):
            if phrase:
                call.select_language(phrase)
            http = ASRHTTP({'text':'Text'})
            await Speech(http, config, call).transcribe(bytes(320))
            fields = {part[0]['name']:part[2] for part in http.kwargs['data']._fields}
            self.assertEqual(json.loads(fields['key_terms']), expected)
            self.assertFalse(http.kwargs['allow_redirects'])

    async def test_authorized_synthesis_posts_exact_native_id(self):
        http = HTTP()
        call = settings()
        original = call.snapshot()
        pcm = await synthesize(Speech(http, native_config(), call))
        self.assertEqual(pcm, b'\x01\x00' * 24)
        url, options = http.requests[0]
        self.assertEqual(url, Config().tts_url)
        self.assertEqual(options['json'], {
            'model': 'scc-native-qwen3', 'voice': OWN_VOICE,
            'input': 'Configured greeting', 'response_format': 'pcm', 'max_new_tokens': 375,
            'language': 'german'})
        self.assertFalse(options['allow_redirects'])
        self.assertEqual(call.snapshot(), original)

    async def test_selected_vendor_id_is_never_substituted_with_own_voice(self):
        alina = '38aabb6a-f52b-4fb0-a3d1-988518f4dc06'
        http = HTTP()
        await synthesize(Speech(http, native_config(), settings(alina)))
        self.assertEqual(http.requests[0][1]['json']['voice'], alina)

    async def test_unregistered_voice_rejection_never_retries_another_voice(self):
        http = HTTP(status=400)
        with self.assertRaisesRegex(RuntimeError, '^TTS unavailable$'):
            await synthesize(Speech(http, native_config(), settings()))
        self.assertEqual(len(http.requests), 1)
        self.assertEqual(http.requests[0][1]['json']['voice'], OWN_VOICE)

    async def test_unregistered_pcm_voice_empty_success_never_falls_back(self):
        # The installed PCM handler starts HTTP 200 before engine validation;
        # an unknown registry ID therefore produces an empty successful body.
        http = HTTP(empty=True)
        with self.assertRaisesRegex(RuntimeError, '^TTS returned empty PCM$'):
            await synthesize(Speech(http, native_config(), settings()))
        self.assertEqual(len(http.requests), 1)
        self.assertEqual(http.requests[0][1]['json']['voice'], OWN_VOICE)

    async def test_parallel_calls_keep_separate_voice_ids_and_config(self):
        http = HTTP()
        config = native_config()
        first, second = settings(OWN_VOICE), settings(OTHER_VOICE)
        second.select_language('English please')
        await asyncio.gather(synthesize(Speech(http, config, first), 'first'),
                             synthesize(Speech(http, config, second), 'second'))
        self.assertEqual({item[1]['json']['input']: item[1]['json']['voice']
                          for item in http.requests},
                         {'first': OWN_VOICE, 'second': OTHER_VOICE})
        self.assertEqual(config, native_config())
        self.assertEqual({item[1]['json']['input']:item[1]['json']['language'] for item in http.requests},
                         {'first':'german','second':'english'})

    async def test_locale_switch_during_request_cannot_change_inflight_voice(self):
        call = settings()
        http = HTTP(lambda: call.select_language('English please'))
        speech = Speech(http, native_config(), call)
        await synthesize(speech)
        self.assertEqual(call.language, 'en-US')
        self.assertEqual(http.requests[0][1]['json']['voice'], OWN_VOICE)
        await synthesize(speech)
        self.assertEqual(http.requests[1][1]['json']['voice'], OTHER_VOICE)
        self.assertEqual(http.requests[1][1]['json']['language'], 'english')
        self.assertEqual(http.gets[0][0], 'http://127.0.0.1:8862/v1/audio/capabilities')

    async def test_english_requires_verified_bounded_capability_before_synthesis(self):
        for capability in ({}, {'version':1,'per_request_language':False,'languages':['english']},
                           {'version':True,'per_request_language':True,'languages':['english']},
                           {'version':1,'per_request_language':True,'languages':['german']},
                           {'padding':'x'*3000}):
            call, http = settings(), HTTP()
            call.select_language('English please')
            http.capability = capability
            with self.subTest(capability=capability):
                with self.assertRaisesRegex(RuntimeError, 'TTS language capability unavailable'):
                    await synthesize(Speech(http, native_config(), call))
                self.assertEqual(http.requests, [])
                self.assertFalse(http.gets[0][1]['allow_redirects'])

    async def test_missing_or_empty_configured_voice_refuses_before_http(self):
        for voice in (None, '', '   '):
            call = settings()
            if voice is None:
                call._projection['tts']['voices'].pop('de-DE')
            else:
                call._projection['tts']['voices']['de-DE']['voice_id'] = voice
            http = HTTP()
            with self.subTest(voice=voice):
                with self.assertRaisesRegex(RuntimeError, 'Configured TTS voice is unavailable'):
                    await synthesize(Speech(http, native_config(), call))
                self.assertEqual(http.requests, [])

    async def test_servicenow_synthesis_requires_authorized_settings(self):
        http = HTTP()
        with self.assertRaisesRegex(RuntimeError, 'Authorized TTS settings are unavailable'):
            await synthesize(Speech(http, native_config()))
        self.assertEqual(http.requests, [])

    async def test_unconfigured_development_voice_remains_available(self):
        http = HTTP()
        await synthesize(Speech(http, Config()))
        self.assertEqual(http.requests[0][1]['json']['voice'], 'scc-demo')

    async def test_tts_context_is_detached_and_follows_selected_language(self):
        call = settings()
        context = call.tts_context()
        self.assertEqual(context, {'voice_id': OWN_VOICE, 'language': 'de-DE',
                                   'voice_profile': 'Marcel (lokal)'})
        context['voice_id'] = 'changed outside'
        self.assertEqual(call.tts_context()['voice_id'], OWN_VOICE)
        self.assertTrue(call.select_language('English please'))
        self.assertEqual(call.tts_context()['voice_id'], OTHER_VOICE)
        self.assertEqual(call.tts_context()['language'], 'en-US')

    async def test_native_locale_key_case_does_not_trigger_fallback_voice(self):
        call = settings()
        call._projection['tts']['voices']['de-de'] = call._projection['tts']['voices'].pop('de-DE')
        http = HTTP()
        await synthesize(Speech(http, native_config(), call))
        self.assertEqual(http.requests[0][1]['json']['voice'], OWN_VOICE)


if __name__ == '__main__':
    unittest.main()
