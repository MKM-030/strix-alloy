"""CPU-only preflight contract: real adapter, stubbed HIP and /proc boundaries."""
import os
import json
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOGS = ('publication-early-cache-api.log', 'lookup-model-timestamped.log')


@unittest.skipUnless(os.name == 'posix', 'Linux GCC CPU fixtures; run inside WSL explicitly')
class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='preflight-cpu-')
        cls.build = pathlib.Path(cls.temporary.name)
        cls.exe = cls.build / 'fixture'
        command = ['gcc', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-DHALOGEN_RESEARCH_VGM64=1', '-DHALOGEN_PREFLIGHT_V1=1',
                   str(ROOT / 'tests/preflight-plan-fixture.c'), '-o', str(cls.exe),
                   '-ldl', '-pthread']
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError('preflight fixture must compile:\n' + result.stderr)
        cls.sequences = json.loads((ROOT / 'tests/preflight-sequences.json').read_text())
        assert len(cls.sequences) == 2 and all(len(sizes) == 253 for sizes in cls.sequences)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_case(self, case, sizes=None, changes=None):
        env = dict(os.environ, HALOGEN_HYBRID_PROFILE='vgm64-copy48-v1',
                   HALOGEN_HYBRID_COPY_BYTES='51539607552',
                   HALOGEN_HYBRID_RECLAIM_COPY='1',
                   HALOGEN_PREFLIGHT_PROFILE='flash0138-copy48-v1')
        for key, value in (changes or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        result = subprocess.run([str(self.exe), case], env=env,
                                input='\n'.join(map(str, sizes or self.sequences[0])),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, case + '\n' + result.stdout + result.stderr)
        return result

    def test_archived_sequences_complete_exact_whole_range_plan(self):
        for sizes in self.sequences:
            result = self.run_case('success', sizes)
            self.assertIn('copied=50433337536', result.stderr)
            self.assertIn('host=22574008704', result.stderr)

    def test_requires_plan_before_registration(self):
        self.run_case('unplanned')

    def test_optins_are_exact(self):
        for key, values in {
            'HALOGEN_PREFLIGHT_PROFILE': (None, '', 'wrong'),
            'HALOGEN_HYBRID_PROFILE': (None, 'wrong'),
            'HALOGEN_HYBRID_COPY_BYTES': (None, '4096', '51539607551', '51539607553',
                                          '051539607552', '+51539607552'),
            'HALOGEN_HYBRID_RECLAIM_COPY': (None, '0', 'true'),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.run_case('bad_config', changes={key: value})

    def test_bad_plan_never_commits_and_poisons(self):
        for case in ('null_ranges', 'null_output', 'range_pointer_overflow', 'zero_base', 'base_overflow',
                     'count', 'count_huge', 'length', 'sum', 'empty', 'ordering',
                     'overlap', 'outside', 'range_overflow', 'ineligible',
                     'prior_copy', 'wrong_choices', 'host_ceiling'):
            with self.subTest(case=case):
                self.run_case(case)

    def test_runtime_mismatch_failure_and_lifecycle_poison(self):
        for case in ('incomplete', 'repeat', 'third', 'wrong_pointer', 'wrong_size',
                     'wrong_flags', 'branch_drift', 'host_drift', 'malloc_fail',
                     'copy_fail', 'register_fail', 'reserve', 'missing_symbol',
                     'cleanup', 'free_fail', 'host_cleanup'):
            with self.subTest(case=case):
                self.run_case(case)

    def test_compiler_gate(self):
        source = ROOT / 'patches/hip-register-hybrid.c'
        for research, preflight in ((0, 1), (1, 2), (1, -1)):
            result = subprocess.run(['gcc', f'-DHALOGEN_RESEARCH_VGM64={research}',
                                     f'-DHALOGEN_PREFLIGHT_V1={preflight}', '-fsyntax-only',
                                     str(source)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_exact_cap_boundary(self):
        self.run_case('cap_boundary')

    def test_failed_copy_and_failed_free_remain_cleanup_only(self):
        self.run_case('copy_and_free_fail')


if __name__ == '__main__':
    unittest.main()
