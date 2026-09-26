# Pure GUFO Operator Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax. This planning task creates no integration implementation or commit.

**Goal:** Supply pure admission, runtime and recovery decisions for exactly two pinned operator probes.

**Architecture:** An immutable allowlist and frozen baseline hold operator policy, independent of model qualification. Each frame wraps normalized telemetry and historical collection timestamps; baseline/recovery validation uses each frame's own collection-time UTC, while current admission/runtime decisions additionally check current freshness.

**Tech Stack:** Python standard library, existing admission constants, unittest.

## Global Constraints

- Root: `C:\Projects\strix-alloy-research\integration`.
- Reuse existing49/24/12GiB constants, source commit and5s sample maximum. No model revisions, qualification flags, GPU launch, mutable policy file or command override.
- Cadence authority: `reports/gufo-telemetry-cadence-20260926.md`: each completed query<=2s, final prelaunch age<=2s, sample age<=5s. Future guardian must independently stop an active query at2s; pure code cannot interrupt a blocked collector.
- Baseline: >=5 distinct samples, >=10s overall interval, <=30s overall interval, non-overlapping queries with starts>=1s apart; host ranges<=512MiB and each GPU range<=256MiB. A gap exceeding5s is rejected. Recovery: exactly5 distinct ordered frames, same original adapter, no summing GPU fields, per-frame thresholds and GPU five-sample range<=64MiB.
- All threshold equalities pass. Invalid structures return stable reason codes from decision APIs; `baseline()` raises `ValueError` containing a stable reason on invalid historical inputs.
- `Frame.snapshot` is the existing collector's normalized dict. `query_start` and `query_end` are outer monotonic timestamps immediately before/after `collect_snapshot()`. `validated_utc` is timezone-aware UTC captured at query completion. The snapshot's `captured_monotonic` must lie within the outer interval. Snapshot sample UTC bounds must be nonfuture and at most5s old at `validated_utc`. Raw/provider normalization remains `telemetry.collect_snapshot()`'s responsibility; this module independently checks its required normalized fields. Callers must not mutate snapshots after framing. Baseline stores only immutable values, never mutable qualification state.
- Runner owns provenance/hash verification, current concurrency inventory completeness, output/result review, active-query watchdog, PID/job cleanup and durable latch. This pure module supplies no authorization to launch. Recovery success requires separate process-exit confirmation by the runner. Five historical recovery frames passing this module cannot authorize a new launch without a fresh admission frame.

### Task 1: Implement and test the pure policy

**Create:** `scripts/gufo_control/operator_policy.py` and `tests/gufo/test_operator_policy.py`.

**Interfaces:** `Frame(snapshot: dict, query_start: float, query_end: float, validated_utc: datetime)`; `baseline(frames: list[Frame]) -> Baseline`; `admission_reasons(probe: Probe, base: Baseline, frame: Frame, *, now: float, now_utc: datetime) -> list[str]`; `runtime_reasons` with the same signature; `recovery_reasons(base: Baseline, frames: list[Frame]) -> list[str]`. PROBES is read-only and each Probe/Baseline is frozen. Reason lists contain zero or more stable strings.

- [ ] Create the complete test file from the second code block below; run its focused command and confirm import failure before adding implementation.
- [ ] Create this complete module, preserving the existing admission module unchanged:

```python
"""Pure fixed-operator bootstrap policy; never launches or qualifies a model."""
from dataclasses import dataclass
from datetime import datetime
import math
import re
from types import MappingProxyType

from .admission import (GIB, MAX_BYTES, PRELAUNCH_FLOOR, RUNTIME_FLOOR,
                        COMMIT_RESERVE, MAX_SAMPLE_AGE_SECONDS, SOURCE_COMMIT)

POLICY_ID = 'operator-bootstrap-v1'
MIB = 1 << 20
MAX_QUERY_SECONDS = 2.0
MAX_PRELAUNCH_AGE_SECONDS = 2.0
GPU_FIELDS = ('adapter_dedicated_bytes', 'adapter_shared_bytes',
              'adapter_total_committed_bytes')
BYTE_FIELDS = ('available_physical_bytes', 'host_committed_bytes',
               'host_commit_limit_bytes', 'commit_headroom_bytes',
               'dedicated_capacity_bytes', *GPU_FIELDS)
PROVIDER = 'PDH/Get-Counter;DXGI/EnumAdapters1'


@dataclass(frozen=True)
class Probe:
    key: str
    filename: str
    sha256: str
    gpu_bytes: int
    host_bytes: int
    deadline_seconds: int
    source_commit: str = SOURCE_COMMIT
    policy_id: str = POLICY_ID


PROBES = MappingProxyType({
    'gdn': Probe('gdn', 'qwen38_flash_next_gdn_ops_test.exe',
        'DDA3E38D646CC9DDF141B8A73C2A725A5BAC755D6D2B5D8D637F19614922C97F',
        GIB, GIB, 30),
    'iq-experts': Probe('iq-experts', 'qwen38_flash_next_iq_experts_ops_test.exe',
        'AE8B70B1621880E4AD58AFEC52F607E70BBD79DBDD27F63A126F9394D7020AF8',
        2*GIB, 2*GIB, 120),
})


@dataclass(frozen=True)
class Frame:
    snapshot: dict
    query_start: float
    query_end: float
    validated_utc: datetime


@dataclass(frozen=True)
class Baseline:
    identity: tuple
    available_min: int
    committed_max: int
    gpu_max: tuple
    first_start: float
    last_end: float


def _time(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('invalid_utc')
    return value


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError('invalid_utc')
    return _utc(datetime.fromisoformat(value.replace('Z', '+00:00')))


def _identity(s):
    a = s['adapter_identity']
    luid = s['adapter_luid']
    if not isinstance(luid, str) or not re.fullmatch(
            r'0x[0-9a-f]{8}_0x[0-9a-f]{8}', luid):
        raise ValueError('invalid_adapter')
    expected = (0x1002, 0x1586, 0x801d2014, 0,
                'AMD Radeon(TM) 8060S Graphics')
    fields = ('vendor_id', 'device_id', 'subsystem_id', 'flags', 'description')
    if (not isinstance(a, dict) or tuple(a.get(k) for k in fields) != expected
            or any(type(a.get(k)) is not int for k in fields[:4])
            or not isinstance(a.get('luid'), str)
            or a['luid'].lower() != luid
            or type(a.get('dedicated_video_memory')) is not int
            or a['dedicated_video_memory'] != s['dedicated_capacity_bytes']):
        raise ValueError('invalid_adapter')
    return (luid, *expected, s['dedicated_capacity_bytes'])


def _frame_reasons(f, *, now=None, now_utc=None, max_age=MAX_SAMPLE_AGE_SECONDS):
    try:
        if not isinstance(f, Frame) or not isinstance(f.snapshot, dict):
            return ['invalid_frame']
        s = f.snapshot
        if any(type(s.get(k)) is not int or not 0 <= s[k] <= MAX_BYTES
               for k in BYTE_FIELDS):
            return ['invalid_counter']
        if (s['host_committed_bytes'] > s['host_commit_limit_bytes']
                or s['commit_headroom_bytes'] !=
                s['host_commit_limit_bytes'] - s['host_committed_bytes']
                or s['dedicated_capacity_bytes'] == 0
                or s['adapter_dedicated_bytes'] > s['dedicated_capacity_bytes']):
            return ['inconsistent_counter']
        _identity(s)
        if (s.get('telemetry_ok') is not True or s.get('provider') != PROVIDER
                or s.get('gpu_scope') != 'adapter_aggregate'
                or s.get('host_scope') != 'host_global'
                or s.get('inventory_scope') != 'known_engine_and_guest_names'):
            return ['invalid_scope']
        pids = s.get('other_inference_pids')
        if not isinstance(pids, list) or any(type(p) is not int or p <= 0 for p in pids):
            return ['invalid_inventory']
        if pids:
            return ['other_inference_active']
        captured = s.get('captured_monotonic')
        if not all(_time(t) for t in (f.query_start, f.query_end, captured)):
            return ['invalid_time']
        if not f.query_start <= captured <= f.query_end:
            return ['invalid_time']
        if f.query_end - f.query_start > MAX_QUERY_SECONDS:
            return ['query_timeout']
        lo, hi = _stamp(s['sample_utc_min']), _stamp(s['sample_utc_max'])
        validated = _utc(f.validated_utc)
        if not lo <= hi <= validated or (validated - lo).total_seconds() > MAX_SAMPLE_AGE_SECONDS:
            return ['stale_or_future_sample']
        if now is not None or now_utc is not None:
            if not _time(now) or now < f.query_end:
                return ['invalid_time']
            current = _utc(now_utc)
            if current < validated:
                return ['invalid_time']
            if (now - captured > max_age
                    or (current - lo).total_seconds() > max_age):
                return ['stale_or_future_sample']
        return []
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return ['invalid_frame']


def _series(frames):
    if not isinstance(frames, list) or not frames:
        return ['invalid_series']
    previous = None
    identity = None
    for f in frames:
        reasons = _frame_reasons(f)
        if reasons:
            return reasons
        current = _identity(f.snapshot)
        if identity is not None and current != identity:
            return ['adapter_changed']
        identity = current
        if previous is not None:
            if (f.query_start < previous.query_end
                    or f.query_start - previous.query_start < 1
                    or f.validated_utc <= previous.validated_utc
                    or _stamp(f.snapshot['sample_utc_min']) <=
                    _stamp(previous.snapshot['sample_utc_min'])):
                return ['invalid_series_order']
            if f.query_start - previous.query_start > MAX_SAMPLE_AGE_SECONDS:
                return ['series_gap']
        previous = f
    return []


def baseline(frames: list[Frame]) -> Baseline:
    reasons = _series(frames)
    if reasons:
        raise ValueError(reasons[0])
    span = frames[-1].query_end - frames[0].query_start
    if len(frames) < 5 or not 10 <= span <= 30:
        raise ValueError('baseline_duration')
    for key, tolerance in (('available_physical_bytes', 512*MIB),
                           ('host_committed_bytes', 512*MIB),
                           *((k, 256*MIB) for k in GPU_FIELDS)):
        values = [f.snapshot[key] for f in frames]
        if max(values) - min(values) > tolerance:
            raise ValueError('baseline_unstable:' + key)
    return Baseline(_identity(frames[0].snapshot),
        min(f.snapshot['available_physical_bytes'] for f in frames),
        max(f.snapshot['host_committed_bytes'] for f in frames),
        tuple(max(f.snapshot[k] for f in frames) for k in GPU_FIELDS),
        frames[0].query_start, frames[-1].query_end)


def _base_valid(b):
    return (isinstance(b, Baseline) and isinstance(b.identity, tuple)
        and len(b.identity) == 7 and isinstance(b.gpu_max, tuple)
        and len(b.gpu_max) == 3
        and all(type(v) is int and 0 <= v <= MAX_BYTES
                for v in (b.available_min, b.committed_max, *b.gpu_max))
        and _time(b.first_start) and _time(b.last_end)
        and 10 <= b.last_end - b.first_start <= 30)


def _common(probe, base, frame, now, now_utc, max_age):
    if (not isinstance(probe, Probe) or not isinstance(probe.key, str)
            or PROBES.get(probe.key) != probe):
        return ['unknown_probe']
    if not _base_valid(base):
        return ['invalid_baseline']
    reasons = _frame_reasons(frame, now=now, now_utc=now_utc, max_age=max_age)
    if reasons:
        return reasons
    if _identity(frame.snapshot) != base.identity:
        return ['adapter_changed']
    if frame.query_start < base.last_end:
        return ['sample_before_baseline']
    return []


def admission_reasons(probe: Probe, base: Baseline, frame: Frame, *,
                      now: float, now_utc: datetime) -> list[str]:
    reasons = _common(probe, base, frame, now, now_utc, MAX_PRELAUNCH_AGE_SECONDS)
    if reasons:
        return reasons
    s, charge = frame.snapshot, probe.gpu_bytes + probe.host_bytes
    if s['available_physical_bytes'] < PRELAUNCH_FLOOR:
        reasons.append('prelaunch_physical_floor')
    if s['available_physical_bytes'] - charge < RUNTIME_FLOOR:
        reasons.append('predicted_physical_floor')
    if s['commit_headroom_bytes'] - charge < COMMIT_RESERVE:
        reasons.append('commit_floor')
    return reasons


def runtime_reasons(probe: Probe, base: Baseline, frame: Frame, *,
                    now: float, now_utc: datetime) -> list[str]:
    reasons = _common(probe, base, frame, now, now_utc, MAX_SAMPLE_AGE_SECONDS)
    if reasons:
        return reasons
    s, charge = frame.snapshot, probe.gpu_bytes + probe.host_bytes
    if s['available_physical_bytes'] < RUNTIME_FLOOR:
        reasons.append('runtime_physical_floor')
    if s['commit_headroom_bytes'] < COMMIT_RESERVE:
        reasons.append('commit_floor')
    if base.available_min - s['available_physical_bytes'] > charge:
        reasons.append('physical_envelope')
    if s['host_committed_bytes'] - base.committed_max > charge:
        reasons.append('commit_envelope')
    for key, maximum in zip(GPU_FIELDS, base.gpu_max):
        if s[key] - maximum > probe.gpu_bytes:
            reasons.append('gpu_envelope:' + key)
    return reasons


def recovery_reasons(base: Baseline, frames: list[Frame]) -> list[str]:
    if not _base_valid(base):
        return ['invalid_baseline']
    reasons = _series(frames)
    if reasons:
        return reasons
    if len(frames) != 5:
        return ['recovery_count']
    if _identity(frames[0].snapshot) != base.identity:
        return ['adapter_changed']
    if frames[0].query_start < base.last_end:
        return ['sample_before_baseline']
    reasons = []
    for f in frames:
        s = f.snapshot
        if s['available_physical_bytes'] < max(PRELAUNCH_FLOOR, base.available_min - GIB):
            reasons.append('physical_not_recovered')
        if s['host_committed_bytes'] > base.committed_max + 512*MIB:
            reasons.append('commit_not_recovered')
        if s['commit_headroom_bytes'] < COMMIT_RESERVE:
            reasons.append('commit_floor')
        for key, maximum in zip(GPU_FIELDS, base.gpu_max):
            if s[key] > maximum + 256*MIB:
                reasons.append('gpu_not_recovered:' + key)
    for key in GPU_FIELDS:
        values = [f.snapshot[key] for f in frames]
        if max(values) - min(values) > 64*MIB:
            reasons.append('recovery_unstable:' + key)
    return list(dict.fromkeys(reasons))
```

- [ ] Use this complete test file (synthetic data only, no real telemetry/process calls):

```python
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
        # Second residual is evaluated against original baseline, never recentered.
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
```

- [ ] From integration root set `$env:PYTHONPATH='scripts'` in the child shell and run `python -m unittest discover -s tests/gufo -p test_operator_policy.py -v`. Expect all9 test methods passing. Fix any concrete discrepancy, preserving the stated contract; do not launch a GPU to validate pure arithmetic.
- [ ] Run `python -m unittest discover -s tests/gufo -v` once. Expect all existing/new tests passing, platform skips only where already declared. This suite uses existing harmless owned-child checks, not model/GPU binaries. Preserve unrelated changes and inspect diff limited to the two owned files.
- [ ] Future authorized implementer commits only these two files with `git add scripts/gufo_control/operator_policy.py tests/gufo/test_operator_policy.py` then `git commit -m "feat: add pure GUFO operator bootstrap policy"`. This instruction applies to the future authorized implementation, not this report-writing task. Report tests and commit ID to the parent for independent review before runner integration.

Self-review: complete code and test fixtures are included; no launch hooks, model identity fabrication, mutable qualification source or GPU field summation. Historical baseline validation is independent of present time; current admission/runtime APIs enforce current monotonic and UTC freshness. Outer active-query watchdog belongs to the future runner. The original Baseline must persist across the sequence; replacing it with a recovered sample would violate the caller contract. This plan has not been executed.
