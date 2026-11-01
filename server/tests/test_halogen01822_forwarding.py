"""Opt-in 0.18.22 integration; validates commands without starting an engine."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controller as c
import manage

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / 'backends/halogen-wsl2-0.18.22'


class Halogen01822Forwarding(unittest.TestCase):
    def engine(self):
        return dict(kind='halogen', directory='backends/halogen-wsl2-0.18.22',
            checkpoint='v2', context=32768, prompt_cache='Off', launcher='python',
            python_executable=sys.executable, powershell='powershell.exe',
            prefill_chunk=8192, max_prefill_tokens=8192, disable_vision=True,
            kernel_controls={'HALOGEN_DECODE_PREFETCH': 0},
            speculation_policy={'HALOGEN_PLD': '3,3', 'HALOGEN_MTP_GATE_P': '0.90'},
            api_defaults={'enable_thinking': False, 'reasoning_effort': 'low',
                          'max_thinking_tokens': 2048})

    def test_opt_in_command_preserves_all_text_profile_controls(self):
        engine = self.engine()
        directory = c.validate_engine(engine, REPO)
        argv = c.halogen_launch_command(engine, directory)
        self.assertEqual(directory, BACKEND)
        self.assertEqual(Path(argv[0]), Path(sys.executable))
        self.assertEqual(Path(argv[3]), BACKEND / 'scripts/service.py')
        self.assertIn('--disable-vision', argv)
        for flag, value in (('--prefill-chunk', '8192'), ('--max-prefill-tokens', '8192'),
                            ('--context-size', '32768'), ('--prompt-cache', 'Off')):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        for key, flag in (('speculation_policy', '--speculation-policy-json'),
                          ('api_defaults', '--api-defaults-json'),
                          ('kernel_controls', '--kernel-controls-json')):
            self.assertEqual(json.loads(argv[argv.index(flag) + 1]), engine[key])
        self.assertNotIn('--draft-tokens', argv)

    def test_invalid_or_unqualified_controls_still_fail_closed(self):
        self.assertTrue((BACKEND / 'Start.ps1').is_file(), 'New package must exist before validating its controls')
        cases = [
            ({'speculation_policy': {'HALOGEN_MTP_GATE_P': 0.9}}, 'explicit.*string'),
            ({'speculation_policy': {'HALOGEN_NPU_WITH_GPU': '1'}}, 'Unsupported speculation'),
            ({'api_defaults': {'enable_thinking': 'false'}}, 'boolean'),
            ({'kernel_controls': {'HALOGEN_HOST_RESERVE_GIB': 0}}, 'Unsupported kernel'),
            ({'disable_vision': 1}, 'boolean'),
            ({'lookup_tuning': {}}, 'supported Halogen v2'),
            ({'private_hsa': {}}, 'pinned Halogen 0.16.2'),
            ({'prefill_chunk': 16384, 'max_prefill_tokens': 8192}, 'chunk no larger'),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                engine = self.engine()
                engine.update(copy.deepcopy(changes))
                with self.assertRaisesRegex(ValueError, message):
                    c.validate_engine(engine, REPO)

    def test_unknown_backend_rejected_by_normal_allowlists(self):
        engine = self.engine()
        unknown = REPO / 'backends/halogen-wsl2-0.18.23'
        for check in (lambda: c.halogen_speculation_module(unknown),
                      lambda: c.halogen_api_defaults_arguments(engine, unknown),
                      lambda: c.halogen_vision_arguments(engine, unknown),
                      lambda: c.halogen_launch_command(engine, unknown)):
            with self.assertRaises(ValueError):
                check()

    def test_profile_requires_matching_release_and_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            package = repo / 'backends/halogen-wsl2-0.18.22'
            (package / '.local').mkdir(parents=True)
            (package / 'profiles').mkdir()
            image = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:' + 'a' * 64
            machine = dict(version='0.18.22', image=image, pwsh='powershell.exe')
            release = dict(version='0.18.22', image=image)
            (package / '.local/machine.json').write_text(json.dumps(machine), encoding='utf-8')
            (package / '.local/api-token.txt').write_text('test-private-token', encoding='utf-8')
            release_path = package / 'profiles/release.json'
            release_path.write_text(json.dumps(release), encoding='utf-8')
            with patch.object(manage, 'REPO', repo):
                actual = manage.make_profile('Halogen', 'v2', 32768, 'Off', '0.18.22')
                self.assertEqual(actual['engine']['directory'], 'backends/halogen-wsl2-0.18.22')
                for key in ('version.api', 'version.engine'):
                    self.assertEqual(actual['backend']['expected'][key], '0.18.22')
                self.assertEqual(actual['backend']['expected']['kv_pool_positions'], 32768)
                self.assertNotIn('test-private-token', json.dumps(actual))
                for changes in ({'version': '0.18.16'}, {'image': 'different-image'}):
                    release_path.write_text(json.dumps(dict(release, **changes)), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'does not match its pinned release'):
                        manage.make_profile('Halogen', 'v2', 32768, 'Off', '0.18.22')

    def test_describe_accepts_explicit_version_without_starting(self):
        with patch.object(sys, 'argv', ['manage.py', 'describe', '--halogen-version', '0.18.22']), \
                patch.object(manage, 'make_profile', return_value={}) as make, \
                patch('builtins.print'), patch.object(manage.subprocess, 'call') as start:
            self.assertEqual(manage.main(), 0)
            make.assert_called_once_with('Halogen', 'v2', 129024, 'Off', '0.18.22')
            start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
