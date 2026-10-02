import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/scheduler-reserve-optin.patch'
SOURCE = pathlib.Path('C:/Projects/strix-alloy-research/sources/pwilkin-release-20260929')


class SchedulerReservePatchTests(unittest.TestCase):
    @unittest.skipUnless(SOURCE.is_dir() and shutil.which('git'), 'Pinned source unavailable')
    def test_optin_patch_applies_and_reverses_exact_pinned_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            for name in ('src/llama-context.cpp', 'src/llama-context.h'):
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((SOURCE / name).read_bytes())
            for args in (('apply', '--check'), ('apply',),
                         ('apply', '--reverse', '--check'), ('apply', '--reverse')):
                result = subprocess.run(['git', *args, str(PATCH)], cwd=directory,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            for name in ('src/llama-context.cpp', 'src/llama-context.h'):
                self.assertEqual((directory / name).read_bytes(), (SOURCE / name).read_bytes())

    def test_default_remains_off_and_changed_chain_reserves(self):
        text = PATCH.read_text(encoding='utf-8')
        self.assertIn('LLAMA_SAMPLER_KEEP_RESERVE', text)
        self.assertIn('std::strcmp(value, "1") == 0', text)
        self.assertIn('if (!same_chain)', text)
        self.assertIn('cparams.n_seq_max == 1', text)
        self.assertIn('sampling.signatures.erase(seq_id)', text)


if __name__ == '__main__':
    unittest.main()
