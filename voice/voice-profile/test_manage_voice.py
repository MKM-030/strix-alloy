import array
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave


class VoiceManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.wav = self.root / 'input.wav'
        self.write_audio()
        self.request = {'wav_path': str(self.wav), 'reference_text': 'Guten Tag. Ich helfe Ihnen.',
            'name': 'Marcel', 'language': 'German', 'source': 'desktop_microphone',
            'consent': {'own_voice': True, 'confirmed_at_utc': '2026-10-13T00:00:00Z',
                        'scope': 'local_synthetic_voice_and_servicenow_demo'}}

    def write_audio(self, amplitude=5000):
        samples = array.array('h', [int(amplitude * math.sin(i / 17)) for i in range(24000 * 4)])
        with wave.open(str(self.wav), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(samples.tobytes())

    def helper(self):
        path = Path(__file__).with_name('manage_voice.py')
        self.assertTrue(path.is_file(), 'Own-voice management helper must exist')
        spec = importlib.util.spec_from_file_location('manage_voice', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def stage(self):
        return self.helper().stage(self.request, self.root / 'profiles')

    def test_consent_is_required_before_creating_a_revision(self):
        self.request['consent']['own_voice'] = False
        with self.assertRaisesRegex(ValueError, 'consent'):
            self.stage()
        self.assertFalse((self.root / 'profiles').exists())

    def test_silent_reference_is_rejected(self):
        self.write_audio(amplitude=0)
        with self.assertRaisesRegex(ValueError, 'silent'):
            self.stage()

    def test_truncated_wave_header_cannot_pass_the_duration_check(self):
        with self.wav.open('r+b') as handle:
            handle.truncate(44 + 24000 * 2)
        with self.assertRaisesRegex(ValueError, 'truncated'):
            self.stage()

    def test_registration_invalidates_receipt_before_a_possibly_ambiguous_post(self):
        helper = self.helper(); profile = self.stage()
        self.assertTrue(hasattr(helper, 'REGISTRATION_RECEIPT'), 'Registration must invalidate startup receipt')
        receipt = self.root / 'registered-voice.json'; receipt.write_text('{"old":"voice"}')
        from types import SimpleNamespace
        def request(*args, **kwargs):
            self.assertFalse(receipt.exists(), 'An ambiguous POST must not leave a reusable receipt')
            raise TimeoutError('response lost')
        native = SimpleNamespace(assert_owned_listener=lambda port: None, request=request,
            ProbeHTTPError=helper.RegistrationRejected, ProbePreflightError=ValueError,
            ProbeListenerNotReady=FileNotFoundError)
        fake_psutil = SimpleNamespace(virtual_memory=lambda: SimpleNamespace(available=50 * 1024**3))
        with patch.object(helper, 'native_module', return_value=native), patch.object(helper, 'REGISTRATION_RECEIPT', receipt), patch.dict('sys.modules', {'psutil': fake_psutil}):
            with self.assertRaises(TimeoutError):
                helper.native_register(profile)
        self.assertFalse(receipt.exists())

    def test_repeated_request_preflight_is_rejected_before_http(self):
        helper = self.helper(); profile = self.stage()
        from types import SimpleNamespace
        class PreflightError(RuntimeError): pass
        def rejected_request(*args, **kwargs): raise PreflightError('owner changed before HTTP')
        native = SimpleNamespace(assert_owned_listener=lambda port: None, request=rejected_request,
            ProbeHTTPError=helper.RegistrationRejected, ProbePreflightError=PreflightError,
            ProbeListenerNotReady=FileNotFoundError)
        fake_psutil = SimpleNamespace(virtual_memory=lambda: SimpleNamespace(available=50*1024**3))
        with patch.object(helper, 'native_module', return_value=native), patch.object(helper, 'REGISTRATION_RECEIPT', self.root/'receipt.json'), patch.dict('sys.modules', {'psutil': fake_psutil}):
            with self.assertRaises(helper.RegistrationRejected):
                helper.native_register(profile)

    def test_repeated_not_ready_listener_is_rejected_before_http(self):
        helper = self.helper(); profile = self.stage()
        from types import SimpleNamespace
        class ListenerNotReady(OSError): pass
        def rejected_request(*args, **kwargs): raise ListenerNotReady('not listening before HTTP')
        native = SimpleNamespace(assert_owned_listener=lambda port: None, request=rejected_request,
            ProbeHTTPError=helper.RegistrationRejected, ProbePreflightError=ValueError,
            ProbeListenerNotReady=ListenerNotReady)
        fake_psutil = SimpleNamespace(virtual_memory=lambda: SimpleNamespace(available=50*1024**3))
        with patch.object(helper, 'native_module', return_value=native), patch.object(helper, 'REGISTRATION_RECEIPT', self.root/'receipt.json'), patch.dict('sys.modules', {'psutil': fake_psutil}):
            with self.assertRaises(helper.RegistrationRejected):
                helper.native_register(profile)

    def test_missing_owner_check_dependency_is_a_preflight_rejection(self):
        helper = self.helper(); profile = self.stage()
        with patch.object(helper, 'native_module', side_effect=ModuleNotFoundError('psutil')):
            with self.assertRaises(helper.RegistrationRejected):
                helper.native_register(profile)

    def test_stage_is_immutable_and_does_not_select_the_voice(self):
        profile = self.stage()
        saved = Path(profile['profile_dir'])
        self.assertEqual((saved / 'reference.wav').read_bytes(), self.wav.read_bytes())
        self.assertEqual(json.loads((saved / 'voice.json').read_text())['reference_text'], self.request['reference_text'])
        self.assertFalse((self.root / 'profiles' / 'active.json').exists())

    def test_tampered_reference_is_rejected_before_server_mutation(self):
        helper = self.helper(); profile = helper.stage(self.request, self.root / 'profiles')
        (Path(profile['profile_dir']) / 'reference.wav').write_bytes(b'changed')
        calls = []
        with self.assertRaisesRegex(ValueError, 'hash'):
            helper.activate(profile['profile_dir'], self.root / 'profiles', lambda p: calls.append(p))
        self.assertEqual(calls, [])

    def test_failed_registration_preserves_the_previous_pointer(self):
        helper = self.helper(); folder = self.root / 'profiles'
        first = helper.stage(self.request, folder); second = helper.stage(dict(self.request, name='New'), folder)
        helper.activate(first['profile_dir'], folder, lambda p: None)
        previous = (folder / 'active.json').read_bytes()
        def rejected(profile):
            raise helper.RegistrationRejected('invalid reference')
        with self.assertRaises(helper.RegistrationRejected):
            helper.activate(second['profile_dir'], folder, rejected)
        self.assertEqual((folder / 'active.json').read_bytes(), previous)

    def test_failed_pointer_write_restores_previous_registry_voice(self):
        helper = self.helper(); folder = self.root / 'profiles'; registered = []
        first = helper.stage(self.request, folder); second = helper.stage(dict(self.request, name='New'), folder)
        helper.activate(first['profile_dir'], folder, lambda p: registered.append(p['profile_id']))
        previous = (folder / 'active.json').read_bytes()
        with patch.object(helper, 'atomic_json', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(RuntimeError, 'restored'):
                helper.activate(second['profile_dir'], folder, lambda p: registered.append(p['profile_id']))
        self.assertEqual(registered[-1], first['profile_id'])
        self.assertEqual((folder / 'active.json').read_bytes(), previous)

    def test_ambiguous_transport_error_restores_previous_registry_voice(self):
        helper = self.helper(); folder = self.root / 'profiles'; registered = []
        first = helper.stage(self.request, folder); second = helper.stage(dict(self.request, name='New'), folder)
        helper.activate(first['profile_dir'], folder, lambda p: None)
        def transport(profile):
            registered.append(profile['profile_id'])
            if profile['profile_id'] == second['profile_id']:
                raise TimeoutError('response lost')
        with self.assertRaisesRegex(RuntimeError, 'restored'):
            helper.activate(second['profile_dir'], folder, transport)
        self.assertEqual(registered[-1], first['profile_id'])
        self.assertEqual(helper.selected_profile(folder)['profile_id'], first['profile_id'])

    def test_successful_activation_returns_previous_identity_and_persists_selection(self):
        helper = self.helper(); folder = self.root / 'profiles'
        first = helper.stage(self.request, folder); second = helper.stage(dict(self.request, name='New'), folder)
        helper.activate(first['profile_dir'], folder, lambda p: None)
        result = helper.activate(second['profile_dir'], folder, lambda p: None)
        self.assertEqual(result['previous_profile_id'], first['profile_id'])
        self.assertEqual(helper.selected_profile(folder)['profile_id'], second['profile_id'])
        self.assertEqual(result['active_voice'], 'scc-demo')

    def test_ambiguous_synthetic_restore_rolls_back_to_selected_own_voice(self):
        helper = self.helper()
        self.assertTrue(hasattr(helper, 'restore_synthetic'), 'Synthetic recovery must use the transaction helper')
        folder = self.root / 'profiles'
        own = helper.stage(self.request, folder)
        helper.activate(own['profile_dir'], folder, lambda p: None)
        synthetic = self.root / 'synthetic'; synthetic.mkdir()
        (synthetic / 'reference.wav').write_bytes(b'synthetic-source')
        import hashlib
        (synthetic / 'voice.json').write_text(json.dumps({'schema_version': 1, 'kind': 'designed_synthetic_voice',
            'name': 'Synthetic', 'language': 'German', 'reference_text': 'Guten Tag.',
            'reference_sha256': hashlib.sha256(b'synthetic-source').hexdigest()}))
        registered = []
        def transport(profile):
            registered.append(profile['profile_id'])
            if profile['profile_id'] == 'synthetic-scc-demo':
                raise TimeoutError('response lost')
        with patch.object(helper, 'DEFAULT_PROFILE', synthetic):
            with self.assertRaisesRegex(RuntimeError, 'restored'):
                helper.restore_synthetic(folder, transport)
        self.assertEqual(registered[-1], own['profile_id'])
        self.assertEqual(helper.selected_profile(folder)['profile_id'], own['profile_id'])


if __name__ == '__main__':
    unittest.main()
