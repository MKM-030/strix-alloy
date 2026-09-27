"""Foreground, fixed-profile, single-attempt native smoke guardian.

Only ``run`` can create a child. Private dependency seams support CPU tests;
the CLI has no path, arithmetic, environment, retry or qualification override.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import ntpath
import os
from pathlib import Path
import secrets
import socket
import threading
import time
import uuid

from . import operator_probe as probe
from . import operator_store, smoke_store, smoke_policy as policy, smoke_http
from . import service_lifecycle, service_store
from .operator_policy import Frame, GPU_FIELDS, MAX_QUERY_SECONDS
from .telemetry import collect_snapshot
from .winjob import OwnedProcess

POLL_SECONDS = 0.05
QUERY_INTERVAL = 1.0
STARTUP_SECONDS = 480.0
LIFETIME_SECONDS = 600.0
CLEANUP_SECONDS = 10.0
RECOVERY_SECONDS = 60.0


def utcnow():
    return datetime.now(timezone.utc)


def fixed_argv(secret):
    p = smoke_store.PINS
    return [str(p.build/p.executable_name), 'serve', '--host', '127.0.0.1',
        '--port', '8836', '--sessions', '1', '--max-connections', '3',
        '--max-request-bytes', '16384', '--api-key', secret, 'llm', '--model',
        str(p.first_shard), '--served-model-name', 'gufo-flash-next', '--context',
        '4096', '--max-tokens', '64', '--think', 'off', '--speculative', 'off',
        '--max-pending', '1', '--max-pending-per-client', '1',
        '--request-timeout-ms', '60000', '--max-output-bytes', '1048576']


def check_port():
    """A short exclusive bind check, never a request to an existing listener."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('127.0.0.1', 8836))
    except OSError as error:
        raise ValueError('smoke_port_unavailable') from error


def _redact(value, secret):
    if isinstance(value, str):
        return value.replace(secret, '[REDACTED]') if secret else value
    if isinstance(value, dict):
        return {_redact(k, secret): _redact(v, secret) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v, secret) for v in value]
    return value


class _QueryEntry:
    """Registered before construction, including an unstarted/failed worker."""
    def __init__(self, phase, proof):
        self.phase, self.proof = phase, deepcopy(proof)
        self.query = None
        self.frame = None
        self.logged = False
        self.measured = False
        self.pending_after_exit = False
        self._started = time.monotonic()
        self._unknown_done = threading.Event()

    @property
    def started(self):
        return self.query.started if self.query is not None else self._started

    @property
    def done(self):
        return self.query.done if self.query is not None else self._unknown_done

    def poll(self):
        if self.query is None:
            raise RuntimeError('collector_construction_unconfirmed')
        value = self.query.poll()
        if value is not None:
            self.frame = value
        return value


def _historical_frame(frame, proof, identity, query_start):
    """Scope only a query begun with live retained-handle proof, never recovery."""
    snapshot = deepcopy(frame.snapshot)
    annotation = dict(status='not_excluded', excluded_pid=None)
    if proof is not None:
        captured = proof.get('identity', {})
        if (proof.get('status') != 'verified' or identity is None
                or captured.get('pid') != identity.get('pid')
                or captured.get('creation_time_100ns') != identity.get('creation_time_100ns')
                or ntpath.normcase(ntpath.normpath(captured.get('executable', ''))) !=
                   ntpath.normcase(ntpath.normpath(identity.get('executable', '')))
                or proof.get('verified_monotonic', float('inf')) > query_start):
            raise ValueError('historical_ownership_unverified')
        pids = snapshot.get('other_inference_pids')
        excluded = None
        if isinstance(pids, list) and identity['pid'] in pids:
            pids.remove(identity['pid'])
            excluded = identity['pid']
        annotation = dict(status='historical_query_start', excluded_pid=excluded,
            identity=deepcopy(captured), verified_monotonic=proof['verified_monotonic'])
    snapshot['owned_inventory_proof'] = annotation
    return replace(frame, snapshot=snapshot)


def _rising_residual(frames):
    """Reject a sustained rising residual even inside the recovery tolerance."""
    if len(frames) != 5:
        return False
    for key in (*GPU_FIELDS, 'host_committed_bytes', 'available_physical_bytes'):
        sign = -1 if key == 'available_physical_bytes' else 1
        values = [sign*f.snapshot[key] for f in frames]
        if values[-1] > values[0] and all(a <= b for a, b in zip(values, values[1:])):
            return True
    return False


class _Guardian:
    def __init__(self, *, store=smoke_store, owned_factory=None, query_factory=None,
                 http_start=None, collect=collect_snapshot, port_check=check_port,
                 policy_module=policy, argv_builder=fixed_argv,
                 profile_id=smoke_store.PROFILE_ID, lifecycle=None):
        self.store = store
        self.lifecycle = lifecycle
        self.ready = False
        self.stop_requested = False
        self.lifetime_deadline = None
        self.policy, self.argv_builder, self.profile_id = policy_module, argv_builder, profile_id
        self.owned_factory = OwnedProcess if owned_factory is None else owned_factory
        self.query_factory = probe.Query if query_factory is None else query_factory
        self.http_start = smoke_http.start_smoke if http_start is None else http_start
        self.collect, self.port_check = collect, port_check
        self.phase = 'static'
        self.entries = []
        self.baseline_complete = False
        self.collector_queries = 0
        self.summarized_queries = 0
        self.failures = []
        self.manifest = self.profile = self.original = self.current = None
        self.runtime_baseline = None
        self.run_dir = self.child = self.identity = self.http = self.inspection = None
        self.http_requested = self.inspection_requested = False
        self.secret = ''
        self.cancel = threading.Event()
        self.attempt_started = False
        self.resumed_at = None
        self.evidence_ok = True
        self.collector_deadline_confirmed = True
        self.http_result = None
        self.module_result = None
        self.runtime_samples = 0
        self.peaks = {}
        self.largest_gap = 0.0
        self.largest_sample_age = 0.0
        self.largest_query = 0.0
        self.recovery_samples = []
        self.exited = self.recovered = False
        self.recovery_deadline = None
        self.exit_code = None

    def _fail(self, error):
        self.failures.append(_redact(type(error).__name__+':'+str(error), self.secret))

    def _write(self, name, value):
        try:
            operator_store.atomic_json(self.run_dir/name, _redact(value, self.secret))
        except BaseException:
            self.evidence_ok = False
            raise

    def _phase(self, phase):
        self.phase = phase
        self._write('phase.json', dict(phase=phase, monotonic=time.monotonic()))

    def _decision(self, phase, frame, decision):
        record = dict(phase=phase, query_start=frame.query_start,
                      decision=decision, decided_monotonic=time.monotonic())
        try:
            with (self.run_dir/'decisions.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(_redact(record, self.secret), allow_nan=False)+'\n')
                stream.flush()
        except BaseException:
            self.evidence_ok = False
            raise
        if not decision['allowed']:
            raise ValueError(phase+':'+','.join(decision['reasons']))

    def _query(self, collect, proof=None):
        if self.entries and not self.entries[-1].done.is_set():
            raise RuntimeError('collector_overlap')
        self._prune_entries()
        entry = _QueryEntry(self.phase, proof)
        self.entries.append(entry)
        self.collector_queries += 1
        entry.query = self.query_factory(collect)
        return entry

    def _prune_entries(self):
        if not self.baseline_complete or not self.entries: return
        retained = []
        for entry in self.entries:
            if (entry is self.entries[-1] or entry.pending_after_exit
                    or any(entry.frame is frame for frame in self.recovery_samples)
                    or not (entry.done.is_set() and entry.measured and entry.logged)):
                retained.append(entry)
            else:
                self.summarized_queries += 1
        self.entries = retained

    def _sync_telemetry(self):
        # probe.log_frame flushes but does not fsync. Entries become discardable
        # only after this separate durable barrier succeeds, including baseline.
        try:
            with (self.run_dir/'telemetry.jsonl').open('a', encoding='utf-8') as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            self.evidence_ok = False
            raise

    def _proof(self, frame):
        proof = self.policy.owned_inventory_frame(frame, self.child).snapshot['owned_inventory_proof']
        proof['verified_monotonic'] = time.monotonic()
        return proof

    def _collect_one(self, phase, *, owned=False):
        self._phase(phase)
        previous = self.entries[-1].started if self.entries else None
        # Capture live proof after cadence wait, directly before constructing query.
        def factory(collect):
            proof = self._proof(self.entries[-1].frame) if owned else None
            return self._query(collect, proof)
        try:
            value = probe.collect_one(self.collect, self.run_dir/'telemetry.jsonl', phase,
                                      previous, query_factory=factory)
        except OSError as error:
            # Query wraps collector exceptions; TimeoutError is an OSError too,
            # but says nothing about evidence writes.
            if not isinstance(error, TimeoutError): self.evidence_ok = False
            raise
        self._sync_telemetry()
        self.entries[-1].logged = True
        self._measure(self.entries[-1])
        self._prune_entries()
        return value

    def _measure(self, entry):
        end = getattr(entry.query, 'ended', None)
        duration = (end if entry.done.is_set() and end is not None else time.monotonic())-entry.started
        self.largest_query = max(self.largest_query, duration)
        if duration > MAX_QUERY_SECONDS:
            self.collector_deadline_confirmed = False
        if entry.done.is_set(): entry.measured = True

    def _log(self, entry, phase):
        try:
            probe.log_frame(self.run_dir/'telemetry.jsonl', entry.frame, phase)
            self._sync_telemetry()
            entry.logged = True
            self._measure(entry)
        except BaseException:
            self.evidence_ok = False
            raise

    def _admit(self, frame, *, owned=False):
        scoped = self.policy.owned_inventory_frame(frame, self.child) if owned else frame
        result = self.policy.admission_decision(self.profile, self.runtime_baseline or self.original, scoped,
                                          now=time.monotonic(), now_utc=utcnow())
        self._decision(self.phase, frame, result)

    def _prepared_recheck_kwargs(self):
        return (dict(prepared_run=self.run_dir)
                if isinstance(self.store, service_store.InstalledStore) else {})

    def _before_begin(self, frame):
        return None

    def _immutable_terminal(self):
        return isinstance(self.store, service_store.InstalledStore)

    def _prelaunch(self):
        self.manifest = self.store.verify_static()
        if self.manifest.get('profile') != self.profile_id:
            raise ValueError('guardian_profile_mismatch')
        self.profile = self.policy.profile_from_manifest(self.manifest)
        self.original = self.store.load_original_operator_baseline()
        env = operator_store.child_environment(dict(os.environ))
        self.port_check()
        self.run_dir = self.store.EVIDENCE/(utcnow().strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
        self.run_dir.mkdir()
        self._phase('baseline')
        try:
            self.current, last = probe.collect_baseline(self.collect,
                self.run_dir/'telemetry.jsonl', query_factory=self._query)
        except OSError as error:
            if not isinstance(error, TimeoutError): self.evidence_ok = False
            raise
        self._sync_telemetry()
        for entry in self.entries:
            entry.logged = True
            self._measure(entry)
        frames = [e.frame for e in self.entries if e.phase == 'baseline']
        self.runtime_baseline = self.policy.stricter_runtime_baseline(self.original, self.current)
        # Collected frames precede current.last_end: validate them against the
        # original numeric limits at their own captured validation times.
        reasons = list(dict.fromkeys(reason for frame in frames
            for reason in self.policy.frame_numeric_reasons(self.profile, self.original, frame,
                now=frame.query_end, now_utc=frame.validated_utc)))
        if _rising_residual(frames[-5:]): reasons.append('rising_residual')
        if reasons: raise ValueError('original_baseline:'+','.join(reasons))
        self._write('baseline.json', dict(original=asdict(self.original), current=asdict(self.current),
            effective=asdict(self.runtime_baseline), current_kind='observed_current_baseline',
            effective_kind='synthetic_stricter_runtime_limits'))
        self.baseline_complete = True
        self._prune_entries()
        preparing = self._prepared_recheck_kwargs()
        self.store.recheck_static(self.manifest, **preparing)
        self.port_check()
        final = self._collect_one('final_precreate')
        self.store.recheck_static(self.manifest, **preparing)
        self._admit(final)
        self._before_begin(final)
        # The permanent marker is consumed even if any subsequent setup fails.
        try:
            self.store.begin_run(self.run_dir, self.manifest, self.original)
        except OSError:
            self.evidence_ok = False
            raise
        self.attempt_started = True
        self.secret = secrets.token_urlsafe(32)
        self._write('argv.json', self.argv_builder(self.secret))
        self.port_check()
        self.store.recheck_static(self.manifest, current_run=self.run_dir)
        # Setup and evidence writes must not consume the final frame's age budget.
        final = self._collect_one('final_precreate')
        # Catch static identity/marker changes during the replacement collection.
        self.store.recheck_static(self.manifest, current_run=self.run_dir)
        self._admit(final)  # Account for begin, stamps and evidence I/O before create.
        reasons = self.policy.admission_reasons(self.profile, self.runtime_baseline or self.original, final,
                                           now=time.monotonic(), now_utc=utcnow())
        if reasons: raise ValueError('pre_create:'+','.join(reasons))
        try:
            self.child = self.owned_factory(self.argv_builder(self.secret), cwd=self.store.BUILD,
                env=env, stdout_path=self.run_dir/'stdout.log', stderr_path=self.run_dir/'stderr.log')
        except BaseException as error:
            self.child = getattr(error, 'owner', None)
            raise
        self.identity = deepcopy(self.child.identity)
        self.policy.owned_inventory_frame(final, self.child)
        self._write('owned.json', self.identity)
        if self.lifecycle is not None:
            self.lifecycle.on_started(self.run_dir, deepcopy(self.identity), self.secret)
        final = self._collect_one('final_preresume', owned=True)
        self._admit(final, owned=True)
        self.store.recheck_static(self.manifest, current_run=self.run_dir)
        self.port_check()
        self._phase('resuming')
        self._admit(final, owned=True)
        resumed_at = time.monotonic()
        self.lifetime_deadline = (resumed_at+LIFETIME_SECONDS if self.lifecycle is None
                                  else self.lifecycle.deadline(resumed_at))
        if self.lifecycle is not None:
            service_lifecycle._validate_deadline(self.lifetime_deadline, time.monotonic())
        if isinstance(self.store, service_store.InstalledStore):
            if self.lifecycle is None or self.lifetime_deadline != service_lifecycle._qualified_deadline(self.manifest, resumed_at):
                raise ValueError('service_deadline_qualification_mismatch')
        # Decision writes themselves can age a sample; final check performs no I/O.
        scoped = self.policy.owned_inventory_frame(final, self.child)
        reasons = self.policy.admission_reasons(self.profile, self.runtime_baseline or self.original, scoped,
                                           now=time.monotonic(), now_utc=utcnow())
        if reasons: raise ValueError('pre_resume:'+','.join(reasons))
        if self.lifecycle is not None:
            service_lifecycle._validate_deadline(self.lifetime_deadline, time.monotonic())
        self.resumed_at = resumed_at
        self.child.resume()
        self.http_requested = True
        self.http = self.http_start(api_key=self.secret,
            startup_deadline=self.resumed_at+STARTUP_SECONDS,
            lifetime_deadline=self.lifetime_deadline, cancel=self.cancel)
        self._phase('serving_attempt')
        return final

    def _runtime(self, frame):
        return self.policy.runtime_decision(self.profile, self.runtime_baseline or self.original, frame, self.child,
                                       now=time.monotonic(), now_utc=utcnow())

    def _peak(self, frame):
        s, base = frame.snapshot, self.original
        deltas = dict(physical_fall_bytes=base.available_min-s['available_physical_bytes'],
                      host_committed_rise_bytes=s['host_committed_bytes']-base.committed_max)
        deltas.update({k:s[k]-v for k,v in zip(GPU_FIELDS, base.gpu_max)})
        for key, value in deltas.items():
            self.peaks[key] = max(self.peaks.get(key, 0), value)

    def _observe_inspection(self):
        if self.inspection is None: return
        self.module_result = self.inspection.snapshot(now=time.monotonic())
        if self.inspection.done.is_set():
            if self.module_result.get('status') != 'verified':
                raise ValueError('module_inspection:'+str(self.module_result.get('status')))
            if not self.inspection.duplicate_closed.is_set():
                raise ValueError('module_duplicate_unclosed')
        elif time.monotonic() >= self.inspection.deadline:
            raise TimeoutError('module_inspection_timeout')

    def _monitor(self, last):
        pending = None
        while True:
            now = time.monotonic()
            if now >= self.lifetime_deadline:
                raise TimeoutError('lifetime_timeout')
            if self.child.wait(0):
                self.exit_code = self.child.exit_code()
                raise RuntimeError('child_exited_before_completion')
            if pending is not None:
                self._measure(pending)
                frame = pending.poll()
                if frame is not None:
                    self._log(pending, 'serving_attempt')
                    decision = self._runtime(frame)
                    # Include a valid pressure-breach sample in observed lower-bound
                    # peaks, but exclude malformed, stale or unowned observations.
                    numeric_reasons = ('runtime_physical_floor', 'commit_floor',
                                       'physical_envelope', 'commit_envelope')
                    if all(r in numeric_reasons or r.startswith('gpu_envelope:')
                           for r in decision['reasons']):
                        self.runtime_samples += 1
                        self._peak(frame)
                    self._decision('serving_attempt', frame, decision)
                    self.largest_gap = max(self.largest_gap,
                        frame.snapshot['captured_monotonic']-last.snapshot['captured_monotonic'])
                    last = frame
                    pending = None
                    if self.inspection is None:
                        self.inspection_requested = True
                        self.inspection = self.child.inspect_modules(app_local_dir=self.store.BUILD)
            # Recheck actual sample age and owner on every tick, independently of HTTP.
            self.largest_sample_age = max(self.largest_sample_age,
                time.monotonic()-last.snapshot['captured_monotonic'])
            result = self._runtime(last)
            if not result['allowed']:
                self._decision('serving_attempt', last, result)
            self._observe_inspection()
            if self.lifecycle is not None:
                request = self.lifecycle.poll(time.monotonic())
                if time.monotonic() >= self.lifetime_deadline:
                    raise TimeoutError('lifetime_timeout')
                # A control result never supersedes freshness or live ownership.
                result = self._runtime(last)
                if not result['allowed']:
                    self._decision('serving_attempt', last, result)
                if request == 'handoff_failed':
                    raise RuntimeError('handoff_failed')
                if request == 'stop':
                    self.stop_requested = True
                    return
                if request is not None:
                    raise ValueError('invalid_lifecycle_request')
            if not self.ready and self.http.done.is_set():
                self.http_result = _redact(self.http.result, self.secret)
                if not isinstance(self.http_result, dict) or self.http_result.get('success') is not True:
                    raise ValueError('http:'+str(self.http_result.get('error') if isinstance(self.http_result, dict) else 'invalid_result'))
                if self.inspection is not None and self.inspection.done.is_set():
                    if self.lifecycle is None: return
                    self.lifecycle.on_ready(dict(run=str(self.run_dir), profile=self.profile_id,
                        identity=deepcopy(self.identity), runtime_samples=self.runtime_samples,
                        captured_monotonic=last.snapshot['captured_monotonic'],
                        observed_monotonic=time.monotonic(), lifetime_deadline=self.lifetime_deadline))
                    self.ready = True
            if pending is None and now-self.entries[-1].started >= QUERY_INTERVAL:
                pending = self._query(self.collect, self._proof(last))
            time.sleep(POLL_SECONDS)

    def _drain(self, entry):
        entry.pending_after_exit = True
        # Never grant a fresh ownership proof after close, or extend the query deadline.
        try:
            while not entry.done.is_set() and time.monotonic() <= entry.started+MAX_QUERY_SECONDS:
                entry.poll()
                time.sleep(POLL_SECONDS)
            self._measure(entry)
            if entry.done.is_set():
                raw = getattr(entry.query, 'value', None)
                if isinstance(raw, Frame): entry.frame = raw
                if entry.frame is not None and not entry.logged:
                    self._log(entry, 'pending_after_exit')
                    scoped = _historical_frame(entry.frame, entry.proof, self.identity, entry.started)
                    reasons = self.policy.frame_numeric_reasons(self.profile, self.runtime_baseline or self.original, scoped,
                        now=entry.frame.query_end, now_utc=entry.frame.validated_utc)
                    self._decision('pending_after_exit', entry.frame, dict(allowed=not reasons,
                        reasons=reasons, owned_inventory_proof=scoped.snapshot['owned_inventory_proof']))
                entry.poll()  # Preserve timeout/error even when a raw frame was recoverable.
            else:
                self.collector_deadline_confirmed = False
                raise TimeoutError('active_query_timeout;collector_still_active')
        except BaseException as error:
            self._fail(error)

    def _workers_terminal(self):
        return (self._http_terminal() and self._inspection_terminal() and
                (self.inspection is None or self.inspection.duplicate_closed.is_set()))

    def _http_terminal(self):
        return not self.http_requested or (self.http is not None and self.http.done.is_set())

    def _inspection_terminal(self):
        return not self.inspection_requested or (self.inspection is not None and self.inspection.done.is_set())

    def _cleanup(self):
        deadline = time.monotonic()+CLEANUP_SECONDS
        self.cancel.set()
        if self.http is not None: self.http.cancel.set()
        # Stop first: no HTTP/inspection wait or telemetry drain before Job close.
        if self.child is not None:
            try:
                if self.identity is None: self.identity = deepcopy(self.child.identity)
                self.child.close(timeout_ms=10000)
                self.exited = True
                self.recovery_deadline = time.monotonic()+RECOVERY_SECONDS
                self.exit_code = self.child.exit_code()
            except BaseException as error:
                self._fail(error)
        else:
            self.exited = True  # OwnedProcess constructor without owner confirmed cleanup.
            self.recovery_deadline = time.monotonic()+RECOVERY_SECONDS
        for entry in self.entries:
            if not entry.logged or not entry.done.is_set(): self._drain(entry)
        while not self._workers_terminal() and time.monotonic() < deadline:
            time.sleep(min(POLL_SECONDS, deadline-time.monotonic()))
        # A collector may terminate while waiting for another worker. Preserve
        # its now-available raw evidence without extending its original deadline
        # or reversing the already-unconfirmed collector cleanup decision.
        for entry in self.entries:
            if entry.done.is_set() and not entry.logged: self._drain(entry)
        if self.http is not None and self.http.done.is_set():
            self.http_result = _redact(self.http.result, self.secret)
        if self.inspection is not None:
            self.module_result = self.inspection.snapshot(now=time.monotonic())
        if not self._workers_terminal(): self._fail(RuntimeError('worker_cleanup_unconfirmed'))
        if self.run_dir is None:
            self.recovered = True  # No telemetry or owned-process activity occurred.
            return
        try:
            self._phase('shutdown')
            if (self.exited and self._workers_terminal() and
                    self.collector_deadline_confirmed and
                    all(e.done.is_set() for e in self.entries)):
                self._recover()
        except BaseException as error:
            self._fail(error)
        if not self.recovered: self._fail(RuntimeError('recovery_unconfirmed'))

    def _recover(self):
        deadline = self.recovery_deadline
        while time.monotonic() < deadline:
            # Do not start a query whose original maximum duration cannot fit.
            earliest = max(time.monotonic(), self.entries[-1].started+QUERY_INTERVAL) if self.entries else time.monotonic()
            if earliest+MAX_QUERY_SECONDS > deadline: break
            try:
                value = self._collect_one('recovery')
                if time.monotonic() > deadline: break
                reasons = self.policy.frame_numeric_reasons(self.profile, self.runtime_baseline or self.original, value,
                    now=time.monotonic(), now_utc=utcnow())
                if reasons:
                    self.recovery_samples = []
                    continue
                self.recovery_samples = (self.recovery_samples+[value])[-5:]
                reasons = self.policy.recovery_reasons(self.current or self.original, self.recovery_samples)
                if _rising_residual(self.recovery_samples): reasons.append('rising_residual')
                if not reasons:
                    self.recovered = True
                    return
            except BaseException:
                # Capture the query even when finish_query / logging raises.
                if self.entries and not self.entries[-1].logged: self._drain(self.entries[-1])
                raise

    def _result(self):
        collector_terminal = all(e.done.is_set() for e in self.entries)
        clean = (self.exited and collector_terminal and self.collector_deadline_confirmed
                 and self._workers_terminal() and self.recovered and self.evidence_ok)
        return _redact(dict(profile=self.profile_id,
            success=not self.failures and clean and self.http_result is not None
                    and self.http_result.get('success') is True
                    and (self.lifecycle is None or (self.ready and self.stop_requested)),
            failure=';'.join(self.failures) or None,
            run=str(self.run_dir) if self.run_dir else None,
            owned_exit_confirmed=self.exited, exit_code=self.exit_code, identity=self.identity,
            collector_terminal=collector_terminal,
            collector_cleanup_confirmed=collector_terminal and self.collector_deadline_confirmed,
            http_terminal=self._http_terminal(),
            inspection_terminal=self._inspection_terminal(),
            inspection_duplicate_closed=not self.inspection_requested or (
                self.inspection is not None and self.inspection.duplicate_closed.is_set()),
            cleanup_confirmed=clean, evidence_write_confirmed=self.evidence_ok,
            original_baseline=asdict(self.original) if self.original else None,
            current_baseline=asdict(self.current) if self.current else None,
            runtime_baseline=asdict(self.runtime_baseline) if self.runtime_baseline else None,
            runtime_baseline_kind='synthetic_stricter_runtime_limits',
            manifest=self.manifest, http=self.http_result, module_inspection=self.module_result,
            resumed_monotonic=self.resumed_at, recovery_samples=len(self.recovery_samples),
            runtime_samples=self.runtime_samples,
            collector_queries=self.collector_queries,
            collector_completed_queries=self.summarized_queries+sum(e.done.is_set() for e in self.entries),
            collector_retained_queries=len(self.entries),
            service_ready=self.ready, stop_requested=self.stop_requested,
            runtime_phase='serving_attempt; readiness/POST progress not exposed',
            runtime_peak_evidence='sampled_lower_bound' if self.runtime_samples else 'unknown',
            sampled_peak_deltas=self.peaks, sampled_peak_delta_baseline='original_operator_baseline',
            allowance_bytes=dict(self.profile.envelope) if self.profile else None,
            largest_query_seconds=self.largest_query, largest_sample_gap_seconds=self.largest_gap,
            largest_sample_age_seconds=self.largest_sample_age,
            model_payload_hash_limit='Pinned GGUF metadata only; tensor payloads not fully hashed',
            child_output_review='Required before sharing stdout/stderr; source inspection is not a runtime log audit'), self.secret)

    def _persist(self, result):
        if self.run_dir is None: return result
        try:
            if self.attempt_started:
                self.store.finish_run(self.run_dir, result)
            else:
                self._write('result.json', result)
            if not result['cleanup_confirmed']:
                latch = self.store.EVIDENCE/'incomplete.json'
                if not latch.exists():
                    operator_store.atomic_json(latch, dict(run=str(self.run_dir),
                        phase='cleanup_unconfirmed', original_baseline=asdict(self.original)))
        except BaseException as error:
            result = self._terminal_failure(error)
        return result

    def _terminal_failure(self, error):
        self.evidence_ok = False
        self._fail(error)
        result = self._result()
        if self.run_dir is None: return result
        # Preserve immutable installed terminal evidence, even if finish_run
        # wrote it before failing to retire the latch. Never erase to continue.
        try:
            latch = self.store.EVIDENCE/'incomplete.json'
            if not latch.exists():
                operator_store.atomic_json(latch, dict(run=str(self.run_dir), phase='evidence_write_failed'))
            if self._immutable_terminal():
                service_store._exclusive_json(self.run_dir/('result-failure-'+uuid.uuid4().hex+'.json'), result)
            else:
                self._write('result.json', result)
        except BaseException:
            pass  # The returned result remains explicitly unconfirmed.
        return result

    def run(self):
        try:
            with operator_store.exclusive(operator_store.EVIDENCE):
                with operator_store.exclusive(self.store.EVIDENCE):
                    try:
                        self._monitor(self._prelaunch())
                    except BaseException as error:
                        self._fail(error)
                    finally:
                        self._cleanup()
                    result = self._persist(self._result())
                    if self.lifecycle is not None:
                        try:
                            self.lifecycle.on_result(deepcopy(result))
                        except BaseException as error:
                            result = self._terminal_failure(error)
                    return result
        except BaseException as error:
            self._fail(error)
            return self._result()


def status(*, print_only=False):
    """Bounded allowlisted summaries; never create a directory, lock or process."""
    result = dict(profile=smoke_store.PROFILE_ID, argv=fixed_argv('[REDACTED]'),
        bounds=dict(smoke_store.BOUNDS), source=smoke_store.PINS.source_commit,
        model_revision=smoke_store.PINS.model_revision, admitted=False,
        admission='requires_fresh_run_baseline')
    root = smoke_store.EVIDENCE
    for filename in ('attempt.json', 'incomplete.json'):
        path = root/filename
        if not path.exists():
            result[filename] = dict(present=False)
            continue
        try:
            data = operator_store.read_json(path)
            run = Path(data['run']).resolve()
            if run.parent != root.resolve(): raise ValueError('invalid_run')
            result[filename] = dict(present=True, state_valid=True)
        except (OSError, ValueError, TypeError, KeyError):
            result[filename] = dict(present=True, state_valid=False)
    if print_only:
        try:
            smoke_store.verify_static()
            operator_store.child_environment(dict(os.environ))
            check_port()
            result['static_qualified'] = True
        except Exception as error:
            result['static_qualified'] = False
            # Errors here precede secret creation and come only from pinned checks.
            result['refused'] = type(error).__name__+':'+str(error)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fixed one-attempt AR4k guardian')
    parser.add_argument('command', choices=('run', 'status', 'print-only'))
    args = parser.parse_args(argv)
    if args.command != 'run':
        result = status(print_only=args.command == 'print-only')
        print(json.dumps(result, allow_nan=False))
        return 2 if result.get('static_qualified') is False else 0
    if os.name != 'nt': parser.error('Windows required')
    result = _Guardian().run()
    print(json.dumps(result, allow_nan=False))
    return 0 if result['success'] else 2 if result['resumed_monotonic'] is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
