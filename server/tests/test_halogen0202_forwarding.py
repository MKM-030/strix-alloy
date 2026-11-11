"""The new release must retain the managed 32K serving contract."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'server'))
import controller
import manage


class Halogen0202Forwarding(unittest.TestCase):
    version = '0.20.2'

    def test_version_describe_does_not_start_an_engine(self):
        with patch.object(sys, 'argv', ['manage.py', 'describe', '--halogen-version', self.version]), \
                patch.object(manage, 'make_profile', return_value={}) as make, \
                patch('builtins.print'), patch.object(manage.subprocess, 'call') as start:
            self.assertEqual(manage.main(), 0)
            make.assert_called_once_with('Halogen', 'v2', 129024, 'Off', self.version)
            start.assert_not_called()

    def test_matching_install_generates_text_capacity_profile_without_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            package = repo / ('backends/halogen-wsl2-' + self.version)
            for name in ('.local', 'profiles', 'scripts'):
                (package / name).mkdir(parents=True)
            shutil.copyfile(REPO / 'backends/halogen-wsl2-0.20.1/scripts/capacity_policy.py',
                            package / 'scripts/capacity_policy.py')
            release = dict(version=self.version, image='synthetic-immutable-image')
            (package / 'profiles/release.json').write_text(json.dumps(release))
            (package / '.local/machine.json').write_text(json.dumps(dict(release, pwsh='powershell.exe')))
            (package / '.local/api-token.txt').write_text('synthetic-test-secret')
            with patch.object(manage, 'REPO', repo), patch.object(controller, 'ROOT', repo / 'server'):
                profile = manage.make_profile('Halogen', 'v2', 32768, 'Off', self.version,
                                              slots=1, kv_pool_positions=32768)
                self.assertEqual(profile['backend']['expected']['version.engine'], self.version)
                self.assertEqual(profile['engine']['directory'], 'backends/halogen-wsl2-' + self.version)
                self.assertEqual(profile['minimum_reserve_gib'], 18)
                self.assertEqual(profile['engine']['slots'], 1)
                self.assertEqual(profile['engine']['kv_pool_positions'], 32768)
                self.assertTrue(profile['engine']['disable_vision'])
                self.assertNotIn('synthetic-test-secret', json.dumps(profile))
                controller.validate_halogen_capacity_profile(profile, repo)
                with self.assertRaisesRegex(ValueError, 'Cache Off'):
                    manage.make_profile('Halogen', 'v2', 32768, 'Flexible', self.version,
                                        slots=1, kv_pool_positions=32768)


if __name__ == '__main__':
    unittest.main()
