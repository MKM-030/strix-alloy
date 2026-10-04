"""Offline policy validation, native manifest and launcher contract."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import service

SOURCE = ROOT / 'scripts/speculation_policy.py'
POLICY = None
if SOURCE.is_file():
    spec = importlib.util.spec_from_file_location('test_halogen_speculation_policy', SOURCE)
    POLICY = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(POLICY)


class SpeculationPolicyTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(POLICY, 'Bounded speculation policy validator is missing')
        return POLICY

    def test_native_manifest_preserves_omission_and_records_exact_policy(self):
        stock_options = service.options(['--checkpoint', 'v2'])
        try:
            options = service.options(['--checkpoint', 'v2', '--speculation-policy-json',
                '{"HALOGEN_PLD":"0","HALOGEN_SPEC_ADAPT":"0"}'])
        except SystemExit as error:
            self.fail('Speculation policy CLI support is missing: ' + str(error))
        with tempfile.TemporaryDirectory() as temporary:
            attempt = Path(temporary)
            (attempt / 'entrypoint-service.sh').write_text('fixture', encoding='utf-8')
            with patch.object(service.r, 'FIXED_MOUNTS', {}), patch.object(service.r, 'MACHINE', None), \
                    patch.object(service.r, 'linux_path', side_effect=lambda path: '/fixture/' + Path(path).name):
                stock = service.build_manifest(stock_options, attempt, 'stock')
                candidate = service.build_manifest(options, attempt, 'candidate')
        self.assertNotIn('HALOGEN_PLD', stock['environment'])
        self.assertNotIn('HALOGEN_SPEC_ADAPT', stock['environment'])
        changed = {key: value for key, value in candidate['environment'].items()
                   if stock['environment'].get(key) != value}
        self.assertEqual(changed, {'HALOGEN_PLD': '0', 'HALOGEN_SPEC_ADAPT': '0'})
        self.assertEqual(candidate['speculation_policy'], changed)
        self.assertNotIn('speculation_policy', stock)
        self.assertEqual(candidate['mounts'], stock['mounts'])

    def test_only_explicit_off_and_stock_policies_are_accepted(self):
        module = self.module()
        self.assertEqual(module.environment(None), {})
        self.assertEqual(module.environment({'HALOGEN_PLD': '3,3',
            'HALOGEN_SPEC_ADAPT': '32,0.35,64'}),
            {'HALOGEN_PLD': '3,3', 'HALOGEN_SPEC_ADAPT': '32,0.35,64'})
        for policy in (None, [], {'HALOGEN_MTP_DEPTH': '2'}, {'HALOGEN_PLD': '2,3'},
                       {'HALOGEN_PLD': '3,4'}, {'HALOGEN_PLD': 0}, {'HALOGEN_PLD': False},
                       {'HALOGEN_SPEC_ADAPT': '16,0.35,64'}, {'HALOGEN_SPEC_ADAPT': ' 0'},
                       {'HALOGEN_SPEC_ADAPT': None}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                module.validate(policy)

    def test_duplicate_or_unbounded_json_is_rejected(self):
        module = self.module()
        for value in ('{"HALOGEN_PLD":"0","HALOGEN_PLD":"3,3"}', 'null', '[]',
                      '{bad}', ' ' * 1025):
            with self.subTest(value=value[:80]), self.assertRaises(ValueError):
                module.parse(value)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell launcher forwarding')
    def test_launcher_keeps_policy_json_one_argument_and_refuses_legacy_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'Start.ps1', root / 'Start.ps1')
            (root / 'scripts/service.py').write_text(
                'import json,sys\nprint(json.dumps(sys.argv[1:]))\n', encoding='utf-8')
            policy = '{"HALOGEN_PLD":"0","HALOGEN_SPEC_ADAPT":"32,0.35,64"}'
            command = [shutil.which('pwsh'), '-NoProfile', '-File', str(root / 'Start.ps1')]
            result = subprocess.run(command + ['-Checkpoint', 'v2', '-SpeculationPolicyJson',
                policy, '-PrintOnly'], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = json.loads(result.stdout)
            self.assertEqual(args[args.index('--speculation-policy-json') + 1], policy)
            self.assertIn('--print-only', args)
            legacy = subprocess.run(command + ['-Profile', 'Trace4k', '-SpeculationPolicyJson',
                policy, '-PrintOnly'], capture_output=True, text=True, timeout=15)
            self.assertNotEqual(legacy.returncode, 0)


if __name__ == '__main__':
    unittest.main()
