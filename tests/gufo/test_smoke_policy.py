from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import unittest

from gufo_control import smoke_store
from gufo_control import smoke_policy as policy
from gufo_control.operator_policy import GIB, MIB, GPU_FIELDS, baseline
from test_operator_policy import EPOCH, frame, series, recovery


def manifest():
    p = smoke_store.PINS
    return dict(profile=p.profile_id, source=p.source_commit,
        executable=str(p.build / p.executable_name), sdk=str(p.sdk),
        bounds=dict(p.bounds), model=dict(revision=p.model_revision,
        first_shard=str(p.first_shard)),
        qualification=deepcopy(smoke_store.expected_qualification(p, 'independent-test-review')),
        margin_report=dict(sha256=p.margin_sha256))


class Owner:
    def __init__(self):
        self.identity = dict(pid=42, creation_time_100ns=1234, executable=r'C:\app\gufo.exe')
        self.live = dict(self.identity)

    def verify_live_identity(self):
        if isinstance(self.live, Exception):
            raise self.live
        return deepcopy(self.live)


class SmokePolicyTests(unittest.TestCase):
    def test_keyword_pins_bind_every_policy_path_without_changing_limits(self):
        from gufo_control.benchmark_runtime import BoundPolicy
        from test_benchmark_runtime import experiment, canonical, FOUR
        pins = replace(smoke_store.PINS, profile_id=FOUR,
            evidence=smoke_store.EVIDENCE.parent/'gufo-ar4k-benchmark-runs',
            experiment_json=canonical(experiment()),
            predecessors=(smoke_store.PredecessorPin(smoke_store.PROFILE_ID,
                smoke_store.EVIDENCE/smoke_store.FIRST_PREDECESSOR_RUN,
                smoke_store.FIRST_PREDECESSOR_SHA256),))
        m = manifest(); m['profile'] = FOUR
        m['qualification'] = smoke_store.expected_qualification(pins, 'review')
        bound = BoundPolicy(pins)
        p = bound.profile_from_manifest(m)
        b = baseline(series()); f = frame(12)
        kw = dict(now=f.query_end, now_utc=f.validated_utc)
        self.assertEqual(bound.admission_reasons(p, b, f, **kw), [])
        self.assertEqual(bound.runtime_reasons(p, b, f, Owner(), **kw), [])
        self.assertEqual(bound.frame_numeric_reasons(p, b, f, **kw), [])
        self.assertEqual(policy.admission_reasons(p, b, f, **kw), ['unqualified_profile'])
        self.assertEqual(bound.runtime_reasons(replace(p, gpu_peak_bytes=69*GIB),
                         b, f, Owner(), **kw), ['unqualified_profile'])
        with self.assertRaisesRegex(ValueError, 'unsafe_bounds'):
            BoundPolicy(replace(pins, bounds=dict(pins.bounds, host_gib=5)))

    def test_stricter_baseline_selects_each_limit_without_mutating_evidence(self):
        self.assertTrue(callable(getattr(policy, 'stricter_runtime_baseline', None)))
        original = baseline(series())
        for changes in (
                dict(available_min=50*GIB, committed_max=20*GIB,
                     gpu_max=tuple(v+GIB for v in original.gpu_max)),
                dict(available_min=54*GIB, committed_max=12*GIB,
                     gpu_max=tuple(v//2 for v in original.gpu_max)),
                dict(available_min=50*GIB, committed_max=12*GIB,
                     gpu_max=(original.gpu_max[0]+GIB, 0, original.gpu_max[2]))):
            current = replace(original, first_start=20, last_end=31.5, **changes)
            before = deepcopy((original, current))
            effective = policy.stricter_runtime_baseline(original, current)
            self.assertEqual(effective, replace(current,
                available_min=max(original.available_min, current.available_min),
                committed_max=min(original.committed_max, current.committed_max),
                gpu_max=tuple(min(a, b) for a, b in zip(original.gpu_max, current.gpu_max))))
            self.assertEqual((original, current), before)

    def test_stricter_baseline_validates_both_identity_and_temporal_order(self):
        self.assertTrue(callable(getattr(policy, 'stricter_runtime_baseline', None)))
        original = baseline(series())
        current = baseline(series(start=20))
        for first, second, reason in (
                (None, current, 'invalid_baseline'),
                (original, replace(current, committed_max=True), 'invalid_baseline'),
                (replace(original, gpu_max=(-1, 0, 0)), current, 'invalid_baseline'),
                (original, replace(current, identity=('other', *current.identity[1:])), 'adapter_changed'),
                (original, replace(current, first_start=11, last_end=22.5), 'sample_before_baseline')):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                policy.stricter_runtime_baseline(first, second)
        touching = replace(current, first_start=original.last_end, last_end=original.last_end+10)
        self.assertEqual(policy.stricter_runtime_baseline(original, touching), touching)

    def test_original_and_current_byte_boundaries_apply_to_admission_and_runtime(self):
        self.assertTrue(callable(getattr(policy, 'stricter_runtime_baseline', None)))
        # Synthetic large carve/available values isolate every independent ceiling.
        identity = deepcopy(frame(0).snapshot['adapter_identity'])
        identity['dedicated_video_memory'] = 128*GIB
        original = baseline(series(available_physical_bytes=80*GIB,
            dedicated_capacity_bytes=128*GIB, adapter_identity=identity))
        for delta in (-GIB, GIB):
            current = replace(original, first_start=20, last_end=31.5,
                available_min=original.available_min-delta,
                committed_max=original.committed_max+delta,
                gpu_max=tuple(v+(delta if delta > 0 else -v//2) for v in original.gpu_max))
            effective = policy.stricter_runtime_baseline(original, current)
            limits = [('available_physical_bytes', effective.available_min-24*GIB, -1, 'physical_envelope'),
                ('host_committed_bytes', effective.committed_max+72*GIB, 1, 'commit_envelope'),
                *((key, maximum+allowance*GIB, 1, 'gpu_envelope:'+key)
                  for key, maximum, allowance in zip(GPU_FIELDS, effective.gpu_max, (68, 20, 68)))]
            for key, limit, sign, reason in limits:
                for extra in (0, 1):
                    changes = dict(available_physical_bytes=80*GIB,
                        dedicated_capacity_bytes=128*GIB, adapter_identity=identity)
                    changes[key] = limit+sign*extra
                    f = frame(40, **changes)
                    for runtime in (False, True):
                        with self.subTest(delta=delta, key=key, extra=extra, runtime=runtime):
                            self.assertEqual(self.decide(f, base=effective, runtime=runtime),
                                             [reason] if extra else [])

    def test_shared_numeric_validation_never_excludes_inventory(self):
        p = policy.profile_from_manifest(manifest())
        b = baseline(series())
        for changes, reason in ((dict(available_physical_bytes=23*GIB), 'runtime_physical_floor'),
                (dict(adapter_shared_bytes=b.gpu_max[1]+20*GIB+1),
                 'gpu_envelope:adapter_shared_bytes'),
                (dict(other_inference_pids=[42]), 'other_inference_active')):
            f = frame(12, **changes)
            self.assertIn(reason, policy.frame_numeric_reasons(p, b, f,
                now=f.query_end, now_utc=f.validated_utc))

    def setUp(self):
        self.profile = policy.profile_from_manifest(manifest())
        self.base = baseline(series())
        self.owner = Owner()

    def decide(self, f, *, runtime=False, age=None, base=None, profile=None):
        now = f.query_end if age is None else f.query_start + age
        args = (profile or self.profile, base or self.base, f)
        kw = dict(now=now, now_utc=EPOCH + timedelta(seconds=now))
        if runtime:
            return policy.runtime_reasons(*args, self.owner, **kw)
        return policy.admission_reasons(*args, **kw)

    def test_profile_is_fixed_immutable_and_detached(self):
        m = manifest()
        p = policy.profile_from_manifest(m)
        m['qualification']['bounds']['gpu_gib'] = 0
        self.assertEqual(p.gpu_peak_bytes, 68*GIB)
        self.assertEqual(p.host_peak_bytes, 4*GIB)
        self.assertEqual(p.shared_physical_allowance_bytes, 20*GIB)
        self.assertEqual(p.commit_peak_bytes, 72*GIB)
        with self.assertRaises(FrozenInstanceError):
            p.qualified = False
        with self.assertRaises(TypeError):
            p.envelope['gpu_peak_bytes'] = 0
        for changed in (replace(p, gpu_peak_bytes=0), replace(p, qualified=False),
                        replace(p, review_id='unbound'), replace(p, model_revision='0'*40),
                        replace(p, shared_allowance_review_id='unbound')):
            self.assertEqual(self.decide(frame(12), profile=changed), ['unqualified_profile'])

    def test_manifest_missing_or_wrong_binding_refuses(self):
        for key in ('profile', 'source', 'executable', 'sdk', 'bounds', 'model', 'qualification', 'margin_report'):
            m = manifest()
            del m[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                policy.profile_from_manifest(m)
        for key in manifest()['qualification']:
            if key == 'guard_review_id':
                continue  # The store authenticates this independently supplied ID.
            m = manifest()
            m['qualification'][key] = 'wrong'
            with self.subTest(key=key), self.assertRaises(ValueError):
                policy.profile_from_manifest(m)
        for review in ('', ' ', None):
            m = manifest()
            m['qualification']['guard_review_id'] = review
            with self.assertRaises(ValueError):
                policy.profile_from_manifest(m)

    def test_admission_boundaries_and_recorded_spill_minimum(self):
        f = frame(12, available_physical_bytes=49*GIB, host_commit_limit_bytes=100*GIB)
        self.assertEqual(self.decide(f), [])
        d = policy.admission_decision(self.profile, self.base, f,
                                     now=f.query_end, now_utc=f.validated_utc)
        self.assertTrue(d['allowed'])
        self.assertEqual(d['shared_physical_allowance_bytes'], 20*GIB)
        self.assertEqual(d['predicted_available_bytes'], 25*GIB)
        self.assertEqual(d['minimum_shared_spill_bytes'], 4*GIB+600*MIB)
        self.assertIn('prelaunch_physical_floor', self.decide(frame(12, available_physical_bytes=49*GIB-1)))
        self.assertNotIn('predicted_physical_floor', self.decide(frame(12, available_physical_bytes=48*GIB)))
        self.assertIn('predicted_physical_floor', self.decide(frame(12, available_physical_bytes=48*GIB-1)))
        self.assertIn('commit_floor', self.decide(frame(12, host_commit_limit_bytes=100*GIB-1)))

    def test_runtime_floors_and_each_independent_delta(self):
        b = baseline(series(available_physical_bytes=48*GIB))
        f = frame(12, available_physical_bytes=24*GIB, host_committed_bytes=88*GIB,
                  host_commit_limit_bytes=100*GIB,
                  adapter_shared_bytes=b.gpu_max[1]+20*GIB,
                  adapter_total_committed_bytes=b.gpu_max[2]+68*GIB)
        self.assertEqual(self.decide(f, runtime=True, base=b), [])
        for key, reason in (('available_physical_bytes', 'physical_envelope'),
                            ('host_committed_bytes', 'commit_envelope'),
                            ('adapter_shared_bytes', 'gpu_envelope:adapter_shared_bytes'),
                            ('adapter_total_committed_bytes', 'gpu_envelope:adapter_total_committed_bytes')):
            changed = deepcopy(f.snapshot)
            changed[key] += -1 if key == 'available_physical_bytes' else 1
            self.assertIn(reason, self.decide(frame(12, **changed), runtime=True, base=b))
        self.assertIn('runtime_physical_floor', self.decide(frame(12, available_physical_bytes=24*GIB-1), runtime=True, base=b))
        self.assertIn('commit_floor', self.decide(frame(12, host_commit_limit_bytes=28*GIB-1), runtime=True))
        # Synthetic larger carve permits testing the independent 68 GiB dedicated delta.
        a = deepcopy(f.snapshot['adapter_identity'])
        a['dedicated_video_memory'] = 128*GIB
        b = baseline(series(dedicated_capacity_bytes=128*GIB, adapter_identity=a))
        for extra in (0, 1):
            f = frame(12, dedicated_capacity_bytes=128*GIB, adapter_identity=a,
                      adapter_dedicated_bytes=b.gpu_max[0]+68*GIB+extra)
            self.assertEqual('gpu_envelope:adapter_dedicated_bytes' in self.decide(f, runtime=True, base=b), bool(extra))

    def test_freshness_query_and_adapter(self):
        self.assertEqual(self.decide(frame(12, 2)), [])
        self.assertEqual(self.decide(frame(12, 2.001)), ['query_timeout'])
        self.assertEqual(self.decide(frame(12), age=2.001), ['stale_or_future_sample'])
        self.assertEqual(self.decide(frame(12), runtime=True, age=5), [])
        self.assertEqual(self.decide(frame(12), runtime=True, age=5.001), ['stale_or_future_sample'])
        self.assertTrue(self.decide(frame(12, sample_utc_max=(EPOCH+timedelta(seconds=20)).isoformat())))
        f = frame(12)
        f.snapshot['adapter_luid'] = '0x00000000_0x000111c2'
        f.snapshot['adapter_identity']['luid'] = f.snapshot['adapter_luid']
        self.assertEqual(self.decide(f), ['adapter_changed'])
        self.assertEqual(self.decide(frame(10)), ['sample_before_baseline'])

    def test_invalid_missing_scope_inventory_and_optional_attribution(self):
        for key, value in (('available_physical_bytes', -1), ('adapter_shared_bytes', 1<<64),
                           ('adapter_total_committed_bytes', True), ('gpu_scope', 'process'),
                           ('host_scope', 'process'), ('provider', 'other'),
                           ('other_inference_pids', None), ('other_inference_pids', [7]),
                           ('other_inference_pids', [42, 7]), ('telemetry_ok', False),
                           ('captured_monotonic', float('nan'))):
            with self.subTest(key=key, value=value):
                self.assertTrue(self.decide(frame(12, **{key: value}), runtime=True))
        for key in ('adapter_shared_bytes', 'host_committed_bytes', 'inventory_scope'):
            f = frame(12)
            del f.snapshot[key]
            self.assertTrue(self.decide(f))
        self.assertEqual(self.decide(frame(12, process_gpu_bytes=None, private_bytes=None), runtime=True), [])

    def test_owned_inventory_copy_and_exact_identity(self):
        f = frame(12, other_inference_pids=[42])
        scoped = policy.owned_inventory_frame(f, self.owner)
        self.assertEqual(f.snapshot['other_inference_pids'], [42])
        self.assertEqual(scoped.snapshot['other_inference_pids'], [])
        self.assertEqual(scoped.snapshot['owned_inventory_proof']['excluded_pid'], 42)
        self.assertEqual(scoped.snapshot['owned_inventory_proof']['status'], 'verified')
        scoped.snapshot['adapter_identity']['description'] = 'changed'
        self.assertNotEqual(scoped.snapshot['adapter_identity'], f.snapshot['adapter_identity'])
        self.assertEqual(self.decide(f, runtime=True), [])
        self.assertEqual(self.decide(f), ['other_inference_active'])
        self.assertIn('other_inference_active', self.decide(frame(12, other_inference_pids=[42, 42]), runtime=True))
        self.assertIn('other_inference_active', self.decide(frame(12, other_inference_pids=[42, 7]), runtime=True))
        for key, value in (('pid', 43), ('creation_time_100ns', 1235), ('executable', r'C:\evil\gufo.exe')):
            self.owner.live = dict(self.owner.identity, **{key: value})
            self.assertEqual(self.decide(f, runtime=True), ['owned_identity_unverified'])
        self.owner.live = RuntimeError('exited')
        self.assertEqual(self.decide(frame(12), runtime=True), ['owned_identity_unverified'])

    def test_baseline_and_recovery_reuse(self):
        values = series()
        values[-1] = frame(10, available_physical_bytes=52*GIB-512*MIB-1)
        with self.assertRaisesRegex(ValueError, 'baseline_unstable'):
            policy.baseline(values)
        self.assertEqual(self.decide(frame(12), base=replace(self.base, available_min=-1)), ['invalid_baseline'])
        self.assertEqual(policy.recovery_reasons(self.base, recovery()), [])
        self.assertIn('other_inference_active', policy.recovery_reasons(self.base, recovery(other_inference_pids=[42])))

    def test_decisions_preserve_proof_and_invalid_frame_is_structured(self):
        f = frame(12, other_inference_pids=[42])
        d = policy.runtime_decision(self.profile, self.base, f, self.owner,
                                   now=f.query_end, now_utc=f.validated_utc)
        self.assertTrue(d['allowed'])
        self.assertEqual(d['owned_inventory_proof']['excluded_pid'], 42)
        self.assertEqual(f.snapshot['other_inference_pids'], [42])
        self.owner.live = RuntimeError('exited')
        d = policy.runtime_decision(self.profile, self.base, f, self.owner,
                                   now=f.query_end, now_utc=f.validated_utc)
        self.assertFalse(d['allowed'])
        self.assertEqual(d['owned_inventory_proof']['status'], 'unverified')
        self.assertIsNone(d['owned_inventory_proof']['excluded_pid'])
        invalid = replace(f, snapshot=None)
        self.assertEqual(self.decide(invalid), ['invalid_frame'])


if __name__ == '__main__':
    unittest.main()
