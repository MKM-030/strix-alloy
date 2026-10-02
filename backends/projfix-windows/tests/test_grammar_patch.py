import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCH = ROOT/'patches/backend-grammar-fast-optin.patch'
SOURCE = pathlib.Path('C:/Projects/strix-alloy-research/sources/pwilkin-release-20260929/common/sampling.cpp')


class GrammarPatchTests(unittest.TestCase):
    def test_patch_is_opt_in_and_fails_closed(self):
        text = PATCH.read_text(encoding='utf-8')
        self.assertIn('LLAMA_BACKEND_GRAMMAR_FAST',text)
        self.assertIn('params.grammar_lazy',text)
        self.assertIn('params.grammar_triggers.empty()',text)
        self.assertIn('grammar fallback requires full logits',text)
        self.assertIn('llama_sampler_apply(gsmpl->grmr, &single_token_data_array)',text)
        self.assertIn('llama_sampler_apply(gsmpl->grmr, &cur_p)',text)

    @unittest.skipUnless(SOURCE.is_file() and shutil.which('git'), 'Local pinned PROJFIX source unavailable')
    def test_patch_applies_and_reverses_without_touching_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            target = directory/'common/sampling.cpp'
            target.parent.mkdir(parents=True)
            original = SOURCE.read_bytes()
            target.write_bytes(original)
            for args in (('apply','--check'),('apply',),('apply','--reverse','--check'),('apply','--reverse')):
                result = subprocess.run(['git',*args,str(PATCH)],cwd=directory,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(target.read_bytes(),original)

if __name__=='__main__': unittest.main()
