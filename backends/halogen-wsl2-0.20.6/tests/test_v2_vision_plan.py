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
        cls.temporary = tempfile.TemporaryDirectory(prefix='scc-v2-plan-')
        cls.executable = Path(cls.temporary.name) / 'fixture'
        result = subprocess.run(
            ['gcc', '-O2', '-Wall', '-Wextra', '-Werror',
             '-DHALOGEN_RESEARCH_VGM64=1', '-DHALOGEN_PREFLIGHT_V1=1',
             '-DHALOGEN_CHECKPOINT_V2=1', str(ROOT / 'tests/v2-vision-plan-fixture.c'),
             '-o', str(cls.executable), '-ldl', '-pthread'],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_case(self, case, tower=None, environment_changes=None):
        env = dict(
            os.environ,
            HALOGEN_HYBRID_PROFILE='vgm64-0206-v2-device64-v1',
            HALOGEN_HYBRID_COPY_BYTES='68719476736',
            HALOGEN_HYBRID_RECLAIM_COPY='1',
            HALOGEN_PREFLIGHT_PROFILE='flash0206-v2-device64-chunk64-v1',
            HALOGEN_V2_MAIN_IDENTITY=(
                f'{os.makedev(8, 1)},41,66687678432,10000000001,20000000002'),
            HALOGEN_V2_R2_IDENTITY=(
                f'{os.makedev(8, 1)},42,1523568192,10000000001,20000000002'),
            HALOGEN_V2_VISION_IDENTITY=(
                f'{os.makedev(8, 1)},43,897916416,10000000001,20000000002'),
        )
        if tower is None:
            env.pop('HALOGEN_VISION_TOWER', None)
        else:
            env['HALOGEN_VISION_TOWER'] = tower
        for key, value in (environment_changes or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        result = subprocess.run([str(self.executable), case], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, case + '\n' + result.stderr[-4000:])
        return result

    def test_embedded_drafter_main_supports_text_and_optional_vision(self):
        text = self.run_case('embedded_text_success')
        vision = self.run_case('embedded_vision_success', '/models/qwen38-flash-next-vision.hgn')
        self.assertIn('complete phase=1 copied=66687358944 host=0', text.stderr)
        self.assertIn('complete phase=2 copied=67585222112 host=0', vision.stderr)

    def test_external_r2_main_requires_r2_and_supports_optional_vision(self):
        text = self.run_case('r2_text_success')
        vision = self.run_case('r2_vision_success', '/models/qwen38-flash-next-vision.hgn')
        self.assertIn('complete phase=2 copied=66687364672 host=0', text.stderr)
        self.assertIn('complete phase=3 copied=67585227840 host=0', vision.stderr)

    def test_tower_requires_exact_explicit_runtime_opt_in(self):
        for path in ('', '/models/other-vision.hgn', '/models/qwen38-flash-next-vision.hgn/extra'):
            with self.subTest(path=path):
                self.run_case('invalid_env', path)

    def test_receipt_identity_environment_is_exact_and_mandatory(self):
        cases = (
            ('invalid_env', None, {'HALOGEN_V2_MAIN_IDENTITY': None}),
            ('invalid_env', None, {'HALOGEN_V2_R2_IDENTITY': None}),
            ('invalid_env', None, {'HALOGEN_V2_MAIN_IDENTITY': '2049,41,66687678432,1'}),
            ('invalid_env', '/models/qwen38-flash-next-vision.hgn',
             {'HALOGEN_V2_VISION_IDENTITY': None}),
            ('embedded_vision_receipt_mismatch', '/models/qwen38-flash-next-vision.hgn',
             {'HALOGEN_V2_VISION_IDENTITY':
              f'{os.makedev(8, 1)},43,897916416,10000000001,20000000003'}),
        )
        for case, tower, changes in cases:
            with self.subTest(case=case, tower=tower, changes=changes):
                self.run_case(case, tower, changes)

    def test_phase_order_completion_and_cardinality_remain_strict(self):
        cases = {
            'vision_first': '/models/qwen38-flash-next-vision.hgn',
            'r2_first': None,
            'embedded_repeat_main': None,
            'embedded_r2_reordered': None,
            'embedded_vision_third_phase': '/models/qwen38-flash-next-vision.hgn',
            'r2_missing': '/models/qwen38-flash-next-vision.hgn',
            'r2_repeat_main': None,
            'r2_embedded_main_reordered': None,
            'r2_repeat_r2': None,
            'r2_vision_third_phase': '/models/qwen38-flash-next-vision.hgn',
        }
        for case, tower in cases.items():
            with self.subTest(case=case):
                self.run_case(case, tower)

    def test_null_metadata_is_rejected_before_layout_observation(self):
        self.run_case('null_ranges')

    def test_r2_layout_and_file_identity_are_exact(self):
        for case in (
            'r2_wrong_map_size', 'r2_wrong_aggregate', 'r2_wrong_range_start', 'r2_wrong_range_end',
            'r2_wrong_path', 'r2_wrong_inode', 'r2_wrong_device', 'r2_wrong_file_size',
            'r2_wrong_file_offset', 'r2_writable_map', 'r2_shifted_map',
        ):
            with self.subTest(case=case):
                self.run_case(case)

    def test_existing_vision_layout_and_file_identity_remain_exact(self):
        for case in (
            'embedded_vision_wrong_map_size', 'embedded_vision_wrong_aggregate',
            'embedded_vision_wrong_range_start', 'embedded_vision_wrong_range_end',
            'embedded_vision_wrong_path', 'embedded_vision_wrong_inode',
            'embedded_vision_wrong_device', 'embedded_vision_wrong_file_size',
            'embedded_vision_wrong_file_offset', 'embedded_vision_writable_map',
            'embedded_vision_shifted_map',
        ):
            with self.subTest(case=case):
                self.run_case(case, '/models/qwen38-flash-next-vision.hgn')

    def test_registration_order_is_bound_to_each_planned_phase(self):
        cases = {
            'embedded_main_registration_order': None,
            'embedded_vision_registration_order': '/models/qwen38-flash-next-vision.hgn',
            'r2_main_registration_order': None,
            'r2_registration_order': None,
            'r2_vision_registration_order': '/models/qwen38-flash-next-vision.hgn',
        }
        for case, tower in cases.items():
            with self.subTest(case=case):
                self.run_case(case, tower)

    def test_copy_cap_and_guest_reserve_apply_in_both_modes(self):
        cases = {
            'embedded_vision_copy_cap': '/models/qwen38-flash-next-vision.hgn',
            'embedded_vision_reserve': '/models/qwen38-flash-next-vision.hgn',
            'r2_copy_cap': None,
            'r2_reserve': None,
        }
        for case, tower in cases.items():
            with self.subTest(case=case):
                self.run_case(case, tower)

    def test_identity_change_after_plan_is_rejected_before_registration(self):
        for case in (
            'embedded_vision_identity_inode_drift', 'embedded_vision_identity_path_drift',
            'r2_identity_inode_drift', 'r2_identity_path_drift',
            'r2_identity_device_drift', 'r2_identity_size_drift',
        ):
            tower = '/models/qwen38-flash-next-vision.hgn' if case.startswith('embedded_') else None
            with self.subTest(case=case):
                self.run_case(case, tower)

    def test_content_generation_change_after_receipt_is_rejected_before_publication(self):
        cases = {
            'r2_main_identity_generation_drift': None,
            'r2_identity_generation_drift': None,
            'embedded_vision_identity_generation_drift':
                '/models/qwen38-flash-next-vision.hgn',
        }
        for case, tower in cases.items():
            with self.subTest(case=case):
                self.run_case(case, tower)

    def test_content_generation_change_during_copy_is_rejected_before_publication(self):
        cases = {
            'r2_main_identity_copy_generation_drift': None,
            'r2_identity_copy_generation_drift': None,
            'embedded_vision_identity_copy_generation_drift':
                '/models/qwen38-flash-next-vision.hgn',
        }
        for case, tower in cases.items():
            with self.subTest(case=case):
                self.run_case(case, tower)

    def test_failed_main_or_r2_copy_never_publishes_partial_device_state(self):
        for case in (
            'r2_main_allocation_fail', 'r2_main_copy_fail', 'r2_allocation_fail',
            'r2_copy_fail', 'r2_copy_free_fail',
            'embedded_vision_allocation_fail', 'embedded_vision_copy_fail',
            'embedded_vision_copy_free_fail', 'r2_vision_allocation_fail',
            'r2_vision_copy_fail', 'r2_vision_copy_free_fail',
        ):
            tower = ('/models/qwen38-flash-next-vision.hgn'
                     if 'vision_' in case else None)
            with self.subTest(case=case):
                self.run_case(case, tower)


if __name__ == '__main__':
    unittest.main()
