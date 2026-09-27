"""Private lifecycle contract for the existing guardian, without an IPC transport.

The installed store verifies the acceptance artifact and its local trust anchor.
There is no default production lease: only that exact reviewed workload supplies
one. Synthetic adapters can exercise the guardian without changing smoke bounds.
"""
import math
from datetime import datetime, timezone
from copy import deepcopy
import time
from pathlib import Path
from typing import Literal, Protocol

from . import service_store
from . import telemetry


_AGGREGATE_FIELDS = ('captured_monotonic', 'sample_utc_min', 'sample_utc_max',
    'provider', 'gpu_scope', 'host_scope', 'adapter_luid',
    'available_physical_bytes', 'host_committed_bytes', 'host_commit_limit_bytes',
    'commit_headroom_bytes', 'adapter_dedicated_bytes', 'adapter_shared_bytes',
    'adapter_total_committed_bytes', 'dedicated_capacity_bytes')
_OWNED_FIELDS = ('available', 'reason', 'provider', 'gpu_scope', 'host_scope',
    'required_for_admission', 'captured_monotonic', 'adapter_luid', 'identity',
    'sample_utc_min', 'sample_utc_max', *telemetry.OWNED_FIELDS)


def _owned_public(value):
    if not isinstance(value, dict): return None
    result = {k: deepcopy(value.get(k)) for k in _OWNED_FIELDS}
    if isinstance(result['identity'], dict):
        result['identity'] = {k: result['identity'].get(k)
            for k in ('pid', 'creation_time_100ns', 'executable')}
    if result['available'] is not True:
        result.update(available=False, **dict.fromkeys(telemetry.OWNED_FIELDS))
    return result


def _fresh(sample, now, now_utc):
    try:
        captured = sample['captured_monotonic']
        stamps = [datetime.fromisoformat(sample[k].replace('Z', '+00:00'))
                  for k in ('sample_utc_min', 'sample_utc_max')]
        return (telemetry.finite_time(captured)
            and 0 <= now-captured <= telemetry.MAX_SAMPLE_AGE_SECONDS
            and all(0 <= (now_utc-stamp).total_seconds() <= telemetry.MAX_SAMPLE_AGE_SECONDS for stamp in stamps))
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return False


def _snapshot(guardian, *, now=None, now_utc=None):
    """Bounded observed telemetry and guardian facts; never collect on a request."""
    now = time.monotonic() if now is None else now
    now_utc = datetime.now(timezone.utc) if now_utc is None else now_utc
    sample = getattr(guardian, 'status_sample', None)
    fresh = isinstance(sample, dict) and _fresh(sample, now, now_utc)
    if guardian.child is not None:
        try:
            if guardian.exited: raise ValueError('owned_process_exited')
            telemetry._owned_identity(guardian.identity, guardian.child.verify_live_identity())
        except (OSError, ValueError, TypeError, KeyError):
            fresh = False
    return dict(phase=guardian.phase if fresh else 'unknown/stale',
        ready=bool(guardian.ready) if fresh else None,
        admitted=(guardian.resumed_at is not None) if fresh else None,
        admission_scope='guardian_pre_resume_decision',
        runtime_observed_samples=guardian.runtime_samples,
        aggregate_validation='normalized_observation_not_admission',
        aggregate_sample={k: deepcopy(sample[k]) for k in _AGGREGATE_FIELDS} if fresh else None,
        owned_counters=_owned_public(sample.get('owned_counters')) if fresh else None,
        snapshot_monotonic=now, snapshot_utc=now_utc.isoformat(),
        stop_reason='stop_requested' if guardian.stop_requested else ('guardian_failure' if guardian.failures else None),
        child_exit=guardian.exit_code, cleanup_confirmed=None, workers_terminal=None)


def _install_sampler(guardian):
    """Use the existing bounded query path, caching only its public allowlist."""
    def collect():
        owned = None
        prior = getattr(guardian, 'status_sample', None)
        if guardian.identity and prior:
            owned = dict(guardian.identity, adapter_luid=prior['adapter_luid'])
        sample = telemetry.collect_snapshot(owned=owned)
        guardian.status_sample = dict({k: deepcopy(sample[k]) for k in _AGGREGATE_FIELDS},
            owned_counters=_owned_public(sample.get('owned_counters')))
        return sample
    guardian.collect = collect


class _Lifecycle(Protocol):
    def deadline(self, resumed_at: float) -> float: ...

    def on_started(self, run_dir: Path, child_identity: dict, api_key: str) -> None:
        """Establish credentials/control before resume, or raise into owned cleanup."""
        ...

    def on_ready(self, snapshot: dict) -> None: ...

    def poll(self, now: float) -> Literal['stop', 'handoff_failed'] | None:
        """Nonblocking inspection of already available control state; never wait."""
        ...

    def on_result(self, result: dict) -> None: ...


def _validate_deadline(value, now):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= max(0, now):
        raise ValueError('service_deadline_invalid')
    return value


def _qualified_deadline(manifest, resumed_at):
    """Consume an InstalledStore-verified manifest, never finite-smoke acceptance."""
    try:
        qualification = manifest['qualification']
        anchor = manifest['qualification_anchor']
        workload = service_store._installed_workload(qualification['installed_workload'])
        service_store.validate_anchor(manifest['installed_profile'], anchor)
        if (manifest['profile'] != service_store.PROFILE_ID
                or qualification['profile_id'] != service_store.PROFILE_ID
                or qualification['status'] != 'persistent-service-accepted'
                or anchor['installed_workload'] != workload
                or not service_store.smoke_store._digest_valid(anchor['acceptance_sha256'])
                or anchor['acceptance_sha256'] != manifest['qualification_stamp']['sha256']
                or qualification['installed_workload_sha256'] != service_store._digest(workload)):
            raise ValueError('qualification_mismatch')
        return _validate_deadline(resumed_at+workload['lifetime_seconds'], resumed_at)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError('persistent_service_unqualified') from error
