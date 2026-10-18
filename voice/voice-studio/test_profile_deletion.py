"""Identity, ownership and permanent deletion exercised through real HTTP/storage."""
import asyncio
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer
import test_studio_server as fixture


class PersonalCodeDeletionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.VoiceStudioHTTPTests.asyncSetUp
    upload = fixture.VoiceStudioHTTPTests.upload
    stage = fixture.VoiceStudioHTTPTests.stage
    activate = fixture.VoiceStudioHTTPTests.activate

    async def login_as(self, password):
        response = await self.client.post('/api/login', json={'password': password},
            headers={'Origin': fixture.ORIGIN})
        self.assertEqual(response.status, 200, await response.text())
        body = await response.json()
        self.headers = {'Origin': fixture.ORIGIN, 'X-CSRF-Token': body['csrf'],
            'Cookie': self.server.COOKIE_NAME + '=' + response.cookies[self.server.COOKIE_NAME].value}
        return body

    async def personal(self, label='Eigener Zugang'):
        await self.login_as(fixture.PASSWORD)
        response = await self.client.post('/api/access-codes', json={'label': label}, headers=self.headers)
        self.assertEqual(response.status, 201, await response.text())
        return await response.json()

    async def delete(self, profile, password, headers=None):
        return await self.client.delete('/api/profiles/' + profile['id'],
            json={'password': password}, headers=headers or self.headers)

    async def listed(self):
        response = await self.client.get('/api/profiles', headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        return (await response.json())['profiles']

    async def test_admin_pin_stays_unchanged_and_personal_secret_is_shown_only_once(self):
        original = self.config.auth_file.read_bytes()
        created = await self.personal()
        self.assertGreaterEqual(len(created['code']), 12)
        self.assertEqual(self.config.auth_file.read_bytes(), original)
        response = await self.client.get('/api/access-codes', headers=self.headers)
        self.assertEqual(response.status, 200)
        public = await response.json()
        self.assertEqual(public['access_codes'][0]['id'], created['access_code']['id'])
        self.assertNotIn(created['code'], json.dumps(public))
        self.assertNotIn('digest', json.dumps(public)); self.assertNotIn('salt', json.dumps(public))
        for file in self.config.runtime.rglob('*'):
            if file.is_file():
                self.assertNotIn(created['code'].encode(), file.read_bytes())
        admin = await self.login_as(fixture.PASSWORD)
        self.assertTrue(admin['is_admin'])
        self.assertEqual(admin['principal_id'], 'administrator')

    async def test_personal_identity_and_owned_profile_permissions_survive_restart(self):
        created = await self.personal()
        identity = await self.login_as(created['code'])
        self.assertFalse(identity['is_admin'])
        self.assertEqual(identity['principal_id'], created['access_code']['id'])
        profile = await self.stage()
        async def idle(): return 0
        restarted = self.server.create_app(self.config, manager=self.manager, idle_check=idle,
            register=lambda profile: None, synthesize=lambda text: b'\0\0' * 24000)
        self.client = TestClient(TestServer(restarted), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server(); self.addAsyncCleanup(self.client.close)
        again = await self.login_as(created['code'])
        self.assertEqual(again['principal_id'], identity['principal_id'])
        owned = next(value for value in await self.listed() if value['id'] == profile['id'])
        self.assertTrue(owned['owner_is_self']); self.assertTrue(owned['can_delete'])

    async def test_personal_code_cannot_provision_or_list_other_codes(self):
        created = await self.personal(); await self.login_as(created['code'])
        for method in ('GET', 'POST'):
            response = await self.client.request(method, '/api/access-codes',
                json={} if method == 'POST' else None, headers=self.headers)
            self.assertEqual(response.status, 403)

    async def test_upload_owner_fields_are_ignored_and_other_personal_owner_cannot_delete(self):
        first = await self.personal('Erster Zugang'); second = await self.personal('Zweiter Zugang')
        await self.login_as(first['code'])
        data = self.upload(); data.update(owner_id=second['access_code']['id'],
            principal_id='administrator', is_admin=True, ownership={'principal_id':'administrator'})
        response = await self.client.post('/api/profiles', json=data, headers=self.headers)
        self.assertEqual(response.status, 201)
        profile = (await response.json())['profile']
        self.assertTrue(profile['owner_is_self']); self.assertTrue(profile['can_delete'])
        await self.login_as(second['code'])
        other = next(value for value in await self.listed() if value['id'] == profile['id'])
        self.assertFalse(other['owner_is_self']); self.assertFalse(other['can_delete'])
        self.assertEqual((await self.delete(profile, second['code'])).status, 403)
        self.assertTrue((self.config.profile_root / 'revisions' / profile['id']).is_dir())

    async def test_owner_deletion_physically_purges_audio_and_removes_all_public_endpoints(self):
        created = await self.personal(); await self.login_as(created['code']); profile = await self.stage()
        self.assertEqual((await self.delete(profile, created['code'])).status, 200)
        self.assertFalse((self.config.profile_root / 'revisions' / profile['id']).exists())
        self.assertNotIn(profile['id'], [value['id'] for value in await self.listed()])
        self.assertEqual((await self.client.get('/api/profiles/' + profile['id'] + '/audio',
            headers=self.headers)).status, 404)
        self.assertEqual((await self.activate(profile)).status, 404)
        self.assertEqual((await self.delete(profile, created['code'])).status, 404)
        self.assertEqual(list(self.root.rglob('*.wav')), [])
        self.assertEqual(self.registered, [])

    async def test_admin_can_delete_any_personal_owned_revision(self):
        created = await self.personal(); await self.login_as(created['code']); profile = await self.stage()
        await self.login_as(fixture.PASSWORD)
        visible = next(value for value in await self.listed() if value['id'] == profile['id'])
        self.assertTrue(visible['can_delete']); self.assertFalse(visible['owner_is_self'])
        self.assertEqual((await self.delete(profile, fixture.PASSWORD)).status, 200)

    async def test_valid_admin_override_authorizes_deletion_in_personal_session(self):
        first = await self.personal(); second = await self.personal('Anderer Zugang')
        await self.login_as(first['code']); profile = await self.stage()
        await self.login_as(second['code'])
        self.assertEqual((await self.delete(profile, fixture.PASSWORD)).status, 200)

    async def test_legacy_profile_is_admin_owned_and_personal_code_cannot_delete_it(self):
        created = await self.personal()
        source = self.root / 'legacy.wav'; source.write_bytes(fixture.wav_bytes())
        request = self.upload(); request['wav_path'] = str(source)
        legacy = self.manager.stage(request, self.config.profile_root)
        profile = {'id': legacy['profile_id']}
        await self.login_as(created['code'])
        entry = next(value for value in await self.listed() if value['id'] == profile['id'])
        self.assertFalse(entry['can_delete']); self.assertFalse(entry['owner_is_self'])
        self.assertEqual((await self.delete(profile, created['code'])).status, 403)
        await self.login_as(fixture.PASSWORD)
        self.assertEqual((await self.delete(profile, fixture.PASSWORD)).status, 200)

    async def test_wrong_or_different_personal_code_cannot_confirm_deletion(self):
        first = await self.personal(); second = await self.personal('Anderer Zugang')
        await self.login_as(first['code']); profile = await self.stage()
        for password in ('wrong-code', second['code']):
            response = await self.delete(profile, password)
            self.assertEqual(response.status, 403)
            self.assertTrue((self.config.profile_root / 'revisions' / profile['id']).exists())

    async def test_delete_requires_session_exact_origin_and_csrf(self):
        await self.login_as(fixture.PASSWORD); profile = await self.stage()
        unauthenticated = {'Origin': fixture.ORIGIN}
        self.assertEqual((await self.delete(profile, fixture.PASSWORD, unauthenticated)).status, 401)
        for field, value in [('Origin','https://evil.example'), ('X-CSRF-Token','wrong')]:
            headers = dict(self.headers); headers[field] = value
            self.assertEqual((await self.delete(profile, fixture.PASSWORD, headers)).status, 403)
        self.assertTrue((self.config.profile_root / 'revisions' / profile['id']).exists())

    async def test_selected_profile_deletion_is_blocked_and_pointer_unchanged(self):
        created = await self.personal(); await self.login_as(created['code']); profile = await self.stage()
        self.assertEqual((await self.activate(profile)).status, 200)
        pointer = (self.config.profile_root / 'active.json').read_bytes()
        response = await self.delete(profile, created['code'])
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'selected_voice_protected')
        self.assertEqual((self.config.profile_root / 'active.json').read_bytes(), pointer)
        entry = next(value for value in await self.listed() if value['id'] == profile['id'])
        self.assertTrue(entry['can_delete']); self.assertTrue(entry['selected'])

    async def test_packaged_synthetic_profile_is_never_deletable(self):
        await self.login_as(fixture.PASSWORD); profile = await self.stage()
        folder = self.config.profile_root / 'revisions' / profile['id']
        metadata = json.loads((folder / 'voice.json').read_text())
        metadata.update(profile_id='synthetic-scc-demo', kind='designed_synthetic_voice')
        (folder / 'voice.json').write_text(json.dumps(metadata))
        folder.rename(self.manager.DEFAULT_PROFILE)
        response = await self.delete({'id':'synthetic-scc-demo'}, fixture.PASSWORD)
        self.assertEqual(response.status, 403)
        self.assertTrue(self.manager.DEFAULT_PROFILE.is_dir())

    async def test_active_call_blocks_deletion(self):
        await self.login_as(fixture.PASSWORD); profile = await self.stage(); self.live_sessions = 1
        response = await self.delete(profile, fixture.PASSWORD)
        self.assertEqual(response.status, 409)
        self.assertEqual((await response.json())['code'], 'call_in_progress')
        self.assertTrue((self.config.profile_root / 'revisions' / profile['id']).exists())

    async def test_activation_race_blocks_deletion_of_inactive_profile(self):
        await self.login_as(fixture.PASSWORD); first = await self.stage(); second = await self.stage('Zweite')
        self.register_release = threading.Event()
        task = asyncio.create_task(self.activate(first))
        await asyncio.to_thread(self.register_entered.wait, 2)
        try:
            self.assertEqual((await self.delete(second, fixture.PASSWORD)).status, 409)
        finally:
            self.register_release.set()
        self.assertEqual((await task).status, 200)
        self.assertTrue((self.config.profile_root / 'revisions' / second['id']).exists())

    async def test_external_manager_activation_lock_also_blocks_deletion(self):
        await self.login_as(fixture.PASSWORD); profile = await self.stage()
        with self.manager.activation_lock(self.config.profile_root):
            response = await self.delete(profile, fixture.PASSWORD)
        self.assertEqual(response.status, 409)
        self.assertTrue((self.config.profile_root / 'revisions' / profile['id']).exists())

    async def test_symlink_inside_revision_never_moves_or_deletes_external_audio(self):
        await self.login_as(fixture.PASSWORD); profile = await self.stage()
        outside = self.root / 'external.wav'; outside.write_bytes(fixture.wav_bytes())
        source = self.config.profile_root / 'revisions' / profile['id'] / 'source.wav'
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError:
            self.skipTest('Symlink creation is unavailable on this test host')
        response = await self.delete(profile, fixture.PASSWORD)
        self.assertEqual(response.status, 403)
        self.assertEqual(outside.read_bytes(), fixture.wav_bytes())
        self.assertTrue(source.is_symlink())

    async def test_failed_purge_is_not_success_and_quarantine_is_private_and_tracked(self):
        await self.login_as(fixture.PASSWORD); profile = await self.stage()
        with patch.object(self.server, 'purge_quarantined_revision', side_effect=OSError('file locked')):
            response = await self.delete(profile, fixture.PASSWORD)
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())['code'], 'delete_purge_failed')
        self.assertNotIn(profile['id'], [value['id'] for value in await self.listed()])
        self.assertTrue(list((self.config.runtime / 'delete-quarantine').rglob('*.wav')))
        journals = list((self.config.runtime / 'delete-journal').glob('*.json'))
        self.assertTrue(any(json.loads(path.read_text())['status'] == 'purge_failed' for path in journals))
        self.assertEqual((await self.client.get('/runtime/delete-quarantine/', headers=self.headers)).status, 404)

    async def test_ownership_write_failure_does_not_publish_unowned_profile(self):
        created = await self.personal(); await self.login_as(created['code'])
        with patch.object(self.server, 'atomic_private_json', side_effect=OSError('disk full')):
            with self.assertLogs('scc.voice_studio', level='ERROR'):
                response = await self.client.post('/api/profiles', json=self.upload(), headers=self.headers)
        self.assertEqual(response.status, 503)
        self.assertEqual(await self.listed(), [])
        self.assertEqual(list(self.root.rglob('*.wav')), [])

    async def test_personal_code_store_write_failure_does_not_create_a_login_identity(self):
        await self.login_as(fixture.PASSWORD)
        with patch.object(self.server, 'atomic_private_json', side_effect=OSError('disk full')):
            with self.assertLogs('scc.voice_studio', level='ERROR'):
                response = await self.client.post('/api/access-codes', json={'label':'Fail'}, headers=self.headers)
        self.assertEqual(response.status, 503)
        response = await self.client.get('/api/access-codes', headers=self.headers)
        self.assertEqual((await response.json())['access_codes'], [])

    async def test_successful_deletes_retain_neither_audio_nor_pending_journals(self):
        await self.login_as(fixture.PASSWORD)
        for _ in range(3):
            profile = await self.stage()
            self.assertEqual((await self.delete(profile, fixture.PASSWORD)).status, 200)
        self.assertEqual(list((self.config.runtime / 'delete-journal').glob('*.json')), [])
        self.assertEqual(list((self.config.runtime / 'delete-quarantine').iterdir()), [])

    async def test_failed_atomic_move_keeps_visible_profile_and_removes_pending_journal(self):
        await self.login_as(fixture.PASSWORD); profile = await self.stage()
        with patch.object(Path, 'rename', side_effect=OSError('move rejected')):
            with self.assertLogs('scc.voice_studio', level='ERROR'):
                response = await self.delete(profile, fixture.PASSWORD)
        self.assertEqual(response.status, 503)
        self.assertIn(profile['id'], [value['id'] for value in await self.listed()])
        self.assertEqual(list((self.config.runtime / 'delete-journal').glob('*.json')), [])

    async def test_full_failed_delete_journal_blocks_new_move_before_audio_changes(self):
        await self.login_as(fixture.PASSWORD); profile = await self.stage()
        journal = self.config.runtime / 'delete-journal'; journal.mkdir()
        for index in range(self.server.MAX_FAILED_PURGES):
            (journal / (str(index) + '.json')).write_text('{}')
        response = await self.delete(profile, fixture.PASSWORD)
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())['code'], 'delete_quarantine_full')
        self.assertTrue((self.config.profile_root / 'revisions' / profile['id']).exists())
        self.assertEqual(len(list(journal.iterdir())), self.server.MAX_FAILED_PURGES)

    async def test_private_atomic_metadata_failure_preserves_previous_complete_file(self):
        target = self.config.runtime / 'existing.json'; target.write_text('{"previous":true}')
        def partial(value, handle, **kwargs):
            handle.write('{"partial":'); raise OSError('write failure')
        with patch.object(self.server.json, 'dump', side_effect=partial):
            with self.assertRaises(OSError):
                self.server.atomic_private_json(target, {'next': True})
        self.assertEqual(target.read_text(), '{"previous":true}')
        self.assertEqual(list(self.config.runtime.glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
