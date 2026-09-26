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
