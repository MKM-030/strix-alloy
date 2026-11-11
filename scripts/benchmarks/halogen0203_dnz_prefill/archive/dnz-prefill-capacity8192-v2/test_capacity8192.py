"""CPU-only capacity, preserved admission and ordinary one-slot collector tests."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / 'dnz-prefill-prep'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Tests(unittest.TestCase):
    def setUp(self):
        path = HERE / 'prepare_source.py'
        self.assertTrue(path.exists(), 'Separate8K-capacity preparation is not implemented')
        self.m = load(path, 'dnz_capacity8192_test_prepare')
        self.normal = json.loads((HERE.parent / 'serving0203-text32k-8192.json').read_bytes())
        self.budget = (self.m.PACKAGE / 'scripts/memory_budget.py').read_bytes()
        self.old_cp = sys.modules.get('capacity_policy')
        load(self.m.PACKAGE / 'scripts/capacity_policy.py', 'capacity_policy')

    def tearDown(self):
        if hasattr(self, 'old_cp'):
            if self.old_cp is None:
                sys.modules.pop('capacity_policy', None)
            else:
                sys.modules['capacity_policy'] = self.old_cp

    def test_equal_private_arms_remove_explicit_keys_and_match_native8k_health(self):
        original = copy.deepcopy(self.normal)
        profiles = self.m.profiles(self.normal)
        reference = copy.deepcopy(profiles['before'])
        reference['engine']['kernel_controls'].pop('HALOGEN_DN_Z_STREAM')
        for arm, mode in [('before', 0), ('candidate', 1), ('after', 0)]:
            value = copy.deepcopy(profiles[arm])
            self.assertNotIn('slots', value['engine'])
            self.assertNotIn('kv_pool_positions', value['engine'])
            self.assertEqual(value['engine']['context'], 8192)
            self.assertEqual(value['engine']['prefill_chunk'], 8192)
            self.assertEqual(value['engine']['max_prefill_tokens'], 8192)
            self.assertEqual(value['backend']['context'], 8192)
            expected = value['backend']['expected']
            self.assertEqual((expected['context'], expected['slot_ctx'], expected['kv_pool_positions'], expected['slots']),
                             (8192, 8192, 8192, 1))
            self.assertEqual(value['concurrency'], 1)
            self.assertNotIn('HALOGEN_EXTERNAL_STREAM', value['engine']['kernel_controls'])
            self.assertEqual(value['engine']['kernel_controls'].pop('HALOGEN_DN_Z_STREAM'), mode)
            self.assertEqual(value, reference)
        self.assertEqual(self.normal, original)
        self.assertEqual(self.normal['engine']['context'], 32768)

    def test_private_v2_clamp_keeps131_before_vision_and_w4b_unchanged(self):
        before, after = {}, {}
        exec(self.budget, before)
        exec(self.m.clamp_v2_budget(self.budget), after)
        for context in (8192, 16384, 32768, 262144):
            self.assertEqual(after['admission_floors'](context, 'v2'), (30, 131))
            self.assertEqual(after['admission_floors'](context, 'v2', vision=True), (31, 132))
            self.assertEqual(after['admission_floors'](context, 'w4b'),
                             before['admission_floors'](context, 'w4b'))
        self.assertEqual(before['admission_floors'](8192, 'v2'), (30, 123))
        self.assertEqual(after['RUNTIME_RESERVE_GIB'], 18)

    def test_existing_capacity_policy_accepts_implicit8k_and_rejects_explicit_pool(self):
        cp = sys.modules['capacity_policy']
        self.assertEqual(cp.resolve(8192, 'v2', disable_vision=True),
                         dict(context=8192, slots=1, kv_pool_positions=8192))
        with self.assertRaises(ValueError):
            cp.resolve(8192, 'v2', disable_vision=True, kv_pool_positions=8192)
        manifest = dict(context=8192, checkpoint='v2', slots=1,
                        environment=dict(HALOGEN_CTX='8192', HALOGEN_KV_POOL_POSITIONS='8192',
                                         HALOGEN_KV_SLOTS='1', HALOGEN_PROMPT_CACHE='0'))
        self.assertEqual(cp.validate_manifest(manifest)['kv_pool_positions'], 8192)

    def test_only_two_collector_slot_reads_change_and_all_guards_survive(self):
        source = (self.m.FROZEN / 'raw/collector/collect_epoch.py').read_bytes()
        changed = self.m.ordinary_collector(source)
        self.assertEqual(changed.count(b"slots = config['engine'].get('slots', 1)"), 2)
        self.assertEqual(changed.replace(b"slots = config['engine'].get('slots', 1)",
                                         b"slots = config['engine']['slots']"), source)
        with self.assertRaises(ValueError):
            self.m.ordinary_collector(changed)

    def test_ordinary_profile_collector_defaults1_but_rejects_null_bool_and_foreign_native(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            self.m.stage_collector(target)
            collector = load(target / 'raw/collector/collect_epoch.py', 'dnz_capacity8192_fake_collector')
            profile = target / 'profile.json'
            config = dict(concurrency=1, engine=dict(prompt_cache='Off'))
            profile.write_text(json.dumps(config))
            ready = dict(identities={}, outer=dict(run_id='outer', profile_sha256='sha'),
                         inner=dict(run_id='inner'), native=dict(slots=1, busy=False, in_flight=0, queued=0,
                             version=dict(api='0.20.3', engine='0.20.3', match=True)),
                         gateway=dict(active_requests=0, queued_requests=0, draining=False, completed=0,
                                      cancelled=0, request_admission_ready=None,
                                      request_admission=collector.NOT_REQUIRED_ADMISSION))
            runtime = types.SimpleNamespace(verify=lambda *a, **k: ready)
            self.assertIs(collector.verify_runtime(runtime, profile, 18840, ready), ready)
            for invalid in (None, True):
                config['engine']['slots'] = invalid
                profile.write_text(json.dumps(config))
                with self.assertRaises(ValueError):
                    collector.verify_runtime(runtime, profile, 18840, ready)
            config['engine'].pop('slots')
            profile.write_text(json.dumps(config))
            ready['native']['slots'] = 2
            with self.assertRaises(ValueError):
                collector.verify_runtime(runtime, profile, 18840, ready)

    def test_case_is_actual2048_plus128_and_8k_input_is_rejected(self):
        case = self.m.request_case(2048)
        self.assertEqual((case['actual_input_tokens'], case['actual_output_tokens'], case['capacity_context']),
                         (2048, 128, 8192))
        self.assertEqual(case['request']['sha256'], 'd7ae756957ef499de88880aba9c6c89da076cad6bcad70d120c54431c7bc071b')
        self.assertLess(case['actual_input_tokens'] + case['actual_output_tokens'], case['capacity_context'])
        with self.assertRaises(ValueError):
            self.m.request_case(8192)

    def test_overlay_budget_is_private_and_all_new_source_members_are_sealed(self):
        baseline = {'scripts/memory_budget.py': self.budget, 'profiles/sources.json': b'{}'}
        original = dict(baseline)
        candidate = self.m.capacity_candidate(baseline)
        self.assertEqual(baseline, original)
        self.assertNotEqual(candidate['scripts/memory_budget.py'], self.budget)
        manifest = json.loads(candidate['profiles/sources.json'])
        self.assertEqual(manifest['files']['scripts/memory_budget.py'],
                         hashlib.sha256(candidate['scripts/memory_budget.py']).hexdigest())


if __name__ == '__main__':
    unittest.main()
