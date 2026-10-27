"""Offline deployment binding checks; no credentials or service access."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HELPER = Path(__file__).with_name('model_deployment.py')
spec = importlib.util.spec_from_file_location('model_deployment', HELPER) if HELPER.exists() else None
m = importlib.util.module_from_spec(spec) if spec else None
if spec:
    spec.loader.exec_module(m)

PROFILE = Path(r'C:\Projects\strix-alloy-clean\server\.local\halogen-update-20261018\primary01810\serving01810-voice32k-prefill8192.json')
PROFILE_SHA256 = '4a0789ace369d1d0b562eae415d2f61181a6804db75c16b62275b3aba91a8b3d'


def health_from(binding):
    value = {'model': binding['model']}
    for dotted, expected in binding['expected'].items():
        target = value
        parts = dotted.split('.')
        for key in parts[:-1]:
            target = target.setdefault(key, {})
        target[parts[-1]] = expected
    return value


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m, 'shared deployment binding helper is missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.profile = json.loads(PROFILE.read_bytes())
        self.profile['backend_token_file'] = 'private/never-read-token.txt'
        self.profile_path = self.root / 'profile.json'
        self.manifest_path = self.root / 'manifest.json'
        self.write_fixture()

    def write_fixture(self, profile_bytes=None, **manifest_changes):
        data = json.dumps(self.profile).encode() if profile_bytes is None else profile_bytes
        self.profile_path.write_bytes(data)
        self.manifest = dict(schema=1, controller_root=str(self.root),
            profile=str(self.profile_path), profile_sha256=hashlib.sha256(data).hexdigest())
        self.manifest.update(manifest_changes)
        self.manifest_path.write_text(json.dumps(self.manifest), encoding='utf-8')
        self.manifest_hash = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()

    def load(self):
        return m.load_deployment(self.manifest_path, manifest_sha256=self.manifest_hash)

    def test_pinned_default_profile_and_safe_cli(self):
        binding = m.load_deployment()
        self.assertEqual(binding['profile_sha256'], PROFILE_SHA256)
        self.assertEqual(Path(binding['profile']), PROFILE.resolve())
        self.assertEqual(binding['model_token_file'], str(Path(r'C:\Projects\strix-alloy-clean\backends\halogen-wsl2-0.18.10\.local\api-token.txt').resolve()))
        self.assertEqual(binding['runner_lock'], str(Path(r'C:\Projects\strix-alloy-clean\backends\halogen-wsl2-0.18.10\.local\runner.lock').resolve()))
        result = subprocess.run([sys.executable, str(HELPER)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), binding)
        self.assertEqual(result.stderr, '')
        self.assertEqual(set(binding), {'profile','profile_sha256','controller_root','model_token_file',
            'runner_lock','expected','model','context','slots','prompt_cache'})

    def test_current_health_passes_and_old_versions_fail(self):
        binding = self.load()
        good = health_from(binding)
        self.assertTrue(m.health_matches(good, binding))
        old = copy.deepcopy(good)
        old['version'].update(api='0.18.8', engine='0.18.8')
        self.assertFalse(m.health_matches(old, binding))
        self.assertEqual(binding['expected']['version.api'], '0.18.10')

    def test_every_expected_field_and_model_require_exact_type_and_value(self):
        binding = self.load()
        good = health_from(binding)
        for dotted in list(binding['expected']) + ['model']:
            for replacement in (None, 'wrong', 1, True, 32768.0):
                value = copy.deepcopy(good)
                target = value
                parts = dotted.split('.')
                for key in parts[:-1]:
                    target = target[key]
                previous = target[parts[-1]]
                if type(previous) is type(replacement) and previous == replacement:
                    continue
                target[parts[-1]] = replacement
                with self.subTest(field=dotted, replacement=replacement):
                    self.assertFalse(m.health_matches(value, binding))
            value = copy.deepcopy(good)
            target = value
            parts = dotted.split('.')
            for key in parts[:-1]:
                target = target[key]
            del target[parts[-1]]
            self.assertFalse(m.health_matches(value, binding))
        self.assertFalse(m.health_matches(None, binding))
        self.assertFalse(m.health_matches({'version.api':'0.18.10'}, binding))

    def test_all_extra_expected_fields_are_checked(self):
        self.profile['backend']['expected']['deployment.revision'] = 'pinned'
        self.write_fixture()
        binding = self.load()
        good = health_from(binding)
        self.assertTrue(m.health_matches(good, binding))
        good['deployment']['revision'] = 'different'
        self.assertFalse(m.health_matches(good, binding))

    def test_relative_token_path_is_resolved_without_reading_it(self):
        token = self.root / self.profile['backend_token_file']
        self.assertFalse(token.exists())
        original = Path.open
        allowed = {self.manifest_path, self.profile_path}
        def guarded_open(path, *args, **kwargs):
            self.assertIn(path, allowed, 'loader opened a file other than manifest/profile')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded_open):
            binding = self.load()
        self.assertEqual(binding['model_token_file'], str(token.resolve()))
        self.assertEqual(binding['runner_lock'], str((self.root / self.profile['engine']['directory'] / '.local/runner.lock').resolve()))

    def test_manifest_and_profile_hash_changes_fail_closed(self):
        with self.assertRaises(ValueError):
            m.load_deployment(self.manifest_path)
        self.profile_path.write_bytes(self.profile_path.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            self.load()
        self.write_fixture()
        self.manifest_path.write_bytes(self.manifest_path.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            self.load()

    def test_duplicate_json_keys_rejected_even_with_matching_hash(self):
        self.write_fixture(profile_bytes=b'{"schema":1,"schema":1}')
        with self.assertRaises(ValueError):
            self.load()
        self.write_fixture()
        self.manifest_path.write_bytes(b'{"schema":1,' + self.manifest_path.read_bytes()[1:])
        self.manifest_hash = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            self.load()

    def test_bounded_files_and_json_constants_fail_closed(self):
        for data in (b' ' * 65537, b'{"schema":NaN}', b'{"schema":Infinity}', b'[]', b'null'):
            self.write_fixture(profile_bytes=data)
            with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                self.load()
        self.write_fixture()
        self.manifest_path.write_bytes(b' ' * 65537)
        self.manifest_hash = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            self.load()

    def test_profile_safety_invariants_cannot_be_rebound(self):
        original = copy.deepcopy(self.profile)
        changes = [
            ('schema', True), ('minimum_reserve_gib', 17), ('minimum_reserve_gib', 18.0),
            ('concurrency', 2), ('backend.upstream', 'http://127.0.0.1:8732'),
            ('backend.context', 8192), ('engine.context', 8192),
            ('engine.prompt_cache', 'Approximate'), ('engine.disable_vision', True),
            ('backend.expected.slots', 2), ('backend.expected.context', 8192),
            ('backend.expected.slot_ctx', 8192), ('backend.expected.kv_pool_positions', 8192),
            ('backend.expected.vision.enabled', False), ('backend.expected.version.match', 1),
            ('engine.directory', '../escape'), ('engine.directory', r'\\server\share'),
            ('backend_token_file', r'\\server\share\token'),
            ('backend_token_file', r'C:\NUL'), ('backend_token_file', 'private/CON.txt'),
        ]
        for dotted, replacement in changes:
            self.profile = copy.deepcopy(original)
            if dotted.startswith('backend.expected.'):
                self.profile['backend']['expected'][dotted[len('backend.expected.'):]] = replacement
            else:
                target = self.profile
                parts = dotted.split('.')
                for key in parts[:-1]:
                    target = target[key]
                target[parts[-1]] = replacement
            self.write_fixture()
            with self.subTest(field=dotted, value=replacement), self.assertRaises(ValueError):
                self.load()

    def test_manifest_paths_schema_and_hash_are_explicit_local_values(self):
        for changes in ({'schema': True}, {'schema':2}, {'profile':'relative.json'},
                {'controller_root':'relative'}, {'profile':r'\\server\share\profile.json'},
                {'profile_sha256':'A'*64}, {'unknown':'unsupported'}):
            self.write_fixture(**changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.load()


if __name__ == '__main__':
    unittest.main()
