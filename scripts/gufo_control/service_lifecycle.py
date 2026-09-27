"""Private lifecycle contract for the existing guardian, without an IPC transport.

The installed store verifies the acceptance artifact and its local trust anchor.
There is no default production lease: only that exact reviewed workload supplies
one. Synthetic adapters can exercise the guardian without changing smoke bounds.
"""
import math
from pathlib import Path
from typing import Literal, Protocol

from . import service_store


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
