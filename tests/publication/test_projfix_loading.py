"""Exercise the launcher's printed command; dummy files are never executed."""
import pathlib,re,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
PWSH=shutil.which('pwsh')
@unittest.skipUnless(PWSH,'PowerShell 7 required')
class ProjfixLoadingTests(unittest.TestCase):
    def test_lookup_loading_is_explicit_and_kv_stays_f16(self):
        with tempfile.TemporaryDirectory(prefix='alloy loading ') as folder:
            root=pathlib.Path(folder); runtime=root/'runtime'; model=root/'model'
            runtime.mkdir();model.mkdir()
            (runtime/'llama-server.exe').write_bytes(b'never execute')
            (model/'fixture-00001-of-00002.gguf').write_bytes(b'GGUF fixture')
            (model/'fixture-00002-of-00002.gguf').write_bytes(b'GGUF fixture')
            result=subprocess.run([PWSH,'-NoProfile','-File',str(ROOT/'app/launch-flash-next.ps1'),
                '-PrintOnly','-RuntimeDir',str(runtime),'-ModelDir',str(model),'-Port','49873'],
                capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertRegex(result.stdout,r'--lazy-mode\s+on(?:\s|$)')
            self.assertRegex(result.stdout,r'-ctk\s+f16\s+-ctv\s+f16')
            self.assertNotIn('--lazy-mode auto',result.stdout)
            self.assertRegex(result.stdout,r'-b\s+2048\s+-ub\s+512')
if __name__=='__main__':unittest.main()
