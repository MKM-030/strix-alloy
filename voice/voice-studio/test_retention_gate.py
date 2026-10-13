"""The fair deadline blocks new private recordings without touching good voices."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from unittest.mock import patch
import unittest

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer
import test_studio_server as fixture

DUE = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)
BEFORE = datetime(2026, 10, 16, 5, 59, tzinfo=timezone.utc)


class RetentionGateTests(unittest.IsolatedAsyncioTestCase):
    login = fixture.VoiceStudioHTTPTests.login
    upload = fixture.VoiceStudioHTTPTests.upload
    stage = fixture.VoiceStudioHTTPTests.stage
    activate = fixture.VoiceStudioHTTPTests.activate

    async def asyncSetUp(self):
        await fixture.VoiceStudioHTTPTests.asyncSetUp(self)
        self.now = BEFORE
        async def idle(): return self.live_sessions
        def register(profile):
            self.registered.append(profile['profile_id'])
            return {'status': 200}
        app = self.server.create_app(self.config, manager=self.manager, idle_check=idle,
            register=register, now=lambda: self.now)
        self.client = TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server(); self.addAsyncCleanup(self.client.close)
        await self.login()

    async def test_shared_policy_exposes_correct_utc_deadline_and_recording_permission(self):
        response = await self.client.get('/api/session', headers=self.headers)
        session = await response.json()
        self.assertEqual(session['retention_due_at_utc'], '2026-10-16T06:00:00Z')
        self.assertTrue(session['recording_allowed'])
        profile = await self.stage()
        self.assertTrue((self.config.profile_root / 'revisions' / profile['id']).exists())
        self.now = DUE
        session = await (await self.client.get('/api/session', headers=self.headers)).json()
        self.assertFalse(session['recording_allowed'])

    async def test_new_upload_is_rejected_at_deadline_before_recording_is_written(self):
        self.now = DUE
        response = await self.client.post('/api/profiles', json=self.upload(), headers=self.headers)
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'fair_retention_expired')
        self.assertEqual(list(self.root.rglob('*.wav')), [])

    async def test_upload_crossing_deadline_never_publishes_profile_after_cleanup_lock(self):
        original_stage = self.manager.stage
        def crossing(*args, **kwargs):
            result = original_stage(*args, **kwargs)
            self.now = DUE
            return result
        with patch.object(self.manager, 'stage', side_effect=crossing):
            response = await self.client.post('/api/profiles', json=self.upload(), headers=self.headers)
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'fair_retention_expired')
        self.assertEqual(list(self.root.rglob('*.wav')), [])
        self.assertFalse((self.config.profile_root / 'active.json').exists())

    async def test_nondefault_activation_after_deadline_never_calls_native_registry(self):
        profile = await self.stage(); self.now = DUE
        response = await self.activate(profile)
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'fair_retention_expired')
        self.assertEqual(self.registered, [])
        self.assertFalse((self.config.profile_root / 'active.json').exists())

    async def test_activation_crossing_manager_lock_deadline_is_rejected_without_rollback_calls(self):
        profile = await self.stage(); original_lock = self.manager.activation_lock
        @contextmanager
        def crossing(root):
            with original_lock(root):
                self.now = DUE
                yield
        with patch.object(self.manager, 'activation_lock', side_effect=crossing):
            response = await self.activate(profile)
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'fair_retention_expired')
        self.assertEqual(self.registered, [])
        self.assertFalse((self.config.profile_root / 'active.json').exists())

    async def test_ambiguous_registration_across_deadline_still_restores_prior_voice(self):
        first = await self.stage(); second = await self.stage('Zweite Stimme')
        self.assertEqual((await self.activate(first)).status, 200)
        pointer = (self.config.profile_root / 'active.json').read_bytes()
        async def idle(): return 0
        def register(profile):
            self.registered.append(profile['profile_id'])
            if profile['profile_id'] == second['id']:
                self.now = DUE
                raise TimeoutError('response lost after native registration')
        app = self.server.create_app(self.config, manager=self.manager, idle_check=idle,
            register=register, now=lambda: self.now)
        self.client = TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server(); self.addAsyncCleanup(self.client.close)
        await self.login()
        with self.assertLogs('scc.voice_studio', level='ERROR'):
            response = await self.activate(second)
        self.assertEqual(response.status, 503)
        self.assertEqual(self.registered[-2:], [second['id'], first['id']])
        self.assertEqual((self.config.profile_root / 'active.json').read_bytes(), pointer)

    async def test_list_and_permanent_delete_remain_available_after_deadline(self):
        profile = await self.stage(); self.now = DUE
        listed = await self.client.get('/api/profiles', headers=self.headers)
        self.assertEqual(listed.status, 200)
        self.assertEqual((await listed.json())['profiles'][0]['id'], profile['id'])
        response = await self.client.delete('/api/profiles/' + profile['id'],
            json={'password': fixture.PASSWORD}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertFalse((self.config.profile_root / 'revisions' / profile['id']).exists())

    async def test_packaged_default_activation_and_account_creation_remain_available_after_deadline(self):
        profile = await self.stage()
        folder = self.config.profile_root / 'revisions' / profile['id']
        data = json.loads((folder / 'voice.json').read_text())
        data.update(profile_id='synthetic-scc-demo', kind='designed_synthetic_voice')
        (folder / 'voice.json').write_text(json.dumps(data))
        folder.rename(self.manager.DEFAULT_PROFILE)
        self.now = DUE
        response = await self.activate({'id':'synthetic-scc-demo'})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.registered, ['synthetic-scc-demo'])
        response = await self.client.post('/api/access-codes', json={'label':'Bleibender Zugang'}, headers=self.headers)
        self.assertEqual(response.status, 201)


if __name__ == '__main__':
    unittest.main()
