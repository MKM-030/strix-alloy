from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manage

class ProfileTests(unittest.TestCase):
    def test_context_and_cache_validation(self):
        for capacity in (True,0,262145):
            with self.assertRaises(ValueError): manage.make_profile('Halogen','v2',capacity)
        with self.assertRaises(ValueError): manage.make_profile('Halogen','bad',129024)
        with self.assertRaises(ValueError): manage.make_profile('Halogen','v2',129024,'unknown')

    def test_native_candidates_do_not_silently_fall_back(self):
        with patch.object(Path,'is_file',return_value=False):
            for backend in ('GUFO','Projfix'):
                with self.assertRaisesRegex(ValueError,'no qualified'):
                    manage.make_profile(backend,'w4b',129024)

    def test_managed_01816_requires_matching_pinned_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            package = repo / 'backends/halogen-wsl2-0.18.16'
            (package / '.local').mkdir(parents=True)
            (package / 'profiles').mkdir()
            image = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:' + 'a' * 64
            machine = dict(version='0.18.16', image=image, pwsh='C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')
            (package / '.local/machine.json').write_text(json.dumps(machine), encoding='utf-8')
            (package / '.local/api-token.txt').write_text('private-test-token', encoding='utf-8')
            (package / 'profiles/release.json').write_text(json.dumps(dict(version='0.18.16', image=image)), encoding='utf-8')
            with patch.object(manage, 'REPO', repo):
                actual = manage.make_profile('Halogen', 'v2', 32768, 'Off', '0.18.16')
                self.assertEqual(actual['engine']['directory'], 'backends/halogen-wsl2-0.18.16')
                self.assertEqual(actual['backend']['expected']['version.api'], '0.18.16')
                self.assertEqual(actual['backend']['expected']['version.engine'], '0.18.16')
                self.assertEqual(actual['backend']['expected']['kv_pool_positions'], 32768)
                self.assertEqual(actual['engine']['prompt_cache'], 'Off')
                self.assertNotIn('private-test-token', json.dumps(actual))
                machine['image'] = 'different-image'
                (package / '.local/machine.json').write_text(json.dumps(machine), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'does not match its pinned release'):
                    manage.make_profile('Halogen', 'v2', 32768, 'Off', '0.18.16')

    def test_describe_accepts_01816_without_starting(self):
        with patch.object(sys, 'argv', ['manage.py', 'describe', '--halogen-version', '0.18.16']), \
                patch.object(manage, 'make_profile', return_value={}) as make, \
                patch('builtins.print'), patch.object(manage.subprocess, 'call') as start:
            self.assertEqual(manage.main(), 0)
            make.assert_called_once_with('Halogen', 'v2', 129024, 'Off', '0.18.16')
            start.assert_not_called()

if __name__=='__main__': unittest.main()
