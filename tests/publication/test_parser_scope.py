"""Parse actual source even when the entire checkout sits beneath .local."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
PWSH=shutil.which('pwsh')

@unittest.skipUnless(PWSH, 'PowerShell 7 required')
class ParserScopeTests(unittest.TestCase):
    def fixture(self, root, bad_source=False):
        parser=root/'tests/publication/Test-PowerShellSyntax.ps1'
        parser.parent.mkdir(parents=True)
        shutil.copyfile(ROOT/'tests/publication/Test-PowerShellSyntax.ps1',parser)
        for rel in ['app/native.ps1','backends/halogen-wsl2/Start.ps1',
                    'backends/halogen-wsl2-0.14.2/Start.ps1','backends/halogen-wsl2-0.15.0/Start.ps1']:
            p=root/rel; p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text('param(' if bad_source and ('0.14.2' if bad_source is True else bad_source) in rel else 'param()',encoding='utf-8')
        ignored=root/'backends/halogen-wsl2-0.14.2/.local/broken.ps1'
        ignored.parent.mkdir(); ignored.write_text('param(',encoding='utf-8')
        return subprocess.run([PWSH,'-NoProfile','-File',str(parser)],
            capture_output=True,text=True,timeout=30)

    def test_parent_local_does_not_hide_real_backend_parser_error(self):
        with tempfile.TemporaryDirectory() as td:
            result=self.fixture(Path(td)/'.local/checkout',bad_source=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('0.14.2',result.stderr)

    def test_only_repository_local_generated_files_are_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            result=self.fixture(Path(td)/'.local/checkout')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('parsed 5 PowerShell',result.stdout)

    def test_new_backend_source_is_also_parsed(self):
        with tempfile.TemporaryDirectory() as td:
            result=self.fixture(Path(td)/'.local/checkout',bad_source='0.15.0')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('0.15.0',result.stderr)

if __name__=='__main__': unittest.main()
