"""Chosen-profile previews use a removable private alias and leave selection intact."""
import asyncio
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import io
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer
import test_studio_server as fixture
import test_retention_cleanup as retention_fixture

DUE = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)
BEFORE = datetime(2026, 10, 16, 5, 59, tzinfo=timezone.utc)
WELCOME = ('Herzlich willkommen bei Sopra Steria auf der Smart Country Convention. '
    'Gemeinsam mit ServiceNow machen wir digitale Services einfach. Ich helfe Ihnen gern, '
    'einen neuen Laptop für Ihren Mitarbeiter zu bestellen.')


class NativeWorker:
    """Real loopback HTTP boundary with the deployed Qwen registry protocol."""
    def __init__(self):
        self.registry = {'scc-demo': 'selected-reference'}
        self.requests = []
        self.speech_error = False
        self.registration_response_lost = False
        self.delete_supported = True
        self.router_404 = False
        self.failed_final_deletes = 0
        self.lost_delete_response = False
        self.after_delete = None
        self.entered = threading.Event()
        self.release = None
        worker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def answer(self, status, value):
                raw = value if isinstance(value, bytes) else json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_DELETE(self):
                worker.requests.append(('DELETE', self.path, None))
                if worker.after_delete:
                    worker.after_delete()
                if not worker.delete_supported:
                    self.answer(501, {'error': {'type': 'not_implemented', 'message': 'no registry'}})
                elif worker.router_404:
                    self.answer(404, {'error': 'route not found'})
                elif self.path.removeprefix('/v1/audio/voices/') in worker.registry:
                    if worker.failed_final_deletes:
                        worker.failed_final_deletes -= 1
                        self.answer(500, {'error': 'temporary reference removal failed'})
                        return
                    worker.registry.pop(self.path.removeprefix('/v1/audio/voices/'))
                    if worker.lost_delete_response:
                        worker.lost_delete_response = False
                        self.connection.close()
                        return
                    self.answer(200, {'status': 'deleted'})
                else:
                    self.answer(404, {'error': {'type': 'not_found_error',
                        'message': 'no registered voice with this name'}})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                worker.requests.append(('POST', self.path, body))
                if self.path == '/v1/audio/voices':
                    worker.registry[body['name']] = hashlib.sha256(
                        base64.b64decode(body['wav_b64'])).hexdigest()
                    if worker.registration_response_lost:
                        self.connection.close()
                        return
                    self.answer(200, {'name': body['name'], 'status': 'registered'})
                elif self.path == '/v1/audio/speech':
                    worker.entered.set()
                    if worker.release:
                        worker.release.wait(5)
                    if worker.speech_error:
                        self.answer(500, {'error': 'worker-private-details'})
                    else:
                        reference_hash = worker.registry[body['voice']]
                        sample = int(reference_hash[:4], 16) % 20000
                        self.answer(200, sample.to_bytes(2, 'little') * (24000 * 5))

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        if self.release:
            self.release.set()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(2)


class ProfilePreviewTests(unittest.IsolatedAsyncioTestCase):
    login = fixture.VoiceStudioHTTPTests.login
    upload = fixture.VoiceStudioHTTPTests.upload
    activate = fixture.VoiceStudioHTTPTests.activate

    async def stage(self, name='Eigene Stimme'):
        data = self.upload(name)
        # Different recordings make a mistaken selected-profile clone visible.
        recording = bytearray(base64.b64decode(data['wav_b64']))
        recording[44:46] = (sum(name.encode()) % 20000).to_bytes(2, 'little')
        data['wav_b64'] = base64.b64encode(recording).decode()
        response = await self.client.post('/api/profiles', json=data, headers=self.headers)
        self.assertEqual(response.status, 201, await response.text())
        return (await response.json())['profile']

    async def asyncSetUp(self):
        await fixture.VoiceStudioHTTPTests.asyncSetUp(self)
        self.worker = NativeWorker()
        self.addCleanup(self.worker.close)
        connection = http.client.HTTPConnection
        def redirect(host, port=None, *args, **kwargs):
            if host == '127.0.0.1' and port == 8862:
                port = self.worker.http.server_port
            return connection(host, port, *args, **kwargs)
        self.addCleanup(patch.stopall)
        patch('http.client.HTTPConnection', side_effect=redirect).start()
        patch.dict('sys.modules', {'psutil': SimpleNamespace(
            virtual_memory=lambda: SimpleNamespace(available=32 * 1024**3))}).start()
        self.ownership_checks = []
        patch.object(self.manager, 'native_module', return_value=SimpleNamespace(
            assert_owned_listener=lambda port: self.ownership_checks.append(port))).start()
        self.now = BEFORE
        async def idle(): return self.live_sessions
        def register(profile):
            self.registered.append(profile['profile_id'])
            return {'status': 200}
        self.app = self.server.create_app(self.config, manager=self.manager,
            register=register, idle_check=idle, synthesize=lambda text: b'\x00\x00' * 24000,
            now=lambda: self.now)
        self.client = TestClient(TestServer(self.app), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def preview(self, profile_id, data=None, headers=None, prefix=''):
        return await self.client.post(prefix + '/api/profiles/' + profile_id + '/preview',
            json={} if data is None else data,
            headers=self.headers if headers is None else headers)

    async def test_chosen_unselected_profile_speaks_while_selected_alias_and_pointer_stay_identical(self):
        await self.login()
        selected = await self.stage('Gewählte Stimme')
        chosen = await self.stage('Andere Stimme')
        self.assertEqual((await self.activate(selected)).status, 200)
        pointer = (self.config.profile_root / 'active.json').read_bytes()
        response = await self.preview(chosen['id'], {'text': '  Guten Tag, liebe Messegäste.  '})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, 'audio/wav')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        reference = self.config.profile_root / 'revisions' / chosen['id'] / 'reference.wav'
        reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
        selected_reference = self.config.profile_root / 'revisions' / selected['id'] / 'reference.wav'
        self.assertNotEqual(reference_hash, hashlib.sha256(selected_reference.read_bytes()).hexdigest())
        expected_sample = int(reference_hash[:4], 16) % 20000
        with wave.open(io.BytesIO(await response.read()), 'rb') as wav:
            self.assertEqual((wav.getframerate(), wav.getsampwidth(), wav.getnchannels()), (24000, 2, 1))
            self.assertGreaterEqual(wav.getnframes() / wav.getframerate(), 4)
            self.assertEqual(wav.readframes(1), expected_sample.to_bytes(2, 'little'))
        self.assertEqual((self.config.profile_root / 'active.json').read_bytes(), pointer)
        self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})
        self.assertEqual(self.registered, [selected['id']])
        speech = next(body for method, path, body in self.worker.requests if path == '/v1/audio/speech')
        self.assertEqual(speech['input'], 'Guten Tag, liebe Messegäste.')
        self.assertNotEqual(speech['voice'], 'scc-demo')

    async def test_profile_preview_needs_no_selected_voice_and_default_is_full_welcome(self):
        await self.login(); chosen = await self.stage()
        self.assertEqual((await self.preview(chosen['id'], prefix='/voice-studio')).status, 200)
        self.assertFalse((self.config.profile_root / 'active.json').exists())
        speech = next(body for method, path, body in self.worker.requests if path == '/v1/audio/speech')
        self.assertEqual(speech['input'], WELCOME)
        session = await (await self.client.get('/api/session', headers=self.headers)).json()
        self.assertEqual(session['preview_text'], WELCOME)
        self.assertEqual(session['max_preview_characters'], 300)

    async def test_authentication_origin_and_csrf_are_required_before_native_requests(self):
        profile_id = '20261013T000000Z-123456abcdef'
        self.assertEqual((await self.preview(profile_id)).status, 401)
        await self.login()
        for headers in [dict(self.headers, Origin='https://evil.test'),
                        {key: value for key, value in self.headers.items() if key != 'X-CSRF-Token'}]:
            self.assertEqual((await self.preview(profile_id, headers=headers)).status, 403)
        self.assertEqual(self.worker.requests, [])

    async def test_text_bounds_and_native_tuning_are_not_client_controlled(self):
        await self.login(); chosen = await self.stage()
        for text in ['  x  ', 'a' * 301, 4, 'Text\u0000verborgen']:
            response = await self.preview(chosen['id'], {'text': text})
            self.assertEqual(response.status, 400)
            self.assertEqual((await response.json())['code'], 'invalid_preview_text')
        self.assertEqual(self.worker.requests, [])
        response = await self.preview(chosen['id'], {'text': 'ä' * 300,
            'voice': 'scc-demo', 'model': 'private-model', 'max_new_tokens': 999999})
        self.assertEqual(response.status, 200)
        speech = next(body for method, path, body in self.worker.requests if path == '/v1/audio/speech')
        self.assertEqual(speech['model'], 'scc-native-qwen3')
        self.assertLessEqual(speech['max_new_tokens'], 360)
        self.assertNotEqual(speech['voice'], 'scc-demo')

    async def test_live_call_and_unknown_idle_state_fail_closed_before_any_native_request(self):
        await self.login(); chosen = await self.stage(); self.live_sessions = 1
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'call_in_progress')
        self.live_sessions = None
        with self.assertLogs('scc.voice_studio', level='ERROR'):
            response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 503)
        self.assertEqual(self.worker.requests, [])

    async def test_own_voice_after_deadline_is_rejected_but_packaged_default_still_previews(self):
        await self.login(); chosen = await self.stage()
        packaged = await self.stage('Mitgeliefert')
        folder = self.config.profile_root / 'revisions' / packaged['id']
        data = json.loads((folder / 'voice.json').read_text())
        data.update(profile_id='synthetic-scc-demo', kind='designed_synthetic_voice')
        (folder / 'voice.json').write_text(json.dumps(data))
        folder.rename(self.manager.DEFAULT_PROFILE)
        self.now = DUE
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'fair_retention_expired')
        self.assertEqual(self.worker.requests, [])
        self.assertEqual((await self.preview('synthetic-scc-demo')).status, 200)
        self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})

    async def test_crossing_deadline_while_waiting_for_activation_lock_never_registers(self):
        await self.login(); chosen = await self.stage(); original = self.manager.activation_lock
        @contextmanager
        def crossing(root):
            with original(root):
                self.now = DUE
                yield
        with patch.object(self.manager, 'activation_lock', side_effect=crossing):
            response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'fair_retention_expired')
        self.assertEqual(self.worker.requests, [])

    async def test_crossing_deadline_during_delete_preflight_never_registers(self):
        await self.login(); chosen = await self.stage()
        self.worker.after_delete = lambda: setattr(self, 'now', DUE)
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'fair_retention_expired')
        self.assertFalse(any(method == 'POST' for method, _, _ in self.worker.requests))

    async def test_symlinked_revisions_directory_is_rejected_before_profile_read(self):
        await self.login(); chosen = await self.stage()
        revisions = self.config.profile_root / 'revisions'
        outside = self.root / 'outside-revisions'
        revisions.rename(outside)
        try:
            revisions.symlink_to(outside, target_is_directory=True)
        except OSError:
            outside.rename(revisions)
            self.skipTest('Creating directory symlinks requires local permission')
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 404)
        self.assertEqual(self.worker.requests, [])

    async def test_invalid_identifier_and_symlinked_reference_are_unavailable(self):
        await self.login(); chosen = await self.stage()
        for profile_id in ['..%5C..%5Cprivate', 'other-alias', '20261013T000000Z-123456abcdef']:
            self.assertEqual((await self.preview(profile_id)).status, 404)
        reference = self.config.profile_root / 'revisions' / chosen['id'] / 'reference.wav'
        outside = self.root / 'outside.wav'; outside.write_bytes(reference.read_bytes())
        reference.unlink()
        try:
            reference.symlink_to(outside)
        except OSError:
            self.skipTest('Creating symlinks requires local permission')
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 404)
        self.assertEqual(self.worker.requests, [])

    async def test_missing_delete_support_and_router_404_never_create_temporary_voice(self):
        await self.login(); chosen = await self.stage()
        for flag in ['delete_supported', 'router_404']:
            self.worker.delete_supported = flag != 'delete_supported'
            self.worker.router_404 = flag == 'router_404'
            with self.assertLogs('scc.voice_studio', level='ERROR'):
                response = await self.preview(chosen['id'])
            self.assertEqual(response.status, 503)
        self.assertFalse(any(method == 'POST' for method, _, _ in self.worker.requests))
        self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})

    async def test_synthesis_failure_and_ambiguous_registration_response_remove_private_alias(self):
        await self.login(); chosen = await self.stage()
        for fail_at in ['speech_error', 'registration_response_lost']:
            self.worker.speech_error = fail_at == 'speech_error'
            self.worker.registration_response_lost = fail_at == 'registration_response_lost'
            with self.assertLogs('scc.voice_studio', level='ERROR'):
                response = await self.preview(chosen['id'])
            self.assertEqual(response.status, 503)
            body = await response.json()
            self.assertEqual(body['code'], 'speech_service_unavailable')
            self.assertNotIn('worker-private-details', json.dumps(body))
            self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})

    async def test_lost_successful_delete_response_is_retried_without_leaking_a_voice(self):
        await self.login(); chosen = await self.stage()
        self.worker.lost_delete_response = True
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 200)
        self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})

    async def test_persistent_cleanup_failure_is_reported_and_recovered_before_another_clone(self):
        await self.login(); chosen = await self.stage()
        self.worker.failed_final_deletes = 3
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())['code'], 'preview_cleanup_failed')
        self.assertEqual(len(self.worker.registry), 2)
        # A second request cannot create a second leaked clone while removal fails.
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())['code'], 'preview_cleanup_failed')
        self.assertEqual(len(self.worker.registry), 2)
        self.assertEqual((await self.preview(chosen['id'])).status, 200)
        self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})

    async def test_a_studio_restart_recovers_pending_private_alias_before_generating_again(self):
        await self.login(); chosen = await self.stage()
        self.worker.failed_final_deletes = 2
        response = await self.preview(chosen['id'])
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())['code'], 'preview_cleanup_failed')
        await self.client.close()
        async def idle(): return 0
        app = self.server.create_app(self.config, manager=self.manager,
            idle_check=idle, now=lambda: self.now)
        self.client = TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server(); self.addAsyncCleanup(self.client.close)
        await self.login()
        self.assertEqual((await self.preview(chosen['id'])).status, 200)
        self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})

    async def test_second_preview_activation_and_delete_stay_blocked_until_native_completion(self):
        await self.login(); chosen = await self.stage()
        self.worker.release = threading.Event()
        running = asyncio.create_task(self.preview(chosen['id']))
        self.assertTrue(await asyncio.to_thread(self.worker.entered.wait, 2))
        try:
            self.assertEqual((await self.preview(chosen['id'])).status, 409)
            self.assertEqual((await self.activate(chosen)).status, 409)
            deleting = await self.client.delete('/api/profiles/' + chosen['id'],
                json={'password': fixture.PASSWORD}, headers=self.headers)
            self.assertEqual(deleting.status, 409)
        finally:
            self.worker.release.set()
        self.assertEqual((await running).status, 200)
        self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})


class PendingPreviewRetentionTests(unittest.TestCase):
    setUp = retention_fixture.RetentionTests.setUp
    profile = retention_fixture.RetentionTests.profile
    run_cleanup = retention_fixture.RetentionTests.run_cleanup

    def pending(self, alias='scc-preview-' + 'a' * 32):
        path = self.studio / 'preview-cleanup.json'
        path.write_text(json.dumps({'schema_version': 1, 'alias': alias}))
        return path

    def online_worker(self):
        self.worker = NativeWorker(); self.addCleanup(self.worker.close)
        connection = http.client.HTTPConnection
        def redirect(host, port=None, *args, **kwargs):
            return connection(host, self.worker.http.server_port if port == 8862 else port,
                *args, **kwargs)
        patcher = patch('http.client.HTTPConnection', side_effect=redirect)
        patcher.start(); self.addCleanup(patcher.stop)
        def ownership(port):
            self.assertTrue(self.manager.locked, 'temporary clone removal must share the activation mutex')
            self.assertEqual(self.manager.selected['profile_id'], 'synthetic-scc-demo')
        self.manager.native_module = lambda: SimpleNamespace(assert_owned_listener=ownership)
        self.services = lambda: {'native_sessions':0, 'tts_running':True, 'native_running':True}

    def test_due_online_cleanup_removes_pending_clone_before_purging_owned_recordings(self):
        folder = self.profile(); journal = self.pending(); self.online_worker()
        self.worker.registry['scc-preview-' + 'a' * 32] = 'leftover-own-reference'
        result = self.run_cleanup()
        self.assertEqual(result['status'], 'purged')
        self.assertFalse(folder.exists()); self.assertFalse(journal.exists())
        self.assertEqual(self.worker.registry, {'scc-demo': 'selected-reference'})

    def test_failed_pending_clone_removal_defers_all_recording_purges(self):
        folder = self.profile(); journal = self.pending(); self.online_worker()
        self.worker.delete_supported = False
        result = self.run_cleanup()
        self.assertEqual(result['status'], 'deferred')
        self.assertTrue(folder.exists()); self.assertTrue(journal.exists())

    def test_proven_offline_cleanup_removes_only_validated_pending_identity(self):
        folder = self.profile(); journal = self.pending()
        self.manager.native_module = lambda: self.fail('Known offline worker must not receive HTTP')
        result = self.run_cleanup()
        self.assertEqual(result['status'], 'purged')
        self.assertFalse(folder.exists()); self.assertFalse(journal.exists())

    def test_corrupt_pending_identity_never_targets_selected_alias_or_purges_recordings(self):
        folder = self.profile(); journal = self.pending('scc-demo'); self.online_worker()
        result = self.run_cleanup()
        self.assertEqual(result['status'], 'deferred')
        self.assertTrue(folder.exists()); self.assertTrue(journal.exists())
        self.assertEqual(self.worker.requests, [])

    def test_due_dry_run_keeps_pending_alias_and_private_journal(self):
        folder = self.profile(); journal = self.pending(); self.online_worker()
        self.worker.registry['scc-preview-' + 'a' * 32] = 'leftover-own-reference'
        result = self.run_cleanup(False)
        self.assertEqual(result['status'], 'dry_run')
        self.assertTrue(folder.exists()); self.assertTrue(journal.exists())
        self.assertEqual(self.worker.requests, [])


if __name__ == '__main__':
    unittest.main()
