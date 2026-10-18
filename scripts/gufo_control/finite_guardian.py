"""Private finite lifecycle adapter. No public CLI, spawning or retry."""
import re
import threading
import time

from . import finite_profile as fp, finite_store as fs
from . import service_ipc as ipc, service_lifecycle, smoke_guard
from .benchmark_runtime import BoundPolicy
from .finite_session import FiniteSession
from .finite_workload import load_workload, WORKLOAD_SHA256


def finite_argv(api_key):
    fp.finite_binding(fp.PINS)
    if type(api_key) is not str or re.fullmatch(r'[A-Za-z0-9_-]{43}', api_key) is None:
        raise ValueError('finite_key')
    p = fp.PINS
    return [str(p.build/p.executable_name), 'serve', '--host', '127.0.0.1',
        '--port', '8836', '--sessions', '1', '--max-connections', '3',
        '--max-request-bytes', '16384', '--api-key', api_key, 'llm', '--model',
        str(p.first_shard), '--served-model-name', 'gufo-flash-next', '--context',
        '4096', '--max-tokens', '64', '--think', 'off', '--speculative', 'off',
        '--max-pending', '1', '--max-pending-per-client', '1',
        '--request-timeout-ms', '60000', '--max-output-bytes', '1048576',
        '--request-policy', 'ar4k-service-v1', '--preserve-thinking', 'off']


class _FiniteGuardian(smoke_guard._Guardian):
    def __init__(self, **dependencies):
        self.index = None
        self.recovery_completed = None
        self.phase_sha256 = None
        self.workload = load_workload()
        dependencies.setdefault('store', fs.FiniteStore())
        dependencies.setdefault('policy_module', BoundPolicy(fp.PINS))
        dependencies.setdefault('argv_builder', finite_argv)
        dependencies.setdefault('profile_id', fp.PROFILE_ID)
        dependencies.setdefault('http_start', self._start_http)
        super().__init__(**dependencies)

    def _prepared_recheck_kwargs(self):
        return dict(prepared_run=self.run_dir)

    def _immutable_terminal(self):
        return True

    def _before_begin(self, frame):
        proof = self.store.record_admission(self.run_dir, self.manifest,
            self.current, frame, now=time.monotonic(), now_utc=smoke_guard.utcnow())
        self.index = proof['lifecycle']
        if type(self.index) is not int or self.index not in (1, 2):
            raise ValueError('finite_lifecycle_index')

    def _start_http(self, **arguments):
        if self.lifecycle is None or self.resumed_at is None:
            raise ValueError('finite_guardian_binding')
        return FiniteSession(self.workload, self.index, self.run_dir,
            resumed_at=self.resumed_at, committed=self.lifecycle.commit_event,
            parent_live=self.lifecycle.parent_live, **arguments)

    def _http_terminal(self):
        return (not self.http_requested or
                (self.http is not None and self.http.terminal()))

    def _recover(self):
        super()._recover()
        if self.recovered and len(self.recovery_samples) == 5:
            self.recovery_completed = time.monotonic()

    def _result(self):
        result = super()._result()
        complete = self.http is not None and self.http.complete()
        valid_stop = self.lifecycle is not None and self.lifecycle.valid_stop
        result.update(finite_coverage=self.http.coverage() if self.http else None,
            finite_phase_sha256=self.phase_sha256,
            finite_recovery_completed_monotonic=self.recovery_completed,
            finite_acceptance='structural_only',
            finite_memory=dict(telemetry='telemetry.jsonl',
                boundaries='phase-evidence.json', per_phase_peaks=None,
                per_phase_peak_status='unknown_not_analyzed',
                owned_counter_status='consult_each_sample; missing_is_unknown'))
        result['success'] = result['success'] and complete and valid_stop
        if not complete or not valid_stop:
            result['failure'] = result['failure'] or 'finite_coverage_or_authenticated_stop_incomplete'
        return smoke_guard._redact(result, self.secret)

    def _persist(self, result):
        try:
            if self.http is not None and self.http.complete():
                record = fs.phase_record(self.run_dir, self.manifest,
                                         self.index, self.http.coverage())
                fs._write(self.run_dir/'phase-evidence.json', record)
                self.phase_sha256 = fs._digest(record)
            if self.lifecycle is not None:
                if not self.lifecycle.parent.alive():
                    self._fail(ValueError('finite_parent_lost'))
                # Confirm native IPC retirement before allowing finish_run to
                # retire the finite incomplete latch. on_result is local-only.
                self.lifecycle.close()
            result = self._result()
        except BaseException as error:
            return self._terminal_failure(error)
        return super()._persist(result)


class _FiniteLifecycle(ipc._IpcLifecycle):
    def __init__(self, guardian, descriptor):
        self.guardian = guardian
        self.commit_event = threading.Event()
        self.parent_live = threading.Event()
        self.valid_stop = False
        self.closed = False
        super().__init__(descriptor, self._deadline,
            profile_validator=self._verify_profile, status_provider=self._status)
        if self.parent.alive():
            self.parent_live.set()

    def _verify_profile(self):
        g = self.guardian
        fp.bind_manifest(g.manifest, pins=fp.PINS)
        identity = fs._read(g.run_dir/'identity.json')
        if (fs._digest(g.manifest) != self.descriptor['profile_digest'] or
                identity['run'] != str(g.run_dir) or
                identity['lifecycle'] != g.index or
                identity['manifest_sha256'] != self.descriptor['profile_digest']):
            raise ValueError('finite_bootstrap_profile_mismatch')

    def _deadline(self, resumed_at):
        if type(self.guardian.index) is not int or self.guardian.index not in (1, 2):
            raise ValueError('finite_lifecycle_index')
        return resumed_at + (3600 if self.guardian.index == 1 else 900)

    def _authorize_event(self, event):
        try:
            ipc._match_identity(self.descriptor['parent'], event['peer'])
            return self.parent.alive()
        except (ValueError, KeyError, TypeError):
            return False

    def _handoff_fields(self):
        session = self.guardian.http
        digest = session.readiness_sha256 if session is not None else None
        if (not isinstance(digest, str) or len(digest) != 64 or
                not session.done.is_set() or session.result.get('success') is not True):
            raise ValueError('finite_readiness_unbound')
        return dict(finite_readiness_sha256=digest,
                    finite_workload_sha256=WORKLOAD_SHA256)

    def _status(self):
        result = service_lifecycle._snapshot(self.guardian)
        if self.guardian.http is not None:
            result.update(self.guardian.http.status())
        else:
            result.update(finite_complete=False, finite_state='pre_resume')
        return result

    def poll(self, now):
        if not self.parent.alive():
            self.parent_live.clear()
            self.failed = True
            self.guardian.cancel.set()
        request = super().poll(now)
        session = self.guardian.http
        if request == 'stop':
            self.valid_stop = (session is not None and session.complete()
                               and self.parent_live.is_set() and self.committed)
            if not self.valid_stop:
                self.guardian.cancel.set()
            return 'stop'
        if request is not None:
            self.guardian.cancel.set()
            return request
        if self.committed:
            self.commit_event.set()
        if session is not None and session.done.is_set() and session.failure is not None:
            raise ValueError('finite_session_failed')
        return None

    def close(self):
        if self.closed:
            return
        super().close()
        self.closed = True


def _run_guardian(descriptor, *, guardian=None):
    g = _FiniteGuardian() if guardian is None else guardian
    life = _FiniteLifecycle(g, descriptor)
    g.lifecycle = life
    service_lifecycle._install_sampler(g)
    try:
        result = g.run()
    finally:
        # Reattempt retained native cleanup if an earlier close was unconfirmed.
        # A failed close never grants successful evidence publication.
        try:
            life.close()
        except BaseException as error:
            result = g._terminal_failure(error)
    return result
