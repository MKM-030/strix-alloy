"""Offline explicit ServiceNow UUID bindings; no worker or model calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

VOICE_ID = '81959ffa-c2ef-4db5-bf95-5df2a24c9404'


class NativeVoiceBindingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'profiles'
        spec = importlib.util.spec_from_file_location('binding_manager', Path(__file__).with_name('manage_voice.py'))
        self.manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.manager)
        self.profile = self.make_profile('first-profile', b'first-local-reference')

    def make_profile(self, name, audio):
        folder = self.root / 'revisions' / name
        folder.mkdir(parents=True)
        (folder / 'reference.wav').write_bytes(audio)
        profile = dict(schema_version=1, profile_id=name, name=name,
            kind='authorized_own_voice', language='German', reference_text='Guten Tag, ich helfe Ihnen.',
            reference_sha256=hashlib.sha256(audio).hexdigest(), source='authorized_existing_own_recording',
            consent=dict(own_voice=True, scope=self.manager.CONSENT_SCOPE,
                         confirmed_at_utc='2026-10-13T00:00:00Z'))
        (folder / 'voice.json').write_text(json.dumps(profile), encoding='utf-8')
        return self.manager.read_profile(folder)

    def bind(self, profile=None, voice_id=VOICE_ID):
        self.assertTrue(hasattr(self.manager, 'bind_native_registration'), 'Persistent UUID binding helper is missing')
        return self.manager.bind_native_registration((profile or self.profile)['profile_dir'], voice_id,
                                                      profile_root=self.root)

    def test_missing_optional_manifest_has_no_extra_registrations(self):
        self.assertEqual(self.manager.native_registrations(self.root), [])

    def test_existing_activation_lock_excludes_binding_metadata_changes(self):
        with self.manager.activation_lock(self.root):
            with self.assertRaisesRegex(RuntimeError, 'activation is in progress'):
                self.bind()
        self.assertFalse((self.root / 'native-registrations.json').exists())

    def test_manifest_profile_path_must_be_an_immutable_local_revision(self):
        self.bind()
        path = self.root / 'native-registrations.json'
        manifest = self.manager.read_json(path)
        manifest['registrations'][0]['profile_id'] = '../outside'
        self.manager.atomic_json(path, manifest)
        with self.assertRaisesRegex(ValueError, 'profile identity'):
            self.manager.native_registrations(self.root)

    def test_binding_is_metadata_only_and_remains_independent_of_active_alias(self):
        self.bind()
        second = self.make_profile('second-profile', b'second-local-reference')
        self.manager.atomic_json(self.root / 'active.json', dict(profile_id=second['profile_id'],
            reference_sha256=second['reference_sha256']))
        registrations = self.manager.native_registrations(self.root)
        self.assertEqual(len(registrations), 1)
        self.assertEqual(registrations[0]['voice_id'], VOICE_ID)
        self.assertEqual(registrations[0]['profile']['profile_id'], self.profile['profile_id'])
        self.assertEqual(self.manager.selected_profile(self.root)['profile_id'], second['profile_id'])

    def test_conflicting_uuid_binding_never_overwrites_existing_manifest(self):
        self.bind()
        manifest = self.root / 'native-registrations.json'
        before = manifest.read_bytes()
        second = self.make_profile('second-profile', b'another-reference')
        with self.assertRaisesRegex(ValueError, 'already bound'):
            self.bind(second)
        self.assertEqual(manifest.read_bytes(), before)
        self.bind()
        self.assertEqual(manifest.read_bytes(), before)

    def test_only_canonical_explicit_uuid_is_accepted_for_extra_binding(self):
        for voice_id in ('scc-demo', 'vendor-voice', 'a' * 32, VOICE_ID.upper(), '../' + VOICE_ID):
            with self.subTest(voice_id=voice_id):
                with self.assertRaises(ValueError):
                    self.bind(voice_id=voice_id)
        self.assertFalse((self.root / 'native-registrations.json').exists())

    def test_manifest_duplicate_uuid_and_malformed_hash_fail_closed(self):
        self.bind()
        path = self.root / 'native-registrations.json'
        original = self.manager.read_json(path)
        for value in (dict(original, registrations=original['registrations'] * 2),
                      dict(original, registrations=[dict(original['registrations'][0], reference_sha256='bad')])):
            with self.subTest(value=value):
                self.manager.atomic_json(path, value)
                with self.assertRaises(ValueError):
                    self.manager.native_registrations(self.root)

    def test_actual_profile_consent_and_reference_are_revalidated(self):
        self.bind()
        folder = Path(self.profile['profile_dir'])
        path = folder / 'voice.json'
        profile = self.manager.read_json(path)
        profile['consent']['own_voice'] = False
        self.manager.atomic_json(path, profile)
        with self.assertRaisesRegex(ValueError, 'consent'):
            self.manager.native_registrations(self.root)
        profile['consent']['own_voice'] = True
        self.manager.atomic_json(path, profile)
        (folder / 'reference.wav').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.manager.native_registrations(self.root)

    def test_unbound_uuid_is_rejected_before_native_listener_or_http(self):
        with patch.object(self.manager, 'native_module') as native:
            with self.assertRaises(self.manager.RegistrationRejected):
                self.manager.native_register(self.profile, voice_id=VOICE_ID, profile_root=self.root)
            native.assert_not_called()

    def test_bound_uuid_registers_exact_name_and_invalidates_receipt_before_post(self):
        self.bind()
        receipt = self.root / 'receipt.json'
        receipt.write_text('old receipt')
        payloads = []
        def request(port, route, method, body, timeout):
            self.assertFalse(receipt.exists())
            payloads.append(json.loads(body))
            return b'{"status":"registered"}', {'ok': True}
        class HTTPError(RuntimeError): pass
        native = SimpleNamespace(assert_owned_listener=lambda port: None, request=request,
            ProbePreflightError=ValueError, ProbeListenerNotReady=FileNotFoundError, ProbeHTTPError=HTTPError)
        fake_psutil = SimpleNamespace(virtual_memory=lambda: SimpleNamespace(available=50 * 1024**3))
        with patch.object(self.manager, 'native_module', return_value=native), \
                patch.object(self.manager, 'REGISTRATION_RECEIPT', receipt), \
                patch.dict('sys.modules', {'psutil': fake_psutil}):
            self.manager.native_register(self.profile, voice_id=VOICE_ID, profile_root=self.root)
            self.manager.native_register(self.profile)
        self.assertEqual([p['name'] for p in payloads], [VOICE_ID, 'scc-demo'])


if __name__ == '__main__':
    unittest.main()
