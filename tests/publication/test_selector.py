"""Offline selector tests: no WSL, model, network, or installation is started."""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PWSH = shutil.which('pwsh')

@unittest.skipUnless(PWSH, 'PowerShell 7 is required')
class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='strix selector ')
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'app').mkdir()
        self.selector = self.root / 'app/select-backend.ps1'
        shutil.copyfile(ROOT / 'app/select-backend.ps1', self.selector)
        native = self.root / 'app/launch-flash-next.ps1'
        native.write_text("throw 'Native launcher must not execute during discovery'\n")
        self.model = self.root / "model's weights & data"
        self.runtime = self.root / 'runtime with spaces'
        self.model.mkdir()
        self.runtime.mkdir()
        self.draft = self.model / 'matching draft.gguf'
        self.draft.write_bytes(b'fixture, not model weights')

    def invoke(self, *args):
        return subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File',
                               str(self.selector), *map(str, args)],
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=30)

    def test_all_descriptions_are_explicit_and_read_only(self):
        for name in ('Native', 'Projfix', 'Halogen', 'GUFO'):
            with self.subTest(backend=name):
                result = self.invoke('-Backend', name, '-Action', 'Describe')
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertFalse(data['selector_starts_models'])
                self.assertFalse(data['single_shared_endpoint'])
                if name == 'Halogen':
                    self.assertEqual(data['version'], '0.14.2')
                    self.assertEqual(data['launcher'], 'backends/halogen-wsl2-0.14.2/Start.ps1')
                    self.assertIn('Serve4k', data['start_command'])
                if name == 'GUFO':
                    self.assertEqual(data['status'], 'persistent_service_unqualified')
                    self.assertIsNone(data['launcher'])

    def test_native_plan_preserves_arguments_without_execution(self):
        result = self.invoke('-Backend', 'Projfix', '-Action', 'PrintOnly',
                             '-ModelDir', self.model, '-RuntimeDir', self.runtime,
                             '-DraftPath', self.draft)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data['executed'])
        self.assertEqual(data['arguments'], ['-PrintOnly', '-ModelDir', str(self.model),
                         '-RuntimeDir', str(self.runtime), '-DraftPath', str(self.draft)])

    def test_unqualified_or_unsupported_print_only_refuses(self):
        for name in ('Halogen', 'GUFO'):
            with self.subTest(backend=name):
                result = self.invoke('-Backend', name, '-Action', 'PrintOnly')
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('refused:', result.stderr)

    def test_unknown_arguments_and_start_actions_refuse(self):
        cases = [('-Backend', 'Unknown', '-Action', 'Describe'),
                 ('-Backend', 'Native', '-Action', 'Start'),
                 ('-Backend', 'Native', '-Action', 'Stop'),
                 ('-Backend', 'Native', '-Action', 'Describe', '-Force'),
                 ('Native', 'Describe'),
                 ('-Backend', 'Native', '-Action', 'Describe', '-ModelDir', self.model)]
        for args in cases:
            with self.subTest(args=args):
                self.assertNotEqual(self.invoke(*args).returncode, 0)

    def test_missing_relative_and_wrong_type_paths_refuse(self):
        for path in ('relative', self.root / 'missing', self.draft):
            with self.subTest(path=path):
                result = self.invoke('-Backend', 'Native', '-Action', 'PrintOnly',
                                     '-ModelDir', path, '-RuntimeDir', self.runtime)
                self.assertEqual(result.returncode, 2, result.stderr)
        result = self.invoke('-Backend', 'Native', '-Action', 'PrintOnly', '-ModelDir', self.model)
        self.assertEqual(result.returncode, 2, result.stderr)
