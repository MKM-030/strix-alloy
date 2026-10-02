import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PublicationBytesTests(unittest.TestCase):
    def test_git_checkout_preserves_all_frozen_bytes_with_autocrlf_modes(self):
        freeze = ROOT / 'profiles/package-sources.json'
        recorded = json.loads(freeze.read_bytes())['files']
        paths = [item['path'] for item in recorded]
        expected = {item['path']: item['sha256'] for item in recorded}
        expected['profiles/package-sources.json'] = hashlib.sha256(freeze.read_bytes()).hexdigest()
        for mode in ('true', 'false', 'input'):
            with self.subTest(autocrlf=mode), tempfile.TemporaryDirectory() as directory:
                base = pathlib.Path(directory)
                source = base / 'source'; source.mkdir()
                for name in expected:
                    destination = source / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, destination)
                subprocess.run(['git', 'init', '-q', str(source)], check=True, capture_output=True)
                subprocess.run(['git', '-C', str(source), '-c', 'core.autocrlf=' + mode,
                                'add', '--', '.'], check=True, capture_output=True)
                subprocess.run(['git', '-C', str(source), '-c', 'user.name=Fixture',
                                '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'],
                               check=True, capture_output=True)
                checkout = base / 'checkout'
                subprocess.run(['git', '-c', 'core.autocrlf=' + mode, 'clone', '-q',
                                str(source), str(checkout)], check=True, capture_output=True)
                for name, sha in expected.items():
                    self.assertEqual(hashlib.sha256((checkout / name).read_bytes()).hexdigest(), sha,
                                     f'{name} changed under core.autocrlf={mode}')
        self.assertIn('.gitattributes', paths)

    def test_comparison_prefill_uses_only_distributed_sources(self):
        script = ROOT / 'scripts/compare-halogen-modes.py'
        spec = importlib.util.spec_from_file_location('halogen_modes_fixture', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fixtures = module.cases('prefill')
        self.assertEqual([case['name'] for case in fixtures],
                         ['prefill_390', 'prefill_780', 'real_code'])
        self.assertIn('REAL_CODE_CHECK', fixtures[-1]['prompt'])
        self.assertIn((ROOT / 'patches/hip-register-hybrid.c').read_text()[:80],
                      fixtures[-1]['prompt'])


if __name__ == '__main__':
    unittest.main()
