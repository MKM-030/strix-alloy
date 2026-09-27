"""Pure policy for the single fixed AR4k smoke; no files or processes are opened.

The profile factory consumes a manifest already authenticated by smoke_store.
It binds that record, but does not authenticate caller-created dictionaries.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
import json
import ntpath
from types import MappingProxyType

from .admission import evaluate_admission, _evaluate_service_admission, GIB, RUNTIME_FLOOR, COMMIT_RESERVE
from .operator_policy import (Frame, Baseline, baseline, recovery_reasons,
    _base_valid, _frame_reasons, _identity, MAX_PRELAUNCH_AGE_SECONDS,
    MAX_SAMPLE_AGE_SECONDS, GPU_FIELDS)
from .smoke_store import PROFILE_ID, BOUNDS, PINS, SERVICE_SMOKE, INSTALLED_SERVICE, expected_qualification, profile_bounds


def _demand(pins):
    bounds = profile_bounds(pins.profile_id)
    if (pins.bounds.keys() != bounds.keys() or any(type(pins.bounds[k]) is not int
            or pins.bounds[k] != value for k, value in bounds.items())):
        raise ValueError('unsafe_bounds')
    return dict(gpu_peak_bytes=bounds['gpu_gib']*GIB,
        host_peak_bytes=bounds['host_gib']*GIB,
        shared_physical_allowance_bytes=bounds['shared_gib']*GIB,
        commit_peak_bytes=(bounds['gpu_gib']+bounds['host_gib'])*GIB)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def stricter_runtime_baseline(original, current):
    """Synthetic numeric limits, retaining the observed current time/identity.

    This is not a measurement or a claim that historical drift was reclaimed.
    Recovery tolerances must use the actual current baseline instead.
    """
    if not _base_valid(original) or not _base_valid(current):
        raise ValueError('invalid_baseline')
    if original.identity != current.identity:
        raise ValueError('adapter_changed')
    if current.first_start < original.last_end:
        raise ValueError('sample_before_baseline')
    return replace(current,
        available_min=max(original.available_min, current.available_min),
        committed_max=min(original.committed_max, current.committed_max),
        gpu_max=tuple(min(a, b) for a, b in zip(original.gpu_max, current.gpu_max)))


@dataclass(frozen=True)
class SmokeProfile:
    profile_id: str = PROFILE_ID
    gpu_peak_bytes: int = 68*GIB
    host_peak_bytes: int = 4*GIB
    shared_physical_allowance_bytes: int = 20*GIB
    commit_peak_bytes: int = 72*GIB
    source_commit: str = PINS.source_commit
    model_revision: str = PINS.model_revision
    shared_memory_policy: str = 'measured_margin'
    qualified: bool = False
    review_id: str = ''
    shared_allowance_review_id: str = ''
    qualification_json: str = ''

    @property
    def envelope(self):
        return MappingProxyType({key: getattr(self, key) for key in (
            'gpu_peak_bytes', 'host_peak_bytes', 'shared_physical_allowance_bytes',
            'commit_peak_bytes', 'source_commit', 'model_revision',
            'shared_memory_policy', 'qualified', 'review_id', 'shared_allowance_review_id')})


def profile_from_manifest(manifest: dict, *, pins=PINS) -> SmokeProfile:
    """Bind only the fixed profile in the authenticated verify_static() result.

    No qualification file is created/read here. Missing reviews fail closed.
    The caller must retain and recheck the complete store manifest before launch.
    """
    if pins.profile_id == INSTALLED_SERVICE:
        from . import service_store
        try:
            service_store.installed_binding(pins)
            q = manifest['qualification']
            review = q['review_id']
            envelope_review = q['persistent_envelope_review_id']
            anchor = service_store.validate_anchor(manifest['installed_profile'],
                                                   manifest['qualification_anchor'])
            if (anchor['acceptance_sha256'] is None
                    or anchor['installed_workload'] is None
                    or manifest['qualification_stamp']['sha256'] != anchor['acceptance_sha256']
                    or _canonical(q) != _canonical(service_store.expected_acceptance(
                        manifest['installed_profile'], review, envelope_review,
                        anchor['installed_workload']))
                    or _canonical(manifest['installed_profile']) != _canonical(
                        service_store.expected_profile(pins))
                    or manifest['profile'] != pins.profile_id
                    or manifest['source'] != pins.source_commit
                    or manifest['model']['revision'] != pins.model_revision
                    or manifest['model']['first_shard'] != str(pins.first_shard)):
                raise ValueError('service_acceptance_mismatch')
            return SmokeProfile(**_demand(pins), profile_id=pins.profile_id,
                source_commit=pins.source_commit, model_revision=pins.model_revision,
                qualified=True, review_id=review,
                shared_allowance_review_id=envelope_review,
                qualification_json=_canonical(q))
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError('invalid_profile_manifest') from error
    try:
        q = manifest['qualification']
        review = q['guard_review_id']
        if not isinstance(review, str) or not review.strip():
            raise ValueError('guard_review_missing')
        expected = expected_qualification(pins, review)
        if (_canonical(q) != _canonical(expected)
                or manifest['profile'] != pins.profile_id
                or manifest['source'] != pins.source_commit
                or manifest['executable'] != str(pins.build / pins.executable_name)
                or manifest['sdk'] != str(pins.sdk)
                or _canonical(manifest['bounds']) != _canonical(pins.bounds)
                or manifest['model']['revision'] != pins.model_revision
                or manifest['model']['first_shard'] != str(pins.first_shard)
                or manifest['margin_report']['sha256'] != pins.margin_sha256):
            raise ValueError('qualification_mismatch')
        return SmokeProfile(**_demand(pins), profile_id=pins.profile_id, source_commit=pins.source_commit,
            model_revision=pins.model_revision, qualified=True, review_id=review,
            shared_allowance_review_id=pins.margin_sha256,
            qualification_json=_canonical(q))
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError('invalid_profile_manifest') from error


def _profile_valid(profile, *, pins=PINS):
    if not isinstance(profile, SmokeProfile):
        return False
    review = profile.review_id
    if not isinstance(review, str) or not review.strip():
        return False
    if pins.profile_id == INSTALLED_SERVICE:
        from . import service_store
        try:
            q = json.loads(profile.qualification_json)
            workload = q['installed_workload']
            expected = SmokeProfile(**_demand(pins), profile_id=pins.profile_id,
                source_commit=pins.source_commit, model_revision=pins.model_revision,
                qualified=True, review_id=review,
                shared_allowance_review_id=profile.shared_allowance_review_id,
                qualification_json=_canonical(service_store.acceptance_record(
                    service_store.expected_profile(pins), review,
                    profile.shared_allowance_review_id, workload,
                    q['controller_artifacts'])))
            return (profile == expected and profile.qualified is True
                and all(type(getattr(profile, k)) is int for k in (
                    'gpu_peak_bytes', 'host_peak_bytes',
                    'shared_physical_allowance_bytes', 'commit_peak_bytes')))
        except (ValueError, TypeError, KeyError):
            return False
    try:
        expected = SmokeProfile(**_demand(pins), profile_id=pins.profile_id, source_commit=pins.source_commit,
            model_revision=pins.model_revision, qualified=True, review_id=review,
            shared_allowance_review_id=pins.margin_sha256,
            qualification_json=_canonical(expected_qualification(pins, review)))
    except (ValueError, TypeError):
        return False
    # Canonical JSON preserves bool/int distinctions that dataclass == does not.
    return (profile == expected and profile.qualified is True
        and all(type(getattr(profile, k)) is int for k in (
            'gpu_peak_bytes', 'host_peak_bytes', 'shared_physical_allowance_bytes', 'commit_peak_bytes')))


def owned_inventory_frame(frame: Frame, owned) -> Frame:
    """Copy raw evidence and exclude exactly one proven-live owned PID.

    The retained-handle method supplies fresh PID, creation time and image proof.
    Unknown/exited/mismatched ownership raises; no name-based exemption exists.
    The guardian can save owned_inventory_proof beside its policy decision.
    """
    try:
        recorded = dict(owned.identity)
        live = owned.verify_live_identity()
        if (not isinstance(live, dict)
                or any(type(recorded.get(k)) is not int or recorded[k] <= 0
                       or type(live.get(k)) is not int or live[k] != recorded[k]
                       for k in ('pid', 'creation_time_100ns'))
                or not isinstance(recorded.get('executable'), str)
                or not recorded['executable'] or not isinstance(live.get('executable'), str)
                or ntpath.normcase(ntpath.normpath(live['executable'])) !=
                   ntpath.normcase(ntpath.normpath(recorded['executable']))):
            raise ValueError('owned_identity_unverified')
        snapshot = deepcopy(frame.snapshot)
        pids = snapshot.get('other_inference_pids')
        excluded = None
        if (isinstance(pids, list) and all(type(p) is int and p > 0 for p in pids)
                and recorded['pid'] in pids):
            pids.remove(recorded['pid'])
            excluded = recorded['pid']
        snapshot['owned_inventory_proof'] = dict(status='verified', excluded_pid=excluded,
                                                identity=deepcopy(live))
        return replace(frame, snapshot=snapshot)
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as error:
        raise ValueError('owned_identity_unverified') from error


def _common(profile, base, frame, now, now_utc, max_age, *, pins=PINS):
    if not _profile_valid(profile, pins=pins):
        return ['unqualified_profile']
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


def admission_decision(profile, original_baseline, frame, *, now, now_utc, pins=PINS) -> dict:
    """JSON-safe decision including the conditional spill minimum for evidence."""
    reasons = _common(profile, original_baseline, frame, now, now_utc,
                      MAX_PRELAUNCH_AGE_SECONDS, pins=pins)
    if reasons:
        result = dict(allowed=False, reasons=reasons, minimum_shared_spill_bytes=None,
            shared_physical_allowance_bytes=None, predicted_available_bytes=None,
            accounting_basis=None)
    else:
        if pins.profile_id in (SERVICE_SMOKE, INSTALLED_SERVICE):
            result = _evaluate_service_admission(frame.snapshot, dict(profile.envelope),
                                                 now=now, pins=pins)
        else:
            result = evaluate_admission(frame.snapshot, dict(profile.envelope), now=now)
        numeric = frame_numeric_reasons(profile, original_baseline, frame,
                                        now=now, now_utc=now_utc, pins=pins)
        result['reasons'] = list(dict.fromkeys([*result['reasons'], *numeric]))
        result['allowed'] = not result['reasons']
    result['owned_inventory_proof'] = deepcopy(frame.snapshot.get('owned_inventory_proof',
        dict(status='not_excluded', excluded_pid=None))) if (
            isinstance(frame, Frame) and isinstance(frame.snapshot, dict)) else None
    return result


def admission_reasons(profile, original_baseline, frame, *, now, now_utc, pins=PINS) -> list[str]:
    return admission_decision(profile, original_baseline, frame, now=now, now_utc=now_utc, pins=pins)['reasons']


def runtime_decision(profile, original_baseline, frame, owned, *, now, now_utc, pins=PINS) -> dict:
    """Evaluate once and retain exactly the ownership proof used for that decision."""
    try:
        scoped = owned_inventory_frame(frame, owned)
    except ValueError:
        return dict(allowed=False, reasons=['owned_identity_unverified'],
                    owned_inventory_proof=dict(status='unverified', excluded_pid=None))
    reasons = frame_numeric_reasons(profile, original_baseline, scoped, now=now, now_utc=now_utc, pins=pins)
    proof = scoped.snapshot['owned_inventory_proof']
    return dict(allowed=not reasons, reasons=reasons, owned_inventory_proof=proof)


def frame_numeric_reasons(profile, original_baseline, frame, *, now, now_utc, pins=PINS) -> list[str]:
    """Shared frame/freshness/threshold checks; never applies a PID exclusion.

    Live callers must first obtain retained-handle proof; pending-after-exit
    callers may explicitly scope a copy with historical query-start proof.
    Recovery passes raw frames, so every listed inference/guest PID refuses.
    """
    reasons = _common(profile, original_baseline, frame, now, now_utc, MAX_SAMPLE_AGE_SECONDS, pins=pins)
    if reasons:
        return reasons
    s, base = frame.snapshot, original_baseline
    if s['available_physical_bytes'] < RUNTIME_FLOOR:
        reasons.append('runtime_physical_floor')
    if s['commit_headroom_bytes'] < COMMIT_RESERVE:
        reasons.append('commit_floor')
    physical_charge = profile.host_peak_bytes + profile.shared_physical_allowance_bytes
    commit_charge = profile.commit_peak_bytes
    gpu_allowances = (profile.gpu_peak_bytes,
                      profile.shared_physical_allowance_bytes,
                      profile.gpu_peak_bytes)
    if base.available_min - s['available_physical_bytes'] > physical_charge:
        reasons.append('physical_envelope')
    if s['host_committed_bytes'] - base.committed_max > commit_charge:
        reasons.append('commit_envelope')
    for key, maximum, allowance in zip(GPU_FIELDS, base.gpu_max, gpu_allowances):
        if s[key] - maximum > allowance:
            reasons.append('gpu_envelope:' + key)
    return reasons


def runtime_reasons(profile, original_baseline, frame, owned, *, now, now_utc, pins=PINS) -> list[str]:
    return runtime_decision(profile, original_baseline, frame, owned,
                            now=now, now_utc=now_utc, pins=pins)['reasons']
