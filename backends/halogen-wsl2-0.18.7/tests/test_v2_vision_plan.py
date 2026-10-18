"""CPU regression for the real V2 planner; no model/GPU allocation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name == 'posix', 'Run inside WSL with GCC')
class V2VisionPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='scc-v2-vision-plan-')
        cls.executable = Path(cls.temporary.name) / 'fixture'
        result = subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror',
                                 '-DHALOGEN_RESEARCH_VGM64=1', '-DHALOGEN_PREFLIGHT_V1=1',
                                 '-DHALOGEN_CHECKPOINT_V2=1',
                                 str(ROOT / 'tests/v2-vision-plan-fixture.c'),
                                 '-o', str(cls.executable), '-ldl', '-pthread'],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_case(self, case, tower='/models/qwen38-flash-next-vision.hgn'):
        env = dict(os.environ, HALOGEN_HYBRID_PROFILE='vgm64-0187-v2-device64-v1',
                   HALOGEN_HYBRID_COPY_BYTES='68719476736', HALOGEN_HYBRID_RECLAIM_COPY='1',
                   HALOGEN_PREFLIGHT_PROFILE='flash0187-v2-device64-chunk64-v1')
        if tower is None:
            env.pop('HALOGEN_VISION_TOWER', None)
        else:
            env['HALOGEN_VISION_TOWER'] = tower
        result = subprocess.run([str(self.executable), case], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, case + '\n' + result.stderr[-3000:])
        return result

    def test_exact_main_then_tower_completes_within_existing_cap(self):
        result = self.run_case('success')
        self.assertIn('complete phase=2 copied=67585222112 host=0', result.stderr)

    def test_text_only_still_refuses_additional_mapping(self):
        self.run_case('text_only', tower=None)

    def test_tower_requires_exact_explicit_runtime_opt_in(self):
        for path in ('', '/models/other-vision.hgn', '/models/qwen38-flash-next-vision.hgn/extra'):
            with self.subTest(path=path):
                self.run_case('invalid_env', tower=path)

    def test_phase_order_completion_and_cardinality_remain_strict(self):
        for case in ('tower_first', 'incomplete_main', 'repeat_main', 'third_phase'):
            with self.subTest(case=case): self.run_case(case)

    def test_wrong_tower_layout_or_identity_poison_without_allocation(self):
        for case in ('wrong_map_size', 'wrong_aggregate', 'wrong_range_start', 'wrong_range_end',
                     'wrong_path', 'wrong_inode', 'wrong_device', 'wrong_file_size',
                     'wrong_file_offset', 'writable_map', 'shifted_map'):
            with self.subTest(case=case): self.run_case(case)

    def test_existing_cap_and_guest_reserve_are_enforced(self):
        for case in ('copy_cap', 'reserve'):
            with self.subTest(case=case): self.run_case(case)

    def test_tower_failure_never_publishes_partial_device_allocation(self):
        for case in ('allocation_fail', 'copy_fail', 'copy_free_fail'):
            with self.subTest(case=case): self.run_case(case)

    def test_identity_change_after_plan_is_rejected_before_registration(self):
        for case in ('identity_inode_drift', 'identity_path_drift'):
            with self.subTest(case=case): self.run_case(case)

if __name__ == '__main__':
    unittest.main()
