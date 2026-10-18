"""HTTP boundary tests: owned speech integration is replaced, not models started."""
from datetime import datetime, timezone
import array
import asyncio
import base64
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

HERE = Path(__file__).resolve().parent
ORIGIN = 'https://strix-alloy.tail7f425a.ts.net'
PASSWORD = 'test-only-long-secret'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def wav_bytes():
    output = io.BytesIO()
    pcm = array.array('h', [round(5000 * math.sin(i / 17)) for i in range(24000 * 4)])
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes(pcm.tobytes())
    return output.getvalue()


class VoiceStudioHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue((HERE / 'studio_server.py').exists(), 'Voice Studio HTTP backend must exist')
        self.server = load(HERE / 'studio_server.py', 'scc_studio_test')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        manager_path = HERE.parent / 'voice-profile' / 'manage_voice.py'
        if not manager_path.exists():
            manager_path = HERE.parent.parent / 'voice-profile' / 'manage_voice.py'
        self.manager = load(manager_path, 'scc_studio_manager_test')
        self.manager.DEFAULT_PROFILE = self.root / 'nonexistent-synthetic'
        self.config = self.server.Config(origin=ORIGIN, runtime=self.root / 'runtime',
            profile_root=self.root / 'profiles', web_root=self.root / 'web')
        self.config.web_root.mkdir()
        (self.config.web_root / 'index.html').write_text('<h1>Voice Studio</h1>')
        await asyncio.to_thread(self.server.initialize_auth, self.config.auth_file, PASSWORD)
        self.live_sessions = 0
        self.registered = []
        self.register_error = None
        self.register_entered = threading.Event()
        self.register_release = None
        self.preview_texts = []
        def register(profile):
            self.register_entered.set()
            if self.register_release:
                self.register_release.wait(3)
            if self.register_error:
                raise self.register_error
            self.registered.append(profile['profile_id'])
            return {'status': 200}
        async def idle_check():
            return self.live_sessions
        def synthesize(text):
            self.preview_texts.append(text)
            return b'\x00\x00' * 24000
        self.app = self.server.create_app(self.config, manager=self.manager,
            register=register, idle_check=idle_check, synthesize=synthesize,
            now=lambda: datetime(2026,10,13,20,tzinfo=timezone.utc))
        self.client = TestClient(TestServer(self.app), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.headers = {'Origin': ORIGIN}
        self.cookie = ''

    async def login(self):
        response = await self.client.post('/api/login', json={'password': PASSWORD}, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        body = await response.json()
        self.headers['X-CSRF-Token'] = body['csrf']
        self.cookie = response.cookies[self.server.COOKIE_NAME].value
        self.headers['Cookie'] = self.server.COOKIE_NAME + '=' + self.cookie
        return response

    def upload(self, name='Eigene Stimme'):
        return {'name': name, 'reference_text': self.server.REFERENCE_TEXT, 'language': 'German',
            'source': 'desktop_microphone', 'wav_b64': base64.b64encode(wav_bytes()).decode(),
            'consent': {'own_voice': True, 'scope': self.manager.CONSENT_SCOPE,
                        'confirmed_at_utc': '2026-10-13T20:00:00Z'}}

    async def stage(self, name='Eigene Stimme'):
        response = await self.client.post('/api/profiles', json=self.upload(name), headers=self.headers)
        self.assertEqual(response.status, 201, await response.text())
        return (await response.json())['profile']

    async def activate(self, profile):
        return await self.client.post('/api/profiles/' + profile['id'] + '/activate',
            json={}, headers=self.headers)

    async def test_private_profiles_and_audio_require_login(self):
        for path in ['/api/profiles', '/api/profiles/20261013T000000Z-123456abcdef/audio']:
            response = await self.client.get(path)
            self.assertEqual(response.status, 401)
        self.assertEqual((await self.client.get('/health')).status, 200)

    async def test_login_sets_secure_cookie_and_logout_invalidates_session(self):
        response = await self.login()
        cookie = response.cookies[self.server.COOKIE_NAME]
        self.assertTrue(cookie['secure']); self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        session = await self.client.get('/api/session', headers=self.headers)
        self.assertTrue((await session.json())['authenticated'])
        response = await self.client.post('/api/logout', json={}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await self.client.get('/api/profiles', headers=self.headers)).status, 401)

    async def test_login_rejects_wrong_origin_and_password(self):
        response = await self.client.post('/api/login', json={'password': PASSWORD},
            headers={'Origin': 'https://evil.test'})
        self.assertEqual(response.status, 403)
        response = await self.client.post('/api/login', json={'password': 'wrong'}, headers=self.headers)
        self.assertEqual(response.status, 401)

    async def test_login_throttles_repeated_failures(self):
        for _ in range(5):
            response = await self.client.post('/api/login', json={'password': 'wrong'}, headers=self.headers)
            self.assertEqual(response.status, 401)
        response = await self.client.post('/api/login', json={'password': PASSWORD}, headers=self.headers)
        self.assertEqual(response.status, 429)

    async def test_mutations_require_origin_and_csrf(self):
        await self.login()
        headers = dict(self.headers); headers.pop('X-CSRF-Token')
        self.assertEqual((await self.client.post('/api/profiles', json={}, headers=headers)).status, 403)
        headers = dict(self.headers); headers['Origin'] = 'https://evil.test'
        self.assertEqual((await self.client.post('/api/profiles', json={}, headers=headers)).status, 403)

    async def test_upload_persists_private_reference_without_selecting_or_registering(self):
        await self.login(); profile = await self.stage()
        self.assertFalse(profile['selected'])
        self.assertTrue((self.config.profile_root / 'revisions' / profile['id'] / 'reference.wav').exists())
        self.assertFalse((self.config.profile_root / 'active.json').exists())
        response = await self.client.get('/api/profiles', headers=self.headers)
        body = await response.json()
        self.assertEqual(body['profiles'][0]['id'], profile['id'])
        self.assertNotIn('source_path', json.dumps(body)); self.assertNotIn('profile_dir', json.dumps(body))
        response = await self.client.get('/api/profiles/' + profile['id'] + '/audio', headers=self.headers)
        self.assertEqual(await response.read(), wav_bytes())
        self.assertEqual(self.registered, [])

    async def test_missing_own_voice_consent_is_rejected_before_persistence(self):
        await self.login(); data = self.upload(); data['consent']['own_voice'] = False
        response = await self.client.post('/api/profiles', json=data, headers=self.headers)
        self.assertEqual(response.status, 400)
        self.assertFalse((self.config.profile_root / 'revisions').exists())

    async def test_invalid_base64_and_oversized_body_are_bounded(self):
        await self.login(); data = self.upload(); data['wav_b64'] = '!!!'
        self.assertEqual((await self.client.post('/api/profiles', json=data, headers=self.headers)).status, 400)
        response = await self.client.post('/api/profiles', data=io.BytesIO(b' ' * (self.server.MAX_BODY_BYTES + 1)),
            headers=dict(self.headers, **{'Content-Type': 'application/json'}))
        self.assertEqual(response.status, 413)

    async def test_profile_path_traversal_and_runtime_files_are_unavailable(self):
        await self.login()
        for path in ['/api/profiles/..%5C..%5Csecret/audio', '/runtime/auth.json',
                     '/voice-studio/runtime/auth.json', '/voice-studio/%2e%2e/runtime/auth.json']:
            response = await self.client.get(path, headers=self.headers)
            self.assertEqual(response.status, 404, path)

    async def test_activation_reuses_transaction_and_selection_is_durable(self):
        await self.login(); profile = await self.stage()
        response = await self.activate(profile)
        self.assertEqual(response.status, 200, await response.text())
        body = await response.json()
        self.assertTrue(body['profile']['selected'])
        self.assertEqual(self.manager.selected_profile(self.config.profile_root)['profile_id'], profile['id'])
        self.assertEqual(self.registered, [profile['id']])

    async def test_rejected_activation_keeps_good_profile_selected(self):
        await self.login(); first = await self.stage(); second = await self.stage('Zweite Stimme')
        self.assertEqual((await self.activate(first)).status, 200)
        pointer = (self.config.profile_root / 'active.json').read_bytes()
        self.register_error = self.manager.RegistrationRejected('invalid reference')
        with self.assertLogs('scc.voice_studio', level='ERROR'):
            response = await self.activate(second)
        self.assertEqual(response.status, 503)
        self.assertEqual((self.config.profile_root / 'active.json').read_bytes(), pointer)

    async def test_live_call_blocks_activation_and_preview(self):
        await self.login(); profile = await self.stage(); self.live_sessions = 1
        self.assertEqual((await self.activate(profile)).status, 409)
        response = await self.client.post('/api/preview', json={}, headers=self.headers)
        self.assertEqual(response.status, 409)
        self.assertEqual(self.registered, []); self.assertEqual(self.preview_texts, [])

    async def test_unavailable_native_health_fails_closed_before_activation(self):
        await self.login(); profile = await self.stage()
        self.live_sessions = None
        with self.assertLogs('scc.voice_studio', level='ERROR'):
            response = await self.activate(profile)
        self.assertEqual(response.status, 503)
        self.assertEqual(self.registered, [])
        self.assertFalse((self.config.profile_root / 'active.json').exists())

    async def test_tampered_reference_is_never_registered(self):
        await self.login(); profile = await self.stage()
        reference = self.config.profile_root / 'revisions' / profile['id'] / 'reference.wav'
        reference.write_bytes(b'changed')
        response = await self.activate(profile)
        self.assertEqual(response.status, 400)
        self.assertEqual(self.registered, [])

    async def test_preview_and_failed_rollback_do_not_make_false_state_claims(self):
        await self.login(); first = await self.stage(); second = await self.stage('Zweite Stimme')
        self.assertEqual((await self.activate(first)).status, 200)
        self.register_error = RuntimeError('response lost and rollback failed')
        with self.assertLogs('scc.voice_studio', level='ERROR'):
            response = await self.activate(second)
        self.assertEqual(response.status, 503)
        error = (await response.json())['error']
        self.assertNotIn('bleibt bestehen', error)
        self.assertNotIn('response lost', error)

    async def test_non_ascii_csrf_is_rejected_as_forbidden(self):
        await self.login()
        headers = dict(self.headers, **{'X-CSRF-Token': 'ü'})
        response = await self.client.post('/api/profiles', json={}, headers=headers)
        self.assertEqual(response.status, 403)

    async def test_public_session_never_contains_access_code(self):
        response = await self.client.get('/api/session')
        body = await response.json()
        self.assertFalse(body['authenticated'])
        self.assertEqual(body['reference_text'], self.server.REFERENCE_TEXT)
        self.assertNotIn('csrf', body)
        self.assertNotIn(PASSWORD, json.dumps(body))

    async def test_auth_initialization_never_replaces_existing_code(self):
        initial = self.config.auth_file.read_bytes()
        with self.assertRaises(FileExistsError):
            self.server.initialize_auth(self.config.auth_file, 'another-test-secret')
        self.assertEqual(self.config.auth_file.read_bytes(), initial)

    async def test_failed_operator_file_permission_setup_never_leaves_orphan_auth(self):
        self.config.auth_file.unlink()
        access_file = self.root / 'operator.txt'
        def permissions(path, **kwargs):
            if Path(path) == access_file:
                raise OSError('permission setup failed')
        with patch.object(self.server, 'restrict_private_path', side_effect=permissions):
            with self.assertRaises(OSError):
                self.server.initialize_operator_access(self.config, access_file)
        self.assertFalse(access_file.exists())
        self.assertFalse(self.config.auth_file.exists())

    async def test_incomplete_exclusive_auth_write_is_removed_by_its_creator(self):
        self.config.auth_file.unlink()
        access_file = self.root / 'operator.txt'
        with patch.object(self.server.json, 'dump', side_effect=OSError('simulated partial auth write')):
            with self.assertRaises(OSError):
                self.server.initialize_operator_access(self.config, access_file)
        self.assertFalse(self.config.auth_file.exists())
        self.assertFalse(access_file.exists())

    async def test_operator_access_initialization_preserves_existing_auth_and_access(self):
        access_file = self.root / 'operator.txt'; access_file.write_text('existing instructions')
        verifier = self.config.auth_file.read_bytes()
        self.assertFalse(self.server.initialize_operator_access(self.config, access_file))
        self.assertEqual(access_file.read_text(), 'existing instructions')
        self.assertEqual(self.config.auth_file.read_bytes(), verifier)

    async def test_operator_access_file_and_auth_match_without_printing_code(self):
        self.config.auth_file.unlink()
        access_file = self.root / 'operator.txt'
        self.assertTrue(self.server.initialize_operator_access(self.config, access_file))
        text = access_file.read_text(encoding='utf-8')
        code = text.split('Zugangscode: ')[1].splitlines()[0]
        self.assertGreaterEqual(len(code), 24)
        self.assertTrue(self.server.password_matches(self.server.read_auth(self.config.auth_file), code))
        self.assertIn(ORIGIN + '/voice-studio/', text)

    async def test_overlapping_activation_is_rejected_without_changing_good_profile(self):
        await self.login(); first = await self.stage(); second = await self.stage('Zweite Stimme')
        self.register_release = threading.Event()
        task = asyncio.create_task(self.activate(first))
        await asyncio.to_thread(self.register_entered.wait, 2)
        try:
            response = await self.activate(second)
            self.assertEqual(response.status, 409)
        finally:
            self.register_release.set()
        self.assertEqual((await task).status, 200)
        self.assertEqual(self.manager.selected_profile(self.config.profile_root)['profile_id'], first['id'])

    async def test_preview_uses_only_selected_alias_and_returns_wav_without_switching(self):
        await self.login(); profile = await self.stage(); self.assertEqual((await self.activate(profile)).status, 200)
        pointer = (self.config.profile_root / 'active.json').read_bytes()
        response = await self.client.post('/api/preview', json={'text': 'Guten Tag.'}, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text() if response.status != 200 else '')
        self.assertEqual(response.content_type, 'audio/wav')
        with wave.open(io.BytesIO(await response.read()), 'rb') as wav:
            self.assertEqual(wav.getframerate(), 24000)
        self.assertEqual(self.preview_texts, ['Guten Tag.'])
        self.assertEqual((self.config.profile_root / 'active.json').read_bytes(), pointer)
        self.assertEqual(self.registered, [profile['id']])

    async def test_prefixed_routes_support_funnel_with_or_without_path_stripping(self):
        self.assertEqual((await self.client.get('/voice-studio/')).status, 200)
        self.assertEqual((await self.client.get('/')).status, 200)
        response = await self.client.get('/voice-studio/api/session')
        self.assertFalse((await response.json())['authenticated'])

    async def test_bare_studio_path_preserves_redirect_location(self):
        response = await self.client.get('/voice-studio', allow_redirects=False)
        self.assertEqual(response.status, 302)
        self.assertEqual(response.headers.get('Location'), '/voice-studio/')


if __name__ == '__main__':
    unittest.main()
