# GUFO finite guardian and authenticated IPC adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Code snippets are starting implementations for scoped RED/GREEN refinement; preserve the normative safety and evidence contracts. This plan grants no runtime qualification.

**Goal:** Reuse the existing owned-process guardian for one finite lifecycle while preserving one live ledger/transport across readiness, authenticated handoff and continuation, and publish success only after complete workload coverage, actual worker termination, authenticated stop, owned exit and recovery.

**Architecture:** Introduce three default-preserving guardian hooks and two default-preserving IPC hooks. A finite-only session owns readiness and continuation in one process; a finite-only guardian subclass binds admission, lifetime, terminal evidence and recovery to the prepared finite store. The existing pressure loop, fresh admission checks and Windows Job Object implementation remain the execution mechanism.

**Tech Stack:** Python standard library, `unittest`, temporary evidence, injected fake process/collector/IPC/transport, existing `FiniteStore`, `BoundPolicy`, `Ledger`, `FiniteTransport`, `ListeningHint` and finite phase contracts.

## Global Constraints

- Planning provenance: private report `gufo-finite-guardian-plan-20260927.md`, SHA256 `754D7CE2F9BEC2E05D5E06A42576E04AEBD9D6382D6D5825A5D6804E876A7D1E`, fully read by the main agent. This executable plan adapts only handoff guidance; predecessor review must pass before implementation.

- Approved design: `C:/Projects/strix-alloy-research/integration/docs/superpowers/specs/2026-09-26-gufo-native-design.md`. No design approval is reopened.
- Later implementation target: `C:/Projects/strix-alloy-research/integration`, branch `codex/gufo-native-integration`. Planning observed HEAD `ab66888e6a3a6a1e04c8dcbe1c65d48f3ea8b288`; the concurrent four phase paths were dirty and were not used as completed implementation.
- Dependencies must be reviewed first: `docs/superpowers/plans/2026-09-27-gufo-finite-phase.md` and `docs/superpowers/plans/2026-09-27-gufo-finite-store.md`. Their interfaces are normative here. This plan does not execute either predecessor.
- Preserve floors **49/24/12 GiB** prelaunch/runtime/commit and envelope **68/4/20 GiB** GPU/additional-host/shared. No policy arithmetic changes or fabricated counters.
- Preserve lifecycle **3600/900 seconds**, readiness **480 seconds**, complete-operation **60 seconds**, POST counts **66/6**, readiness GET cap **240**, models GET count **1**, and a single shared three-socket semaphore. POST 1 is readiness; no extra completion, warmup, retry or replacement.
- Frozen workload SHA256 `30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38`; use `load_workload()`.
- Native source `e6feed7ca52df4661d10434c72a8ea5b5f054bc2`; source tree `7912be2688d6874c0e13f4723aad00a5c3cbe1cf`; runtime `C:/Projects/strix-alloy-research/runtimes/gufo-native-service-header-e6feed7-therock10.2`; runtime variant `service-ar4k-header-v1`; preserve the store plan's binary/model/SDK/controller pins.
- Exactly one finite store profile `ar4k-service-lifecycle-v1`; evidence root `C:/Projects/strix-alloy-research/reports/gufo-service-lifecycle-v1-runs`. Installed service qualification, entrypoints, leases, roots and acceptance remain unchanged.
- Same in-process `Ledger` and `FiniteTransport`, with live `ReturnedReceipt.source` identity, continue across handoff. No disk reconstruction of a client or receipt and no transfer of generation credentials to a second client.
- The parent must remain live before and after handoff until terminal shutdown. A lost ACK is resolved against the exact authenticated run, never by relaunching. Only that authenticated original parent can handoff, commit, inspect or stop the finite lifecycle.
- Default existing guardian locks, single Job Object owner, suspended create/assign/resume, module inspection, owned identity checks, precreate/preresume admission, pressure checks, bounded cleanup and five recovered samples remain in force.
- Synthetic-only implementation verification. No real listener/socket/pipe, process launch, model, GPU, native helper, telemetry collection, collector invocation, recovery operation, persistent system change, D: access, marker/latch mutation outside disposable test roots, installed acceptance, commit or push during this planning task. Commands below are future offline commands only.
- A complete certificate is structural evidence. Pending prose review remains pending. Missing owned counters and per-phase peaks remain explicitly unknown until measured evidence is analyzed; this adapter supplies the exact phase boundaries and sampled telemetry provenance, not invented measurements.

## Boundaries and file map

Paths in the following code tasks are relative to `C:/Projects/strix-alloy-research/integration`.

| File | Responsibility |
| --- | --- |
| `scripts/gufo_control/smoke_guard.py` | Three narrow hooks: prepared-run kwargs, pre-begin admission witness, immutable failure report selection. |
| `scripts/gufo_control/service_ipc.py` | Two default-preserving hooks: per-event authorization and bound handoff fields. |
| `tests/gufo/test_finite_guardian_seams.py` | Synthetic default-preservation and hook ordering tests. |
| `scripts/gufo_control/finite_session.py` | One live readiness/continuation worker graph, same transport and ledger. |
| `scripts/gufo_control/finite_guardian.py` | Finite policy/store/argv, authenticated lifecycle, final evidence binding. No CLI or subprocess spawn. |
| `tests/gufo/test_finite_guardian.py` | Synthetic session, parent lifetime, terminal and persistence tests. |

No edits to phase implementation, startup reader, finite store, installed service, Job Object, telemetry or policy modules are included. If the reviewed phase/store interface differs from its plan, report the exact mismatch before integrating it; do not substitute an invented attribute.

## Task 1: Small shared hooks with unchanged existing defaults

**Consumes:** `_Guardian._prelaunch`, `_terminal_failure`; `_IpcLifecycle.on_ready`, `poll`; existing synthetic `test_smoke_guard.Harness`.

**Produces:** `_Guardian._prepared_recheck_kwargs() -> dict`, `_Guardian._before_begin(frame) -> None`, `_Guardian._immutable_terminal() -> bool`; `_IpcLifecycle._authorize_event(event) -> bool` and `_IpcLifecycle._handoff_fields() -> dict`. Defaults preserve current behavior, including InstalledStore-only handling.

- [ ] **Step 1: Create `tests/gufo/test_finite_guardian_seams.py` with these complete tests.**

```python
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gufo_control import smoke_guard as guard, service_ipc as ipc
from test_smoke_guard import Harness


class GuardianSeamTests(unittest.TestCase):
    def test_default_hooks_leave_smoke_profile_unchanged(self):
        value = guard._Guardian()
        self.assertEqual(value._prepared_recheck_kwargs(), {})
        self.assertIsNone(value._before_begin(object()))
        self.assertFalse(value._immutable_terminal())
        life = object.__new__(ipc._IpcLifecycle)
        self.assertTrue(life._authorize_event({'command': 'stop'}))
        self.assertEqual(life._handoff_fields(), {})

    def test_admission_hook_runs_before_begin_and_create(self):
        base = guard._Guardian
        events = []
        class Hooked(base):
            def _before_begin(self, frame):
                events.append(('admitted', frame, self.current, self.child))
        with tempfile.TemporaryDirectory() as root:
            harness = Harness(root)
            original = harness.store.begin_run
            def begin(*args):
                events.append(('begin',))
                return original(*args)
            harness.store.begin_run = begin
            with patch.object(guard, '_Guardian', Hooked):
                result = harness.run()
            self.assertTrue(result['success'], result)
            self.assertEqual([event[0] for event in events], ['admitted', 'begin'])
            self.assertIsNotNone(events[0][1])
            self.assertIsNotNone(events[0][2])
            self.assertIsNone(events[0][3])
            self.assertEqual(harness.events.count('create'), 1)
            self.assertEqual(result['recovery_samples'], 5)

    def test_hook_refusal_cannot_create_or_consume_attempt(self):
        base = guard._Guardian
        class Refusing(base):
            def _before_begin(self, frame):
                raise ValueError('synthetic_admission_record_failure')
        with tempfile.TemporaryDirectory() as root:
            harness = Harness(root)
            with patch.object(guard, '_Guardian', Refusing):
                result = harness.run()
            self.assertFalse(result['success'])
            self.assertEqual(harness.children, [])
            self.assertNotIn('begin', harness.events)

    def test_immutable_failure_keeps_prior_terminal_bytes(self):
        class Immutable(guard._Guardian):
            def _immutable_terminal(self):
                return True
        with tempfile.TemporaryDirectory() as root:
            run = Path(root) / 'run-1'
            run.mkdir()
            terminal = run / 'result.json'
            terminal.write_bytes(b'{"original":true}\n')
            value = Immutable(store=SimpleNamespace(EVIDENCE=Path(root)))
            value.run_dir = run
            result = value._terminal_failure(ValueError('publication_failed'))
            self.assertFalse(result['success'])
            self.assertEqual(terminal.read_bytes(), b'{"original":true}\n')
            self.assertEqual(len(list(run.glob('result-failure-*.json'))), 1)
            self.assertTrue((Path(root) / 'incomplete.json').exists())
```

- [ ] **Step 2: Confirm RED using only the new synthetic test module.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest test_finite_guardian_seams -v
```

Expected RED: absent hook methods, missing call to the pre-begin hook, or the immutable-result assertion. No real endpoint/process is used.

- [ ] **Step 3: Add the following complete methods inside `_Guardian`.**

```python
    def _prepared_recheck_kwargs(self):
        return (dict(prepared_run=self.run_dir)
                if isinstance(self.store, service_store.InstalledStore) else {})

    def _before_begin(self, frame):
        return None

    def _immutable_terminal(self):
        return isinstance(self.store, service_store.InstalledStore)
```

Replace only the `preparing` assignment in `_prelaunch` with:

```python
        preparing = self._prepared_recheck_kwargs()
```

Insert this line immediately after the first `self._admit(final)` and before `begin_run` (not after the attempt is consumed):

```python
        self._before_begin(final)
```

In `_terminal_failure`, replace only the InstalledStore condition governing the exclusive `result-failure-<uuid>.json` branch:

```python
            if self._immutable_terminal():
```

Retain that branch's existing `service_store._exclusive_json` call. No other `_prelaunch`, `_monitor`, `_cleanup`, `_recover` or `run` code changes are needed.

Add these complete methods inside `_IpcLifecycle`:

```python
    def _authorize_event(self, event):
        return True

    def _handoff_fields(self):
        return {}
```

Inside `poll`, immediately after `command = event['command']` and before the existing `original` assignment, insert:

```python
                if command != 'disconnect' and not self._authorize_event(event):
                    self.server.reply(event, dict(state='refused'))
                    continue
```

Replace the complete final `self.server.reply` expression in `on_ready` with:

```python
        self.server.reply(self.parent_event, dict(state='ready', guardian=self.record['guardian'],
            child=self.record['child'], run=self.record['run'], **self._handoff_fields()), retain=True)
```

Replace only the durable handoff write expression in the existing `commit` branch with:

```python
                    operator_store.atomic_json(self.run_dir/'handoff.json',
                        dict(self.record, state='committed', **self._handoff_fields()))
```

These fields cannot change the envelope, peer checks or committed-state ordering. The finite override returns only two prefixed digest fields. The default remains empty.

- [ ] **Step 4: Confirm GREEN and default preservation.**

```powershell
python -B -m unittest test_finite_guardian_seams test_smoke_guard test_service_lifecycle test_service_ipc.ProtocolTests -v
git diff --check
```

Expected: selected tests PASS. Do not select `test_service_ipc.NativeTests`; those create real native IPC/processes. Review the tiny shared diff independently before Task 2. No commit is performed by this plan-writing task; later execution follows the parent's existing commit authorization.

## Task 2: Finite session, IPC lifetime and pre-publication evidence

**Consumes:** reviewed `FiniteStore.recheck_static(manifest, *, current_run=None, prepared_run=None)`, `FiniteStore.record_admission(run_dir, manifest, current_baseline, frame, *, now, now_utc) -> dict`, `phase_record(run_dir, manifest, lifecycle, coverage_dict) -> dict`; `BoundPolicy(fp.PINS)`; `CoverageCertificate`, `VerifiedHandoff`, `start_readiness`, `readiness_digest`, `run_remaining`; `Ledger`, `FiniteTransport`, `ListeningHint`; Task 1 hooks.

**Produces:** private `finite_guardian._run_guardian(descriptor, *, guardian=None) -> dict`. It runs exactly one admitted finite lifecycle and has no CLI, spawn or retry. Descriptor schema remains `{parent, profile_digest, record_path}`; `profile_digest` is `finite_store._digest(verified_full_manifest)`, not an installed profile digest. Run identity is the guardian-created directory's basename.

- [ ] **Step 1: Create `tests/gufo/test_finite_guardian.py` from the complete module below the production blocks, before creating either production module.**
- [ ] **Step 2: Run RED.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest test_finite_guardian -v
```

Expected: import failure for `finite_session`/`finite_guardian`. If predecessor modules are still missing, finish their reviewed implementation first; do not fake their production interfaces to force this test green.

- [ ] **Step 3: Create `scripts/gufo_control/finite_session.py` with this complete starting implementation.**

```python
"""One in-process finite HTTP worker graph; importing does no I/O."""
from dataclasses import asdict
import threading
import time

from .finite_ledger import Ledger
from .finite_transport import FiniteTransport
from .finite_startup import ListeningHint
from .finite_workload import WORKLOAD_SHA256
from . import finite_phase as phase


class FiniteSession:
    def __init__(self, workload, index, run_dir, *, api_key, resumed_at,
                 startup_deadline, lifetime_deadline, cancel, committed,
                 parent_live):
        if (startup_deadline != resumed_at + 480 or
                lifetime_deadline != resumed_at + (3600 if index == 1 else 900)):
            raise ValueError('finite_session_deadline')
        self.cancel, self.committed, self.parent_live = cancel, committed, parent_live
        self.done = threading.Event()  # readiness notification, not worker termination
        self.ledger = Ledger(run_dir/'ledger', workload, index, run_dir.name,
                             resumed_at, create=True)
        self.transport = FiniteTransport(self.ledger, workload, api_key, cancel=cancel)
        self.readiness = None
        self.readiness_sha256 = None
        self.certificate = None
        self.phase_started = False
        self.failure = None
        self._ready_result = dict(success=False, error='finite_not_ready')
        self.thread = threading.Thread(target=self._work,
            args=(workload, run_dir, startup_deadline, lifetime_deadline),
            daemon=True, name='gufo-finite-session')
        self.thread.start()

    def _work(self, workload, run_dir, startup_deadline, lifetime_deadline):
        try:
            self.readiness = phase.start_readiness(workload, self.ledger,
                self.transport, ListeningHint(run_dir),
                startup_deadline=startup_deadline, lifetime_deadline=lifetime_deadline)
            while self.readiness.thread.is_alive():
                self.readiness.thread.join(.01)
                if self.cancel.is_set() or not self.parent_live.is_set():
                    self.cancel.set()
                if time.monotonic() >= startup_deadline:
                    self.cancel.set()
                    raise ValueError('finite_readiness_join_deadline')
            self.readiness.thread.join(0)
            self.readiness_sha256 = phase.readiness_digest(
                self.readiness, self.ledger, self.transport)
            self._ready_result = dict(self.readiness.result)
            self.done.set()
            while not self.committed.wait(.01):
                if (self.cancel.is_set() or not self.parent_live.is_set() or
                        time.monotonic() >= lifetime_deadline):
                    raise ValueError('finite_handoff_interrupted')
            if self.cancel.is_set() or not self.parent_live.is_set():
                raise ValueError('finite_handoff_interrupted')
            counts = self.ledger.snapshot()['counts']
            handoff = phase.VerifiedHandoff(self.ledger.header['run_id'],
                WORKLOAD_SHA256, self.readiness_sha256, counts['ready'],
                counts['models'], counts['post'], True, True)
            self.phase_started = True
            self.certificate = phase.run_remaining(workload, self.ledger,
                self.transport, handoff, stop_event=self.cancel,
                parent_alive=self.parent_live.is_set)
            if not self.certificate.complete:
                self.failure = self.certificate.failure or 'finite_coverage_incomplete'
        except BaseException as error:
            self.failure = type(error).__name__ + ':' + str(error)
            self.cancel.set()
        finally:
            self.done.set()

    def terminal(self):
        # Join actual threads; done events do not establish termination.
        if self.thread.ident is not None:
            self.thread.join(0)
        if self.readiness is not None:
            self.readiness.thread.join(0)
            if self.readiness.thread.is_alive():
                return False
        if self.thread.is_alive():
            return False
        # An unexpected exception after entering the phase cannot establish
        # whether it left inner wave workers alive. Fail closed indefinitely.
        return (not self.phase_started or (self.certificate is not None and
                                          self.certificate.workers_terminal is True))

    def complete(self):
        return (self.terminal() and self.certificate is not None and
                self.certificate.complete is True and self.failure is None)

    @property
    def result(self):
        if self.failure is not None:
            return dict(success=False, error=self.failure)
        if self.phase_started and not self.thread.is_alive():
            return dict(success=self.complete(), error=None if self.complete()
                        else 'finite_workers_unconfirmed')
        return dict(self._ready_result)

    def status(self):
        complete = self.complete()
        return dict(finite_complete=complete, finite_workers_terminal=self.terminal(),
            finite_readiness_sha256=self.readiness_sha256,
            finite_post_count=(self.certificate.post_count if self.certificate else None),
            finite_state=('complete_awaiting_stop' if complete else
                          'failed' if self.failure else
                          'continuation' if self.phase_started else 'readiness_or_handoff'),
            finite_acceptance='structural_only')

    def coverage(self):
        return asdict(self.certificate) if self.certificate is not None else None
```

The coordinator does no transport work until the child is resumed. It never reopens the ledger after handoff. It may remain a daemon on an unconfirmed stuck worker, but terminal flags stay false and the latch blocks the next lifecycle. Cleanup closes the child's Job Object first; it never waits for this worker before closing that job.

- [ ] **Step 4: Create `scripts/gufo_control/finite_guardian.py` with this complete starting implementation.**

```python
"""Private finite lifecycle adapter. No public CLI, spawning or retry."""
from pathlib import Path
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
```

All static rechecks and both final fresh precreate/preresume checks still execute in the inherited code. Admission recording can age the first frame: `begin_run` checks its age and fails closed; the guardian still recollects and re-admits immediately before creation. There is no overwrite of admission evidence to refresh an already consumed attempt.

The inherited `_Guardian.run` persists before calling `on_result`. The finite override therefore attaches the whole phase record and recovery timestamp in `_persist`/`_result`. `_terminal_failure` uses the immutable hook, retaining a first `result.json` and a separate failure report when the store rejects incomplete success or pointer/latch publication fails. Parent observation of HTTP readiness alone never qualifies either run.

`_FiniteLifecycle.close` occurs before `finish_run`, including cancellation/retirement of pipe operations. The default installed wrapper still has its original close timing. If close fails, terminal failure evidence is retained and the incomplete latch remains; another lifecycle is blocked. A final retry of close cannot turn that failure into a successful result.

- [ ] **Step 5: Use this complete test module for Step 1.**

```python
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from gufo_control import finite_session as session_module
from gufo_control import finite_guardian as fg, finite_phase as phase
from gufo_control import service_ipc as ipc, smoke_guard
from gufo_control.finite_workload import WORKLOAD_SHA256


def certificate(run='run-1', *, complete=True, terminal=True):
    return phase.CoverageCertificate(run, 2,
        tuple(f'post-{n:03d}' for n in range(2, 7)), 1, 1, 6,
        terminal, ((1, 100.0), (6, 101.0)), (), (), False,
        None if complete else 'synthetic_failure', complete)


def wait_until(predicate):
    until = time.monotonic() + 2
    while not predicate():
        if time.monotonic() >= until:
            raise AssertionError('synthetic_worker_timeout')
        time.sleep(.002)


class FakeServer:
    def __init__(self):
        self.events, self.replies = [], []
    def poll(self):
        result, self.events = self.events, []
        return result
    def reply(self, event, value, **kwargs):
        self.replies.append(value)
    def close(self):
        return None


class FiniteGuardianTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_session(self, *, phase_result=None, block_phase=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        ready_thread = threading.Thread(target=lambda: None)
        ready_thread.start()
        ready_thread.join()
        ready_done = threading.Event()
        ready_done.set()
        readiness = SimpleNamespace(thread=ready_thread, done=ready_done,
            result={'success': True}, receipts=())
        ledger = SimpleNamespace(header={'run_id': 'run-1'},
            snapshot=lambda: {'counts': {'ready': 1, 'models': 1, 'post': 1}})
        transport = SimpleNamespace(ledger=ledger)
        calls = []
        def remaining(workload, got_ledger, got_transport, handoff, **kwargs):
            calls.append((got_ledger, got_transport, handoff))
            if block_phase is not None:
                block_phase.wait(1)
            return phase_result or certificate()
        ledger_factory = stack.enter_context(patch.object(session_module, 'Ledger', return_value=ledger))
        transport_factory = stack.enter_context(patch.object(session_module, 'FiniteTransport', return_value=transport))
        stack.enter_context(patch.object(session_module, 'ListeningHint', return_value=object()))
        start = stack.enter_context(patch.object(phase, 'start_readiness', return_value=readiness))
        digest = stack.enter_context(patch.object(phase, 'readiness_digest', return_value='A'*64))
        stack.enter_context(patch.object(phase, 'run_remaining', side_effect=remaining))
        committed, parent, cancel = (threading.Event() for _ in range(3))
        parent.set()
        resumed = time.monotonic()
        value = session_module.FiniteSession(object(), 2, self.root/'run-1',
            api_key='x'*43, resumed_at=resumed, startup_deadline=resumed+480,
            lifetime_deadline=resumed+900, cancel=cancel,
            committed=committed, parent_live=parent)
        def cleanup():
            cancel.set()
            committed.set()
            if block_phase is not None:
                block_phase.set()
            value.thread.join(2)
        self.addCleanup(cleanup)
        wait_until(value.done.is_set)
        return value, committed, parent, calls, ledger_factory, transport_factory, start, digest

    def test_one_client_readiness_then_authenticated_continuation(self):
        value, commit, parent, calls, ledger, transport, start, digest = self.make_session()
        self.assertEqual(calls, [])
        self.assertFalse(value.terminal())
        commit.set()
        wait_until(lambda: not value.thread.is_alive())
        self.assertTrue(value.complete())
        self.assertEqual(ledger.call_count, 1)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(start.call_count, 1)
        self.assertEqual(digest.call_count, 1)
        self.assertIs(calls[0][0], value.ledger)
        self.assertIs(calls[0][1], value.transport)
        self.assertEqual(calls[0][2].readiness_digest, 'A'*64)
        self.assertTrue(calls[0][2].worker_joined)
        self.assertEqual(value.status()['finite_post_count'], 6)

    def test_readiness_done_is_not_terminal_phase_success(self):
        block = threading.Event()
        value, commit, parent, calls, *unused = self.make_session(block_phase=block)
        commit.set()
        wait_until(lambda: bool(calls))
        self.assertTrue(value.done.is_set())
        self.assertFalse(value.terminal())
        self.assertFalse(value.complete())
        block.set()
        wait_until(lambda: not value.thread.is_alive())
        self.assertTrue(value.complete())

    def test_parent_loss_before_commit_never_continues(self):
        value, commit, parent, calls, *unused = self.make_session()
        parent.clear()
        wait_until(lambda: not value.thread.is_alive())
        self.assertEqual(calls, [])
        self.assertFalse(value.complete())
        self.assertTrue(value.cancel.is_set())

    def test_phase_failure_or_unjoined_workers_never_qualifies(self):
        for terminal in (False, True):
            value, commit, parent, calls, *unused = self.make_session(
                phase_result=certificate(complete=False, terminal=terminal))
            commit.set()
            wait_until(lambda: not value.thread.is_alive())
            self.assertFalse(value.complete())
            self.assertEqual(value.terminal(), terminal)

    def make_lifecycle(self, *, complete=False):
        parent_id = dict(pid=7, creation_time_100ns=8, executable='python.exe', user_sid='S-1-test')
        parent = SimpleNamespace(alive=Mock(return_value=True), close=Mock())
        value = SimpleNamespace(index=2, http=SimpleNamespace(
            complete=lambda: complete, failure=None, done=threading.Event(),
            readiness_sha256='A'*64, result={'success': True}), cancel=threading.Event())
        value.http.done.set()
        descriptor = dict(parent=parent_id, profile_digest='b'*64,
                          record_path=str(self.root/'endpoint.json'))
        with patch.object(ipc, '_validate_descriptor', return_value=parent):
            life = fg._FiniteLifecycle(value, descriptor)
        life.server = FakeServer()
        life.run_dir = self.root
        life.record = dict(run_id='c'*32, profile_digest='b'*64,
            guardian=parent_id, child={'pid': 9}, run=str(self.root))
        life.parent_event = {'channel': SimpleNamespace()}
        life.status = {'state': 'running'}
        life.committed = True
        self.addCleanup(life.close)
        return life, value, parent, parent_id

    def test_parent_death_after_handoff_still_fails(self):
        life, guardian, parent, identity = self.make_lifecycle()
        parent.alive.return_value = False
        self.assertEqual(life.poll(time.monotonic()), 'handoff_failed')
        self.assertFalse(life.parent_live.is_set())
        self.assertTrue(guardian.cancel.is_set())

    def test_other_authenticated_same_user_peer_cannot_stop(self):
        life, guardian, parent, identity = self.make_lifecycle(complete=True)
        life.server.events.append(dict(command='stop', channel=object(),
            peer=dict(identity, pid=88)))
        self.assertIsNone(life.poll(time.monotonic()))
        self.assertFalse(life.stopping)
        self.assertEqual(life.server.replies[-1], {'state': 'refused'})

    def test_stop_qualifies_only_after_full_coverage(self):
        for complete in (False, True):
            life, guardian, parent, identity = self.make_lifecycle(complete=complete)
            life.server.events.append(dict(command='stop', channel=object(), peer=identity))
            self.assertEqual(life.poll(time.monotonic()), 'stop')
            self.assertEqual(life.valid_stop, complete)
            self.assertEqual(guardian.cancel.is_set(), not complete)

    def test_exact_deadlines_and_handoff_digest_fields(self):
        life, guardian, parent, identity = self.make_lifecycle()
        self.assertEqual(life.deadline(10), 910)
        guardian.index = 1
        self.assertEqual(life.deadline(10), 3610)
        self.assertEqual(life._handoff_fields(), dict(finite_readiness_sha256='A'*64,
            finite_workload_sha256=WORKLOAD_SHA256))

    def test_admission_and_prepared_directory_are_exact(self):
        g = object.__new__(fg._FiniteGuardian)
        g.run_dir, g.manifest, g.current = self.root, {'bound': True}, object()
        g.store = SimpleNamespace(record_admission=Mock(return_value={'lifecycle': 2}))
        frame = object()
        g._before_begin(frame)
        self.assertEqual(g.index, 2)
        self.assertEqual(g._prepared_recheck_kwargs(), {'prepared_run': self.root})
        args = g.store.record_admission.call_args.args
        self.assertEqual(args[:2], (self.root, g.manifest))
        self.assertIs(args[2], g.current)
        self.assertIs(args[3], frame)
        self.assertTrue(g._immutable_terminal())

    def test_final_result_requires_coverage_and_authenticated_completed_stop(self):
        for complete, valid_stop in ((False, False), (False, True),
                                     (True, False), (True, True)):
            with self.subTest(complete=complete, valid_stop=valid_stop):
                g = object.__new__(fg._FiniteGuardian)
                g.secret = ''
                g.phase_sha256 = 'D'*64
                g.recovery_completed = 123.0
                g.http = SimpleNamespace(complete=lambda: complete,
                    coverage=lambda: {'complete': complete})
                g.lifecycle = SimpleNamespace(valid_stop=valid_stop)
                with patch.object(smoke_guard._Guardian, '_result',
                                  return_value={'success': True, 'failure': None}):
                    result = g._result()
                self.assertEqual(result['success'], complete and valid_stop)
                self.assertEqual(result['finite_phase_sha256'], 'D'*64)
                self.assertEqual(result['finite_recovery_completed_monotonic'], 123.0)
                self.assertIsNone(result['finite_memory']['per_phase_peaks'])

    def test_phase_and_ipc_retirement_precede_store_publication(self):
        order = []
        g = object.__new__(fg._FiniteGuardian)
        g.run_dir, g.manifest, g.index = self.root, {'bound': True}, 2
        g.phase_sha256 = None
        g.http = SimpleNamespace(complete=lambda: True, coverage=lambda: {'live': True})
        g.lifecycle = SimpleNamespace(parent=SimpleNamespace(alive=lambda: True),
            close=lambda: order.append('ipc_closed'))
        g._result = lambda: {'success': True, 'finite_phase_sha256': g.phase_sha256}
        record = {'bound_phase': True}
        with patch.object(fg.fs, 'phase_record', return_value=record), \
             patch.object(fg.fs, '_write', side_effect=lambda *args: order.append('phase_written')), \
             patch.object(smoke_guard._Guardian, '_persist',
                          side_effect=lambda result: (order.append('finish_run'), result)[1]):
            result = g._persist({})
        self.assertEqual(order, ['phase_written', 'ipc_closed', 'finish_run'])
        self.assertEqual(result['finite_phase_sha256'], fg.fs._digest(record))

    def test_unconfirmed_ipc_close_never_calls_finish_run(self):
        g = object.__new__(fg._FiniteGuardian)
        g.http = None
        g.lifecycle = SimpleNamespace(parent=SimpleNamespace(alive=lambda: True),
            close=Mock(side_effect=RuntimeError('pending_io_retained')))
        g._terminal_failure = Mock(return_value={'success': False})
        with patch.object(smoke_guard._Guardian, '_persist') as persist:
            self.assertFalse(g._persist({})['success'])
        persist.assert_not_called()
        g._terminal_failure.assert_called_once()

    def test_fifth_recovered_sample_timestamp_is_recorded_after_recover(self):
        g = object.__new__(fg._FiniteGuardian)
        g.recovered, g.recovery_samples, g.recovery_completed = True, [object()]*5, None
        with patch.object(smoke_guard._Guardian, '_recover'), \
             patch.object(fg.time, 'monotonic', return_value=123.0):
            g._recover()
        self.assertEqual(g.recovery_completed, 123.0)
```

These tests intentionally mock phase internals at the adapter seam; the reviewed phase suite supplies actual receipt/capture/ledger tests, full 66/6 coverage, POST1 readiness, cancellation and wave workers. They do not manufacture production receipts or constitute phase acceptance. The two-way binding of a real certificate to `phase_record` is already in the finite store's test suite and must remain GREEN.

- [ ] **Step 6: Run GREEN and scoped regressions.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest test_finite_guardian test_finite_guardian_seams -v
python -B -m unittest test_finite_profile test_finite_store test_finite_phase test_finite_startup test_finite_ledger test_finite_transport.FiniteTransportTests test_finite_assessment -v
python -B -m unittest test_smoke_guard test_service_lifecycle test_service_ipc.ProtocolTests test_service_store test_benchmark_runtime -v
git diff --check
git diff --stat
```

Expected: selected synthetic tests PASS; exact preceding profile/store test names must exist from their implemented plan. No full `test_service_ipc` invocation, test discovery over the entire GUFO tree or native process/helper tests. Review Task 2 separately, especially session thread return, early stop and pre-persistence ordering. No live run follows from GREEN.

## Minimal next parent interface, explicitly outside these two units

The later public parent/hidden bootstrap task consumes `_run_guardian(descriptor)`. It must implement a fixed-profile hidden invocation without model/path/timeout overrides, write the validated three-field descriptor, use the current interpreter hidden with `CREATE_NO_WINDOW`, and keep that parent alive through the single lifecycle. This plan adds no public command, process creation or two-attempt loop.

The exact protocol is:

1. `FiniteStore.verify_static()` yields the immutable full manifest. Parent pins `fs._digest(manifest)` in the descriptor; `record_path` is an exclusive, non-reparse `endpoint.json` location. It records its full `_process_identity` and retains exact child guardian identity. The hidden guardian revalidates descriptor parent and full admitted manifest.
2. Read the exact published endpoint/control record under the private root, checking guardian identity, child identity, run path and the descriptor digest. Call `ipc.control_request(record, 'handoff', timeout_seconds=490)`. A returned `indeterminate` requires `control_request` status for that exact record; it never authorizes another process start.
3. Poll authenticated `status` with a bounded timeout no greater than remaining lifecycle time. Inspect `handoff_confirmed`, exact run/child/guardian identity and `finite_complete`. The guardian continues all POSTs itself. The parent must not use the written engine credential file to perform readiness or workload HTTP.
4. Once `finite_complete is True`, issue authenticated `stop` for that exact record. An earlier stop remains available as cancellation but is a failed finite attempt. Parent loss after commit is failure. Lifecycle deadlines are fixed regardless of polling or failed status.
5. Wait for the owned guardian's terminal report; validate the linked `current.json`/`identity.json`/`result.json`/`phase-evidence.json` via the finite store history, not a convenient success boolean. Require strict cleanup, five recovery samples, confirmed IPC retirement, no retained incomplete latch and final immutable hashes. Parent stays alive until this result exists.
6. Only then start the separately admitted second lifecycle. Its baseline starts strictly after the first `finite_recovery_completed_monotonic`. No third lifecycle, hidden retry, marker deletion or inferred semantic/installed acceptance.

Actual parent file-path validation, launching, exact-run status resolution, terminal history reading and the two-attempt public orchestration are concrete work for that next task. No source patch in this plan exposes `_run_guardian` to ordinary installed commands.

## Self-review, concrete limitations and frozen handoff

- Approved memory/ownership behavior is inherited, not copied: both guardian locks, the original Job Object owner and full precreate/preresume/runtime checks remain. Only `_before_begin` adds the finite immutable admission witness before the latch is consumed.
- One task owns one `Ledger`, one `FiniteTransport`, one semaphore and live receipt objects. The readiness thread is joined before the digest and readiness notification. The session's readiness `done` event is never used for terminal worker proof; the guardian overrides `_http_terminal` and requires actual session/readiness termination plus the phase's joined-wave certificate.
- Specific predecessor check: the implemented phase certificate must confirm joins for every started inner worker, including a worker already dead when a join loop is entered. The reference phase plan's final `is_alive` check alone is not a join operation. If phase review has not secured that semantic guarantee, this adapter must remain unimplemented until that small phase correction is reviewed; it cannot invent thread handles absent from the public phase interface.
- Authenticated same-run commit is required before constructing `VerifiedHandoff`. The durable handoff includes readiness and workload digests. Original-parent identity is enforced for all finite requests; generic installed behavior remains default-compatible.
- IPC resources retire before `finish_run`, full coverage binds before `on_result`, and `_terminal_failure` preserves a first terminal result. An unconfirmed worker or IPC close cannot retire the finite latch or grant lifecycle 2.
- Before implementing this adapter, consume the final independently reviewed phase receipt semantics. The original operation and return deadlines remain binding. A later evidence recheck must not renew an HTTP attempt or exceed the fixed resume+480 readiness deadline. The active phase task has focused regressions for this distinction and for actual worker joins; their passing review is required, not assumed by this plan. The adapter creates no retry.
- Per-phase memory peaks are not calculated by this bounded adapter. The report explicitly carries `unknown_not_analyzed`, with exact certificate boundaries and the existing durably sampled timeline. No memory qualification, peak coverage, owned-counter availability, final semantic verdict, public service acceptance or performance claim is produced. The remaining footprint/envelope review must include the new coordinator thread, retained receipts and IPC buffers before real execution.
- The private `_run_guardian` is not yet a launchable public feature; the required next parent interface above is precise. The old failed historical recovery latch still blocks admission, and no recovery or acceptance operation is part of this plan.
- Self-review checked fixed bounds, source/profile isolation, type/signature consistency against the two normative predecessor plans, immutable failure handling and the no-extra-POST invariant. Production code blocks are complete starting implementations for RED/GREEN refinement, not a claim of executed tests. No tests were executed and no checkout files were edited during planning.
- Frozen status: **prepared for main-agent review; not implemented or executed**. Only this private report is written by this planning task.
