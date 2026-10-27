"""Due-date and scoped physical deletion checks; no real voices or services."""
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('scc_retention', HERE / 'retention_cleanup.py')
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)

class Manager:
    def __init__(self, root):
        self.PROFILE_ROOT = root / 'voice/voice-profile/runtime/profiles'
        self.DEFAULT_PROFILE = root / 'voice/assets/scc-demo'
        self.REGISTRATION_RECEIPT = root / 'voice/native-start/runtime/registered-voice.json'
        self.PROFILE_ROOT.mkdir(parents=True); self.DEFAULT_PROFILE.mkdir(parents=True)
        self.DEFAULT_PROFILE.joinpath('reference.wav').write_bytes(b'packaged default')
        self.selected = None; self.restored = []; self.locked = False
    def read_profile(self, folder):
        result = json.loads(Path(folder).joinpath('voice.json').read_text())
        result['profile_dir'] = str(folder)
        return result
    def selected_profile(self, root): return self.selected
    def restore_synthetic(self, root, register=None):
        profile = {'profile_id':'synthetic-scc-demo', 'kind':'designed_synthetic_voice',
                   'reference_sha256':'packaged'}
        if register: register(profile)
        self.selected = profile; self.restored.append(profile['profile_id'])
    @contextmanager
    def activation_lock(self, root):
        if self.locked: raise RuntimeError('activation busy')
        self.locked = True
        try: yield
        finally: self.locked = False

class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.manager = Manager(self.root)
        self.studio = self.root / 'voice/voice-studio/runtime'; self.studio.mkdir(parents=True)
        self.clock = datetime(2026, 10, 16, 6, 0, tzinfo=timezone.utc)
        self.states = []; self.calls = []
        self.services = lambda: {'native_sessions':0, 'tts_running':False, 'native_running':False}
    def profile(self, suffix='123456abcdef'):
        id = '20261013T120000Z-' + suffix
        folder = self.manager.PROFILE_ROOT / 'revisions' / id; folder.mkdir(parents=True)
        profile = {'schema_version':1, 'profile_id':id, 'kind':'authorized_own_voice',
                   'language':'German', 'created_at_utc':'2026-10-13T12:00:00Z',
                   'source':'desktop_microphone', 'consent':{'own_voice':True,
                    'scope':'local_synthetic_voice_and_servicenow_demo', 'confirmed_at_utc':'2026-10-13T12:00:00Z'}}
        (folder / 'voice.json').write_text(json.dumps(profile))
        (folder / 'reference.wav').write_bytes(b'fake recording')
        (folder / 'source.wav').write_bytes(b'fake source')
        return folder
    def run_cleanup(self, apply=True):
        return retention.cleanup(self.root, manager=self.manager, now=self.clock,
            apply=apply, service_check=self.services, report=False)
    def test_not_due_does_not_touch_profiles_or_services(self):
        folder = self.profile(); self.clock = datetime(2026,10,16,5,59,59,tzinfo=timezone.utc)
        self.services = lambda: self.fail('must not inspect services before deadline')
        result = self.run_cleanup(); self.assertEqual(result['status'], 'not_due')
        self.assertTrue(folder.exists()); self.assertEqual(self.manager.restored, [])
    def test_due_dry_run_plans_without_metadata_or_audio_changes(self):
        folder = self.profile(); result = self.run_cleanup(False)
        self.assertEqual(result['status'], 'dry_run'); self.assertEqual(result['profiles'], 1)
        self.assertTrue(folder.exists()); self.assertEqual(self.manager.restored, [])
    def test_offline_catchup_restores_default_and_physically_deletes_only_owned_recording(self):
        folder = self.profile(); outside = self.root / 'founder-test'; outside.mkdir()
        (outside / 'original.wav').write_bytes(b'original retained')
        preview = self.studio / retention.PREVIEW_FILES[0]; preview.write_bytes(b'test preview')
        result = self.run_cleanup(); self.assertEqual(result['status'], 'purged')
        self.assertFalse(folder.exists()); self.assertFalse(preview.exists())
        self.assertEqual(self.manager.selected['profile_id'], 'synthetic-scc-demo')
        self.assertEqual((outside / 'original.wav').read_bytes(), b'original retained')
        self.assertEqual(self.manager.DEFAULT_PROFILE.joinpath('reference.wav').read_bytes(), b'packaged default')
        self.assertEqual(self.run_cleanup()['status'], 'purged')
    def test_active_call_defers_before_restoration_or_deletion(self):
        folder = self.profile(); self.services = lambda: {'native_sessions':1, 'tts_running':True, 'native_running':True}
        result = self.run_cleanup(); self.assertEqual(result['status'], 'deferred')
        self.assertTrue(folder.exists()); self.assertEqual(self.manager.restored, [])
    def test_unknown_listener_or_service_failure_is_fail_closed(self):
        folder = self.profile()
        def fail(): raise RuntimeError('foreign listener')
        self.services = fail
        self.assertEqual(self.run_cleanup()['status'], 'deferred'); self.assertTrue(folder.exists())
    def test_symlink_never_removes_external_recording(self):
        folder = self.profile(); outside = self.root / 'protected.wav'; outside.write_bytes(b'original')
        (folder / 'source.wav').unlink()
        try:
            (folder / 'source.wav').symlink_to(outside)
        except OSError as error:
            if getattr(error, 'winerror', None) == 1314:
                self.skipTest('Windows user has no symbolic-link creation privilege; Linux guard test remains applicable')
            raise
        self.assertEqual(self.run_cleanup()['status'], 'deferred')
        self.assertEqual(outside.read_bytes(), b'original'); self.assertTrue(folder.exists())
    def test_unknown_child_file_and_nested_folder_defer_whole_sweep(self):
        folder = self.profile(); (folder / 'unrelated.txt').write_text('do not delete')
        self.assertEqual(self.run_cleanup()['status'], 'deferred'); self.assertTrue(folder.exists())
    def test_failed_default_registration_keeps_all_recordings(self):
        folder = self.profile(); self.services = lambda: {'native_sessions':0, 'tts_running':True, 'native_running':True}
        def fail(*a, **kw): raise RuntimeError('TTS failed')
        self.manager.restore_synthetic = fail
        self.assertEqual(self.run_cleanup()['status'], 'deferred'); self.assertTrue(folder.exists())
    def test_service_state_is_rechecked_after_default_registration(self):
        folder = self.profile(); checks = iter([{'native_sessions':0,'tts_running':False,'native_running':False},
                                              {'native_sessions':1,'tts_running':True,'native_running':True}])
        self.services = lambda: next(checks)
        self.assertEqual(self.run_cleanup()['status'], 'deferred'); self.assertTrue(folder.exists())
    def test_post_deadline_revision_is_preserved(self):
        folder = self.profile(); meta = json.loads((folder/'voice.json').read_text())
        meta['created_at_utc'] = '2026-10-17T12:00:00Z'; (folder/'voice.json').write_text(json.dumps(meta))
        self.assertEqual(self.run_cleanup()['status'], 'deferred'); self.assertTrue(folder.exists())
    def test_partial_old_delete_quarantine_is_physically_purged_from_matching_private_journal(self):
        folder = self.profile(); token = 'a' * 32
        quarantine = self.studio / 'delete-quarantine'; quarantine.mkdir()
        folder.rename(quarantine / (folder.name + '-' + token))
        moved = quarantine / (folder.name + '-' + token)
        (moved / 'reference.wav').unlink(); (moved / 'voice.json').unlink()
        journal = self.studio / 'delete-journal'; journal.mkdir()
        (journal / (token + '.json')).write_text(json.dumps({'schema_version':1,
            'profile_id':folder.name, 'quarantine_name':moved.name, 'requested_by':'personal-123456abcdefabcd',
            'created_at_utc':'2026-10-13T12:00:00Z', 'status':'purge_failed'}))
        result = self.run_cleanup(); self.assertEqual(result['status'], 'purged')
        self.assertFalse(moved.exists()); self.assertFalse((journal/(token+'.json')).exists())
    def test_failed_physical_purge_keeps_private_retry_journal_and_next_run_finishes(self):
        folder = self.profile()
        from unittest.mock import patch
        with patch.object(retention, 'purge_tree', side_effect=OSError('file locked')):
            result = self.run_cleanup()
        self.assertEqual(result['status'], 'deferred')
        self.assertFalse(folder.exists())
        self.assertEqual(len(list((self.studio / 'delete-journal').glob('*.json'))), 1)
        result = self.run_cleanup(); self.assertEqual(result['status'], 'purged')
        self.assertEqual(list((self.studio / 'delete-quarantine').iterdir()), [])
    def test_crashed_manager_staging_audio_is_removed(self):
        staging = self.manager.PROFILE_ROOT / 'revisions/.staging-abcdefgh'
        staging.mkdir(parents=True); (staging/'source.wav').write_bytes(b'staged source')
        self.assertEqual(self.run_cleanup()['status'], 'purged'); self.assertFalse(staging.exists())
    def test_symlink_packaged_default_defers_without_touching_external_voice(self):
        folder = self.profile(); source = self.manager.DEFAULT_PROFILE
        external = self.root/'external-default'; source.rename(external)
        try:
            source.symlink_to(external, target_is_directory=True)
        except OSError as error:
            if getattr(error, 'winerror', None) == 1314:
                self.skipTest('Windows user has no symbolic-link creation privilege; Linux guard test remains applicable')
            raise
        self.assertEqual(self.run_cleanup()['status'], 'deferred')
        self.assertTrue(folder.exists()); self.assertEqual(self.manager.restored, [])
    def test_unknown_staging_contents_are_preserved(self):
        staging = self.manager.PROFILE_ROOT / 'revisions/.staging-abcdefgh'
        staging.mkdir(parents=True); (staging/'unrelated.txt').write_bytes(b'preserve')
        self.assertEqual(self.run_cleanup()['status'], 'deferred'); self.assertTrue(staging.exists())
    def test_startup_does_not_run_cleanup_before_deadline(self):
        from unittest.mock import patch
        launcher = retention.module('scc_retention_launcher_test', HERE / 'launch_studio.py')
        with patch.object(launcher, 'RUNTIME', self.studio), patch.object(launcher.subprocess, 'run', side_effect=AssertionError('must not launch')):
            with patch.object(retention, 'due', return_value=False):
                # Inject one loaded helper through the import hook.
                with patch.object(launcher.importlib.util, 'module_from_spec', return_value=retention):
                    with patch.object(launcher.importlib.util, 'spec_from_file_location') as factory:
                        factory.return_value.name = 'test-helper'; factory.return_value.loader.exec_module = lambda mod: None
                        self.assertEqual(launcher.retention_catchup()['status'], 'not_due')
    def test_startup_after_deadline_runs_only_due_helper_and_reports_deferral(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        launcher = retention.module('scc_retention_launcher_test2', HERE / 'launch_studio.py')
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(stdout=b'{"status":"deferred","reason":"call_active_or_status_invalid"}')
        with patch.object(launcher, 'RUNTIME', self.studio), patch.object(retention, 'due', return_value=True), patch.object(launcher.subprocess, 'run', side_effect=run):
            with patch.object(launcher.importlib.util, 'module_from_spec', return_value=retention):
                with patch.object(launcher.importlib.util, 'spec_from_file_location') as factory:
                    factory.return_value.name = 'test-helper'; factory.return_value.loader.exec_module = lambda mod: None
                    result = launcher.retention_catchup()
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(calls[0][2:], [str(HERE / 'retention_cleanup.py'), '--apply'])
    def test_service_native_health_uses_live_camel_case_contract(self):
        self.assertEqual(retention.native_sessions({'nativeSessions':0,'authMode':'servicenow','status':'ok'}), 0)
        with self.assertRaises(retention.Deferred):
            retention.native_sessions({'nativeSessions':0,'auth_mode':'servicenow','status':'ok'})
        with self.assertRaises(retention.Deferred):
            retention.native_sessions({'nativeSessions':False,'authMode':'servicenow','status':'ok'})
    def test_service_command_derives_python_from_actual_owned_launcher(self):
        from types import SimpleNamespace
        owner = SimpleNamespace(PYTHON=Path('approved-other-env/python.exe'),
             NATIVE=self.root / 'voice/native-bridge', ROOT=self.root)
        args = retention.native_arguments(owner, self.root)
        self.assertEqual(args[0], str(owner.PYTHON))
        self.assertEqual(args[1:], ['-u', str(owner.NATIVE / 'native_bridge.py'),
             '--config', str(owner.NATIVE / 'config.example.json')])
    def test_utc_boundary_is_berlin_eight_am_on_october_sixteenth(self):
        self.assertEqual(retention.DUE_UTC.isoformat(), '2026-10-16T06:00:00+00:00')

if __name__ == '__main__': unittest.main()
