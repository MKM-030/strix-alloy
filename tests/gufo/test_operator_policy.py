from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from gufo_control.operator_policy import (
    Frame, PROBES, POLICY_ID, SOURCE_COMMIT, GIB, MIB, GPU_FIELDS,
    baseline, admission_reasons, runtime_reasons, recovery_reasons)

EPOCH = datetime(2026, 9, 26, tzinfo=timezone.utc)


def frame(start, duration=1.5, **changes):
    identity = dict(luid='0x00000000_0x000111c1', vendor_id=0x1002,
        device_id=0x1586, subsystem_id=0x801d2014, flags=0,
        description='AMD Radeon(TM) 8060S Graphics', dedicated_video_memory=64*GIB)
    stamp = (EPOCH + timedelta(seconds=start)).isoformat()
    s = dict(available_physical_bytes=52*GIB, host_committed_bytes=16*GIB,
        host_commit_limit_bytes=240*GIB, dedicated_capacity_bytes=64*GIB,
        adapter_dedicated_bytes=600*MIB, adapter_shared_bytes=70*MIB,
        adapter_total_committed_bytes=800*MIB, adapter_luid=identity['luid'],
        adapter_identity=identity, captured_monotonic=start, sample_utc_min=stamp,
        sample_utc_max=stamp, telemetry_ok=True,
        provider='PDH/Get-Counter;DXGI/EnumAdapters1', gpu_scope='adapter_aggregate',
        host_scope='host_global', inventory_scope='known_engine_and_guest_names',
        other_inference_pids=[])
    s.update(changes)
    s['commit_headroom_bytes'] = s['host_commit_limit_bytes'] - s['host_committed_bytes']
    return Frame(s, start, start+duration, EPOCH+timedelta(seconds=start+duration))


def series(start=0, **changes):
    return [frame(start+2*i, **changes) for i in range(6)]


def recovery(**changes):
    return [frame(20+2*i, **changes) for i in range(5)]


class OperatorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.base = baseline(series())

    def decide(self, fn, f, key='gdn', age=None):
        now = f.query_end if age is None else f.query_start+age
        return fn(PROBES[key], self.base, f, now=now,
                  now_utc=EPOCH+timedelta(seconds=now))

    def test_allowlist_immutable_identity(self):
        self.assertEqual(set(PROBES), {'gdn', 'iq-experts'})
        self.assertEqual(PROBES['gdn'].gpu_bytes+PROBES['gdn'].host_bytes, 2*GIB)
        self.assertEqual(PROBES['iq-experts'].gpu_bytes+PROBES['iq-experts'].host_bytes, 4*GIB)
        self.assertEqual(PROBES['gdn'].deadline_seconds, 30)
        self.assertEqual(PROBES['iq-experts'].deadline_seconds, 120)
        self.assertEqual(PROBES['gdn'].source_commit, SOURCE_COMMIT)
        self.assertEqual(PROBES['gdn'].policy_id, POLICY_ID)
        self.assertEqual(PROBES['gdn'].sha256, 'DDA3E38D646CC9DDF141B8A73C2A725A5BAC755D6D2B5D8D637F19614922C97F')
        self.assertEqual(PROBES['iq-experts'].sha256, 'AE8B70B1621880E4AD58AFEC52F607E70BBD79DBDD27F63A126F9394D7020AF8')
        with self.assertRaises(TypeError):
            PROBES['new'] = PROBES['gdn']
        with self.assertRaises(FrozenInstanceError):
            PROBES['gdn'].gpu_bytes = 0
        f = frame(12)
        self.assertEqual(admission_reasons(replace(PROBES['gdn'], gpu_bytes=0),
            self.base, f, now=f.query_end, now_utc=f.validated_utc), ['unknown_probe'])

    def test_admission_boundaries(self):
        f = frame(12, available_physical_bytes=49*GIB, host_commit_limit_bytes=32*GIB)
        self.assertEqual(self.decide(admission_reasons, f, 'iq-experts'), [])
        self.assertIn('prelaunch_physical_floor', self.decide(admission_reasons,
            frame(12, available_physical_bytes=49*GIB-1)))
        self.assertIn('commit_floor', self.decide(admission_reasons,
            frame(12, host_commit_limit_bytes=32*GIB-1), 'iq-experts'))
        self.assertIn('predicted_physical_floor', self.decide(admission_reasons,
            frame(12, available_physical_bytes=26*GIB-1)))

    def test_freshness_and_query_equality(self):
        self.assertEqual(self.decide(admission_reasons, frame(12, 2)), [])
        self.assertEqual(self.decide(admission_reasons, frame(12, 2.001)), ['query_timeout'])
        self.assertEqual(self.decide(admission_reasons, frame(12), age=2.001), ['stale_or_future_sample'])
        self.assertEqual(self.decide(runtime_reasons, frame(12), age=5), [])
        self.assertEqual(self.decide(runtime_reasons, frame(12), age=5.001), ['stale_or_future_sample'])
        f = frame(12, sample_utc_min=(EPOCH+timedelta(seconds=10)).isoformat(),
                  sample_utc_max=(EPOCH+timedelta(seconds=10)).isoformat())
        self.assertEqual(self.decide(admission_reasons, f), ['stale_or_future_sample'])

    def test_historical_baseline_and_immutable_summary(self):
        frames = series()
        b = baseline(frames)
        frames[0].snapshot['available_physical_bytes'] = 0
        self.assertEqual(b.available_min, 52*GIB)
        with self.assertRaises(FrozenInstanceError):
            b.available_min = 0
        self.assertEqual(recovery_reasons(b, recovery()), [])

    def test_baseline_order_span_and_drift(self):
        for values in ([], series()[:4], [frame(i) for i in range(11)],
                       [frame(2*i) for i in range(17)],
                       [frame(0), frame(2), frame(4), frame(6), frame(12)]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                baseline(values)
        for key, limit in (('available_physical_bytes', 512*MIB),
                           ('host_committed_bytes', 512*MIB),
                           *((k, 256*MIB) for k in GPU_FIELDS)):
            frames = series()
            v = frames[-1].snapshot[key]
            frames[-1] = frame(10, **{key: v+limit})
            baseline(frames)
            frames[-1] = frame(10, **{key: v+limit+1})
            with self.assertRaisesRegex(ValueError, 'baseline_unstable'):
                baseline(frames)

    def test_runtime_envelopes_and_no_gpu_sum(self):
        updates = {k: self.base.gpu_max[i]+GIB for i, k in enumerate(GPU_FIELDS)}
        f = frame(12, available_physical_bytes=50*GIB,
                  host_committed_bytes=18*GIB, **updates)
        self.assertEqual(self.decide(runtime_reasons, f), [])
        for key in GPU_FIELDS:
            changed = dict(updates, **{key: updates[key]+1})
            self.assertIn('gpu_envelope:'+key, self.decide(runtime_reasons, frame(12, **changed)))
        self.assertIn('physical_envelope', self.decide(runtime_reasons,
            frame(12, available_physical_bytes=50*GIB-1)))
        self.assertIn('commit_envelope', self.decide(runtime_reasons,
            frame(12, host_committed_bytes=18*GIB+1)))
        b = baseline(series(available_physical_bytes=26*GIB))
        f = frame(12, available_physical_bytes=24*GIB, host_commit_limit_bytes=28*GIB)
        self.assertEqual(runtime_reasons(PROBES['gdn'], b, f, now=f.query_end, now_utc=f.validated_utc), [])
        self.assertIn('runtime_physical_floor', self.decide(runtime_reasons,
            frame(12, available_physical_bytes=24*GIB-1)))
        self.assertIn('commit_floor', self.decide(runtime_reasons,
            frame(12, host_commit_limit_bytes=28*GIB-1)))

    def test_invalid_telemetry_and_identity(self):
        for changes in (dict(available_physical_bytes=-1), dict(adapter_shared_bytes=True),
                        dict(available_physical_bytes=1<<64), dict(captured_monotonic=float('nan')),
                        dict(other_inference_pids=[7]), dict(gpu_scope='caller'),
                        dict(sample_utc_min='not-a-date'), dict(adapter_identity={}),
                        dict(host_commit_limit_bytes=0), dict(provider='other')):
            with self.subTest(changes=changes):
                self.assertTrue(self.decide(admission_reasons, frame(12, **changes)))
        f = frame(12)
        f.snapshot['adapter_luid'] = '0x00000000_0x000111c2'
        f.snapshot['adapter_identity']['luid'] = f.snapshot['adapter_luid']
        self.assertEqual(self.decide(admission_reasons, f), ['adapter_changed'])
        self.assertEqual(self.decide(admission_reasons, frame(10)), ['sample_before_baseline'])

    def test_recovery_thresholds_and_original_baseline(self):
        changes = {k: self.base.gpu_max[i]+256*MIB for i, k in enumerate(GPU_FIELDS)}
        values = recovery(available_physical_bytes=51*GIB,
                          host_committed_bytes=16*GIB+512*MIB, **changes)
        self.assertEqual(recovery_reasons(self.base, values), [])
        self.assertIn('physical_not_recovered', recovery_reasons(self.base,
            recovery(available_physical_bytes=51*GIB-1)))
        self.assertIn('commit_not_recovered', recovery_reasons(self.base,
            recovery(host_committed_bytes=16*GIB+512*MIB+1)))
        for key in GPU_FIELDS:
            self.assertIn('gpu_not_recovered:'+key, recovery_reasons(self.base,
                recovery(**{key: changes[key]+1})))
        self.assertIn('gpu_not_recovered:'+GPU_FIELDS[0], recovery_reasons(self.base,
            recovery(**{GPU_FIELDS[0]: self.base.gpu_max[0]+300*MIB})))

    def test_recovery_stability_distinctness_identity_and_floor(self):
        values = recovery()
        values[-1] = frame(28, adapter_shared_bytes=70*MIB+64*MIB)
        self.assertEqual(recovery_reasons(self.base, values), [])
        values[-1] = frame(28, adapter_shared_bytes=70*MIB+64*MIB+1)
        self.assertIn('recovery_unstable:adapter_shared_bytes', recovery_reasons(self.base, values))
        self.assertEqual(recovery_reasons(self.base, recovery()[:4]), ['recovery_count'])
        values = recovery()
        values[1] = values[0]
        self.assertEqual(recovery_reasons(self.base, values), ['invalid_series_order'])
        values = recovery()
        values[2].snapshot['adapter_identity']['luid'] = '0x00000000_0x000111c2'
        values[2].snapshot['adapter_luid'] = '0x00000000_0x000111c2'
        self.assertEqual(recovery_reasons(self.base, values), ['adapter_changed'])
        self.assertIn('commit_floor', recovery_reasons(self.base,
            recovery(host_commit_limit_bytes=28*GIB-1)))


if __name__ == '__main__':
    unittest.main()
