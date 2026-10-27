"""Windows PowerShell 5.1 PrintOnly checks; no controller or engine is run."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
SCRIPT = ROOT / 'scripts/Start-Halogen-ServiceNow.ps1'
BASELINE = ROOT / 'server/.local/halogen-update-20261025/primary01815/prefetch-off-candidate/profile01815-32k-adaptive-prefetch-off.json'
TEXT_BASELINE = ROOT / 'server/.local/halogen-update-20261025/primary01816/prefetch-auto-post-heartbeat/off-packet/profile-baseline.json'
READY = (os.name == 'nt' and POWERSHELL.is_file() and BASELINE.is_file()
         and (ROOT / 'server/.local/venv/Scripts/python.exe').is_file()
         and (ROOT / 'server/.local/servicenow-api-token.txt').is_file())


@unittest.skipUnless(READY, 'Local installed backend and frozen baseline plus Windows PowerShell 5.1 required')
class MeasuredLauncherTest(unittest.TestCase):
    def invoke(self, *arguments, profile='Measured32K'):
        return subprocess.run([str(POWERSHELL), '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(SCRIPT), '-Profile', profile, '-PrintOnly', *arguments],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)

    def test_print_only_matches_measured_baseline_without_session_write(self):
        sessions = ROOT / 'server/.local/servicenow-sessions'
        before = {path.name for path in sessions.glob('*.json')}
        expected = json.loads(BASELINE.read_text(encoding='utf-8-sig'))
        for trace in [False, True]:
            with self.subTest(console_trace=trace):
                result = self.invoke(*(['-ConsoleTrace'] if trace else []))
                self.assertEqual(result.returncode, 0, result.stderr)
                start = result.stdout.find('{')
                self.assertGreaterEqual(start, 0, 'PrintOnly must return the resolved measured configuration')
                actual, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
                self.assertEqual(actual['token_file'], str(ROOT / 'server/.local/servicenow-api-token.txt'))
                self.assertEqual(actual['backend_token_file'], expected['backend_token_file'])
                self.assertEqual(actual.pop('console_trace'), trace)
                reference = copy.deepcopy(expected)
                reference.pop('console_trace')
                # Paths are deliberately returned, never token contents.
                actual.pop('token_file'); reference.pop('token_file')
                actual.pop('backend_token_file'); reference.pop('backend_token_file')
                # SystemRoot casing can vary after reboot; these are the same
                # native PS5.1 executable on the Windows filesystem.
                actual['engine']['powershell'] = os.path.normcase(actual['engine']['powershell'])
                reference['engine']['powershell'] = os.path.normcase(reference['engine']['powershell'])
                self.assertEqual(actual, reference)
        self.assertEqual({path.name for path in sessions.glob('*.json')}, before)

    def test_incompatible_explicit_profile_options_fail_before_launch(self):
        for arguments in [('-HalogenVersion', '0.18.10'), ('-Thinking', 'On'),
                          ('-MtpPolicy', 'Fixed2'), ('-PromptCache', 'Off')]:
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Measured32K requires', result.stdout + result.stderr)

    def test_existing_current4k_defaults_are_preserved(self):
        result = self.invoke(profile='Current4K')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Halogen 0.18.10 v2; MTP policy Fixed2; PLD 3,3; cache Off', result.stdout)
        self.assertIn('Context capacity: 262144', result.stdout)
        self.assertIn('Thinking default: On; medium effort', result.stdout)
        self.assertIn('Prefill chunk / token arena: 4096 / 4096', result.stdout)

    @unittest.skipUnless(TEXT_BASELINE.is_file(), 'Frozen 0.18.16 text baseline required')
    def test_text32k_print_only_matches_tested_profile_and_trace_is_opt_in(self):
        sessions = ROOT / 'server/.local/servicenow-sessions'
        before = {path.name for path in sessions.glob('*.json')}
        expected = json.loads(TEXT_BASELINE.read_text(encoding='utf-8-sig'))
        for trace in (False, True):
            with self.subTest(console_trace=trace):
                result = self.invoke(*(['-ConsoleTrace'] if trace else []), profile='MeasuredText32K')
                self.assertEqual(result.returncode, 0, result.stderr)
                start = result.stdout.find('{')
                self.assertGreaterEqual(start, 0, 'Resolved configuration must be printed')
                actual, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
                reference = copy.deepcopy(expected)
                reference['console_trace'] = trace
                actual['engine']['powershell'] = os.path.normcase(actual['engine']['powershell'])
                reference['engine']['powershell'] = os.path.normcase(reference['engine']['powershell'])
                self.assertEqual(actual, reference)
                self.assertIn('no session configuration was written and no engine was launched', result.stdout)
        self.assertEqual({path.name for path in sessions.glob('*.json')}, before)

    def test_text32k_rejects_conflicting_explicit_selectors(self):
        for arguments in [('-HalogenVersion', '0.18.15'), ('-Thinking', 'On'),
                          ('-MtpPolicy', 'Fixed2'), ('-PromptCache', 'Flexible')]:
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments, profile='MeasuredText32K')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('MeasuredText32K requires', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
