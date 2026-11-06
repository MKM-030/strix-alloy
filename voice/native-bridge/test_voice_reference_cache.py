"""Authorized reference bytes/cache boundaries; no real service, DLL or model."""
import asyncio
import copy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import wave

from voice_reference_cache import ReferenceCache, ReferenceUnavailable


SERVICE, TTS, ATTACHMENT = 'a'*32, 'b'*32, 'c'*32
VOICE = '81959ffa-c2ef-4db5-bf95-5df2a24c9404'


def fixture():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\x01\x00' * 72000)
    data = stream.getvalue()
    return data, dict(version=1, service_id=SERVICE, tts_config_sys_id=TTS,
        voice_id=VOICE, attachment_sys_id=ATTACHMENT, sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data), reference_text='Dies ist die freigegebene eigene Aufnahme.',
        reference_language='de', provenance=dict(kind='authorized_own_voice',
            profile_id='20261017T224025Z-290c3e30ad1b',
            consent_scope='local_synthetic_voice_and_servicenow_demo',
            confirmed_at_utc='2026-10-17T22:40:25+00:00'))


class Response:
    def __init__(self, data, status):
        self.status, self.remaining = status, bytearray(data)
        self.headers = {'Content-Type':'audio/wav','Cache-Control':'no-store'}
        self.content = self
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def read(self, limit):
        chunk = bytes(self.remaining[:min(limit, 7777)])
        del self.remaining[:len(chunk)]
        return chunk


class HTTP:
    def __init__(self, data):
        self.data, self.status, self.requests = data, 200, []
    def post(self, url, **options):
        self.requests.append((url, copy.deepcopy(options)))
        return Response(self.data, self.status)


class ReferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data, self.descriptor = fixture()
        self.http, self.registrations, self.owner = HTTP(self.data), [], (42, 1.0)
        async def register(**payload):
            self.registrations.append(payload)
            await asyncio.sleep(0)
        self.cache = ReferenceCache(self.http, 'https://unit-test.service-now.com',
            Path(self.temporary.name), register=register, owner_identity=lambda:self.owner)

    async def prepare(self, **changes):
        values = dict(service_id=SERVICE, tts_config_sys_id=TTS, voice_id=VOICE,
            language='en-US', reference=self.descriptor, authorization='Bearer caller-test-token')
        values.update(changes)
        return await self.cache.prepare(**values)

    async def test_each_cache_hit_requires_caller_authorization_but_registers_immutable_alias_once(self):
        first, second = await asyncio.gather(self.prepare(), self.prepare())
        self.assertEqual(first, second)
        self.assertEqual(first.selected_voice_id, VOICE)
        self.assertTrue(first.registry_voice_id.startswith('snref-'))
        self.assertNotEqual(first.registry_voice_id, VOICE)
        self.assertEqual(len(self.registrations), 1)
        self.assertEqual(self.registrations[0], dict(voice_id=first.registry_voice_id,
            reference_text=self.descriptor['reference_text'], wav_bytes=self.data))
        self.assertEqual(len(self.http.requests), 2)
        for url, options in self.http.requests:
            self.assertEqual(url, 'https://unit-test.service-now.com/api/sn_voice_aia/ai_voice_agent/agents_authorized')
            self.assertEqual(options['headers']['Authorization'], 'Bearer caller-test-token')
            self.assertFalse(options['allow_redirects'])
            self.assertEqual(options['json'], dict(serviceId=SERVICE, assistantSettingsVersion=1,
                voiceReferenceVersion=1, language='en-US', reference=self.descriptor))
        for path in Path(self.temporary.name).rglob('*'):
            if path.is_file():
                self.assertNotIn(b'caller-test-token', path.read_bytes())
        self.http.status = 403
        with self.assertRaises(ReferenceUnavailable):
            await self.prepare()
        self.assertEqual(len(self.registrations), 1)

    async def test_wrong_selected_binding_and_invalid_descriptor_never_fetch(self):
        for changes in (dict(service_id='d'*32), dict(tts_config_sys_id='d'*32), dict(voice_id='other'),
                        dict(authorization='Basic admin'), dict(language='https://evil')):
            with self.subTest(changes=changes):
                with self.assertRaises(ReferenceUnavailable):
                    await self.prepare(**changes)
        for key, value in (('sha256','x'*64), ('size_bytes',True), ('reference_text','bad'),
                           ('reference_language',''), ('extra','bad')):
            descriptor = dict(self.descriptor, **{key:value})
            with self.assertRaises(ReferenceUnavailable):
                await self.prepare(reference=descriptor)
        self.assertEqual(self.http.requests, [])

    async def test_hash_size_and_pcm_fail_before_registration_or_cache(self):
        for data in (self.data[:-2], b'x'*len(self.data), self.data + b'xx'):
            self.http.data = data
            with self.assertRaises(ReferenceUnavailable):
                await self.prepare()
        invalid = b'x'*100
        self.http.data = invalid
        self.descriptor.update(sha256=hashlib.sha256(invalid).hexdigest(), size_bytes=len(invalid))
        with self.assertRaises(ReferenceUnavailable):
            await self.prepare()
        self.assertEqual(self.registrations, [])
        self.assertEqual(list(Path(self.temporary.name).iterdir()), [])

    async def test_tampered_cache_fails_closed_and_new_transcript_has_another_alias(self):
        first = await self.prepare()
        descriptor = dict(self.descriptor, reference_text='Ein anderer vollständig freigegebener Referenztext.')
        second = await self.prepare(reference=descriptor)
        self.assertNotEqual(first.registry_voice_id, second.registry_voice_id)
        self.assertEqual(first.selected_voice_id, second.selected_voice_id)
        first.wav_path.write_bytes(b'tampered')
        with self.assertRaises(ReferenceUnavailable):
            await self.prepare()
        self.assertEqual(len(self.registrations), 2)

    async def test_registry_owner_change_requires_registration_again_and_lost_receipt_is_not_reused(self):
        first = await self.prepare()
        self.owner = (43, 2.0)
        self.assertEqual((await self.prepare()).registry_voice_id, first.registry_voice_id)
        self.assertEqual(len(self.registrations), 2)
        async def changing_owner(**payload):
            self.registrations.append(payload)
            self.owner = (44, 3.0)
        self.cache.register = changing_owner
        self.owner = (45, 4.0)
        with self.assertRaises(ReferenceUnavailable):
            await self.prepare()
        async def good(**payload):
            self.registrations.append(payload)
        self.cache.register = good
        await self.prepare()
        self.assertEqual(len(self.registrations), 4)


if __name__ == '__main__':
    unittest.main()
