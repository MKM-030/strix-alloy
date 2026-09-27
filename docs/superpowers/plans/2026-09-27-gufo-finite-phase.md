# GUFO finite readiness and phase executor implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an offline-testable readiness worker and fixed phase executor whose structural completion requires live returned receipts for every scheduled operation.

**Architecture:** Read only the owned child's bounded stderr stream until its exact listening line, then consume finite GET slots, the sole models GET, and POST 1. The worker terminates and supplies its live receipt to a later authenticated guardian/IPC adapter. A continuation with an explicit authenticated handoff input consumes POST 2–66 or 2–6, joins every worker, and returns a structural coverage certificate. This task does not integrate the finite store/guardian/IPC or alter installed service behavior.

**Tech Stack:** Python 3.12 standard library, `unittest`, temporary files, fake clock and scripted transport. Existing `Workload`, `Ledger`, `FiniteTransport`, `OperationResult`, `Milestone` and pure assessment.

## Global constraints and file map

- Work in `C:/Projects/strix-alloy-research/integration`, branch `codex/gufo-native-integration`. The reviewed transport baseline is committed `acf64f8`; inspect that code and `docs/superpowers/plans/2026-09-27-gufo-finite-transport.md` before implementation. Preserve its live Ledger poison and three reviewed transport fixes. The startup hint is implemented separately by `2026-09-27-gufo-finite-startup.md`; this plan consumes its `ListeningHint` interface.
- Workload pin: exactly 132273 bytes and SHA256 `30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38`. Lifecycle 1 has 66 POSTs, lifecycle 2 has 6; each has at most 240 readiness GETs and exactly one models GET. POST 1 is readiness in both. No warmup, replay, replacement slot or second simultaneous finite transport client.
- Preserve 60-second complete-operation, resume+480-second readiness and resume+3600/900-second absolute deadlines, three owned sockets, four 30-second idle windows after 6/18/30/48, 49/24/12 GiB memory floors, and 68/4/20 GiB GPU/host/shared envelope. The latter memory review remains a later gate.
- The native `http_server.cpp:1199–1204` line is `YYYY-MM-DD HH:MM:SS [INFO] [server] event=listening address=http://127.0.0.1:8836 auth=bearer max_connections=3 max_body_bytes=16384\n`; `logging.cpp:69–88` flushes it to stderr. It is only a scheduling hint. Reserved GET `/ready`, GET `/v1/models` and POST 1 still prove readiness. Failed first GET remains a consumed failed slot under the existing fail-closed ledger.
- Only synthetic offline tests; no listener, real socket, model, GPU, native helper, telemetry, recovery, D: drive, installed acceptance or launch. No SSE content-event count is a token count. A local disconnect is not proof of server cancellation.

| Path | Sole responsibility |
| --- | --- |
| `scripts/gufo_control/finite_ledger.py` | Read-only, locked receipt lookup for an existing exact slot. |
| `scripts/gufo_control/finite_phase.py` | Live receipt construction/verification, readiness task, fixed remaining phases, structural certificate. |
| `tests/gufo/test_finite_ledger.py` | Focused RED/GREEN receipt-accessor test using the existing temp ledger fixture. |
| `tests/gufo/test_finite_phase.py` | Real temp-ledger receipt tests and scripted transport/clock scheduling tests. |

### Task 1: Live receipts, readiness and all fixed phases

**Files:** Create `scripts/gufo_control/finite_phase.py` and `tests/gufo/test_finite_phase.py`; modify `scripts/gufo_control/finite_ledger.py` and `tests/gufo/test_finite_ledger.py` only.

**Interfaces:** `ReturnedReceipt` is created only at the synchronous transport return site, with `source=transport` as an in-process identity and `returned_at=clock()`. `VerifiedHandoff` is a future guardian/IPC adapter input: it attests that readiness task finished and was joined, its live receipt digest was authenticated, and the same exact run was committed. The pure continuation validates its fields and ledger binding; it does **not** independently prove the IPC authentication or guardian cleanup. `CoverageCertificate.complete` means structural workload coverage only; manual prose verdicts, memory and lifecycle/recovery acceptance remain separate gates.

- [ ] **Step 1: Add this test to the existing temporary-ledger fixture in `tests/gufo/test_finite_ledger.py`, then run it RED.** Expected `AttributeError: 'Ledger' object has no attribute 'receipt'`.

```python
    def test_receipt_requires_completed_exact_slot(self):
        row = self.ledger.reserve('ready', 1)
        with self.assertRaisesRegex(ValueError, 'finite_receipt_incomplete'):
            self.ledger.receipt('ready-001')
        self.ledger.complete(row['slot'], {'success': True})
        reservation, outcome = self.ledger.receipt('ready-001')
        self.assertEqual(reservation['ordinal'], 1)
        self.assertEqual(outcome['result'], {'success': True})
        with self.assertRaisesRegex(ValueError, 'finite_receipt_incomplete'):
            self.ledger.receipt('post-001')
```

- [ ] **Step 2: Add this read-only method to `Ledger` in `finite_ledger.py`, then run the same test GREEN.** The method returns copies of rows that `_scan` already validated. A standalone returned pair is corroborating storage, not a live receipt.

```python
    def receipt(self, slot: str) -> tuple[dict, dict]:
        with self._locked():
            reservations, outcomes, late_latch = self._scan()
            if late_latch is not None:
                raise ValueError('finite_transport_failed')
            if type(slot) is not str or slot not in reservations or slot not in outcomes:
                raise ValueError('finite_receipt_incomplete')
            return json.loads(_encoded(reservations[slot])), json.loads(_encoded(outcomes[slot]))
```

- [ ] **Step 3: Write `tests/gufo/test_finite_phase.py` from the complete test module printed below the production reference block, then run it RED.** Run `python -m unittest test_finite_phase -v`; expected import failure for `gufo_control.finite_phase`. Do this before creating `finite_phase.py`. The test module is placed after the production reference solely to keep interface definitions adjacent to their implementation text.
- [ ] **Step 4: Create `scripts/gufo_control/finite_phase.py` with this complete starting code.** The only transport calls occur inside `_invoke`; the returned object is captured directly, not reconstructed from disk. `verify_receipt` checks its projected durable outcome and sibling hashes. The future authenticated adapter must explicitly create `VerifiedHandoff` after joining the readiness thread and verifying the guardian's live receipt digest.

```python
"""Finite readiness and fixed workload schedule; structural evidence only."""
from concurrent.futures import Future
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import queue
import threading
import time

from .build_identity import checked_path
from .finite_transport import FiniteTransport, OperationResult, Milestone
from .finite_workload import WORKLOAD_SHA256, Workload

def _bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')

def _hash_file(path, maximum, deadline, clock):
    checked_path(path)
    before = path.stat()
    if before.st_size > maximum:
        raise ValueError('finite_evidence_size')
    digest = sha256()
    count = 0
    with path.open('rb') as stream:
        while True:
            if clock() >= deadline:
                raise ValueError('finite_evidence_deadline')
            part = stream.read(min(65536, maximum-count+1))
            if not part:
                break
            count += len(part)
            if count > maximum:
                raise ValueError('finite_evidence_size')
            digest.update(part)
    checked_path(path)
    after = path.stat()
    if (count != before.st_size or count != after.st_size or
            (before.st_dev, before.st_ino, before.st_ctime_ns) !=
            (after.st_dev, after.st_ino, after.st_ctime_ns)):
        raise ValueError('finite_evidence_changed')
    if clock() >= deadline:
        raise ValueError('finite_evidence_deadline')
    return digest.hexdigest().upper()

def _durable(result):
    value = dict(result.__dict__)
    value.pop('response')
    if result.assessment is not None:
        value['assessment'] = {key: result.assessment.get(key) for key in
            ('structural_success', 'answer_status', 'fully_validated',
             'request_contract_pass', 'errors')}
    return value

@dataclass(frozen=True)
class ReturnedReceipt:
    slot: str
    result: OperationResult
    returned_at: float
    reservation_sha256: str
    outcome_sha256: str
    source: object  # same-process transport identity; never serialized

def verify_receipt(ledger, transport, receipt, *, clock=time.monotonic):
    if not isinstance(receipt, ReturnedReceipt) or receipt.source is not transport:
        raise ValueError('finite_live_receipt_missing')
    reservation, outcome = ledger.receipt(receipt.slot)
    observed = clock()
    times = (receipt.result.sent_at, receipt.result.headers_at,
             receipt.result.first_content_at, receipt.result.terminal_at,
             receipt.result.close_started_at, receipt.result.close_completed_at)
    if (type(receipt.returned_at) not in (int, float) or
            not math.isfinite(receipt.returned_at) or
            not reservation['started'] <= receipt.returned_at <= observed or
            any(value is not None and
                (type(value) not in (int, float) or not math.isfinite(value) or
                 not reservation['started'] <= value <= receipt.returned_at)
                for value in times)):
        raise ValueError('finite_receipt_chronology')
    if (receipt.result.slot != receipt.slot or not receipt.result.success or
            receipt.returned_at >= reservation['deadline'] or
            outcome['result'] != _durable(receipt.result) or
            receipt.reservation_sha256 != sha256(_bytes(reservation)).hexdigest().upper() or
            receipt.outcome_sha256 != sha256(_bytes(outcome)).hexdigest().upper()):
        raise ValueError('finite_receipt_mismatch')
    evidence = ledger.root.with_name(ledger.root.name + '-finite-evidence')
    checked_path(evidence, directory=True)
    wire = evidence / (receipt.slot + '.wire.bin')
    if _hash_file(wire, reservation['wire_allowance'], reservation['deadline'], clock) != receipt.result.capture_sha256:
        raise ValueError('finite_capture_mismatch')
    if receipt.result.answer_sha256 is not None:
        answer = evidence / (receipt.slot + '.answer.json')
        limit = ledger.limits['generated_text_or_tool_argument_utf8_bytes']
        if _hash_file(answer, limit, reservation['deadline'], clock) != receipt.result.answer_sha256:
            raise ValueError('finite_answer_mismatch')
    return reservation

def _invoke(ledger, transport, operation, clock):
    result = operation()  # exact live synchronous return, never an outcome-file read
    returned_at = clock()
    reservation, outcome = ledger.receipt(result.slot)
    receipt = ReturnedReceipt(result.slot, result, returned_at,
        sha256(_bytes(reservation)).hexdigest().upper(),
        sha256(_bytes(outcome)).hexdigest().upper(), transport)
    verify_receipt(ledger, transport, receipt, clock=clock)
    return receipt

@dataclass
class FiniteReadinessTask:
    done: threading.Event
    cancel: threading.Event
    thread: threading.Thread
    result: dict
    receipts: tuple[ReturnedReceipt, ...]

def start_readiness(workload: Workload, ledger, transport: FiniteTransport,
                    hint, *, startup_deadline, lifetime_deadline,
                    clock=time.monotonic, pause=time.sleep):
    if (ledger.workload != workload or ledger.header['deadline'] != lifetime_deadline or
            startup_deadline != ledger.header['resumed_at'] + 480):
        raise ValueError('finite_readiness_identity')
    task = FiniteReadinessTask(threading.Event(), transport.cancel, None,
                               {'success': False, 'error': 'not_started'}, ())
    def work():
        receipts = []
        def live():
            if task.cancel.is_set() or clock() >= startup_deadline:
                raise ValueError('finite_readiness_cancelled_or_deadline')
        def call(operation):
            live()
            receipt = _invoke(ledger, transport, operation, clock)
            live()
            return receipt
        try:
            live()
            while not hint.poll(startup_deadline):
                if task.cancel.is_set():
                    raise ValueError('finite_readiness_cancelled')
                pause(min(.05, max(0, startup_deadline-clock())))
            for ordinal in range(1, 241):
                receipt = call(
                    lambda ordinal=ordinal: transport.get('ready', ordinal))
                receipts.append(receipt)
                if receipt.result.status == 200:
                    if receipt.result.response != {'status': 'ready',
                                                   'model': 'gufo-flash-next'}:
                        raise ValueError('finite_ready_shape')
                    break
                if (receipt.result.status != 503 or
                    receipt.result.response.get('error', {}).get('code') != 'not_ready'):
                    raise ValueError('finite_ready_response')
            else:
                raise ValueError('finite_ready_exhausted')
            receipts.append(call(lambda: transport.get('models', 1)))
            post = call(lambda: transport.post(1))
            receipts.append(post)
            assessment = post.result.assessment or {}
            if (post.result.classification != 'complete_positive' or
                    assessment.get('structural_success') is not True or
                    assessment.get('native_metrics_valid') is not True or
                    assessment.get('fully_validated') is not True or
                    assessment.get('check') != 'exact_arithmetic_4'):
                raise ValueError('finite_post1_invalid')
            if ledger.snapshot()['pending']:
                raise ValueError('finite_readiness_pending')
            task.result = {'success': True, 'error': None,
                           'post_attempted': True, 'ready_polls': ordinal}
        except BaseException as error:
            task.result = {'success': False, 'error': type(error).__name__ + ':' + str(error),
                           'post_attempted': any(r.slot == 'post-001' for r in receipts)}
        finally:
            task.receipts = tuple(receipts)
            task.done.set()
    task.thread = threading.Thread(target=work, daemon=True, name='gufo-finite-readiness')
    task.thread.start()
    return task

def readiness_digest(task, ledger, transport, *, clock=time.monotonic):
    if not task.done.is_set() or task.thread.is_alive() or task.result.get('success') is not True:
        raise ValueError('finite_readiness_worker_active')
    for receipt in task.receipts:
        verify_receipt(ledger, transport, receipt, clock=clock)
    if not task.receipts or task.receipts[-1].slot != 'post-001':
        raise ValueError('finite_post1_receipt_missing')
    rows = [(r.slot, r.outcome_sha256) for r in task.receipts]
    return sha256(_bytes(rows)).hexdigest().upper()

@dataclass(frozen=True)
class VerifiedHandoff:
    # Construct only in the later authenticated guardian/IPC wrapper.
    run_id: str
    workload_sha256: str
    readiness_digest: str
    ready_count: int
    models_count: int
    post_count: int
    worker_joined: bool
    ipc_committed: bool

@dataclass(frozen=True)
class CoverageCertificate:
    run_id: str
    lifecycle: int
    returned_slots: tuple[str, ...]
    ready_count: int
    models_count: int
    post_count: int
    workers_terminal: bool
    phase_boundaries: tuple[tuple[int, float], ...]
    idle_windows: tuple[tuple[int, float, float], ...]
    wave_proofs: tuple[tuple[int, float, float, float], ...]
    pending_semantic_review: bool
    failure: str | None
    complete: bool  # structural coverage only, never service acceptance

def run_remaining(workload, ledger, transport, handoff: VerifiedHandoff, *,
                  clock=time.monotonic, pause=time.sleep,
                  stop_event=None, parent_alive=lambda: True,
                  milestones=None):
    if (not isinstance(handoff, VerifiedHandoff) or
            handoff.run_id != ledger.header['run_id'] or
            handoff.workload_sha256 != WORKLOAD_SHA256 or
            not handoff.worker_joined or not handoff.ipc_committed or
            handoff.models_count != 1 or handoff.post_count != 1 or
            not 1 <= handoff.ready_count <= 240):
        raise ValueError('finite_handoff_invalid')
    snapshot = ledger.snapshot()
    if (snapshot['pending'] or snapshot['counts'] !=
            {'ready': handoff.ready_count, 'models': 1, 'post': 1}):
        raise ValueError('finite_handoff_ledger')
    first_slots = ([f'ready-{n:03d}' for n in range(1, handoff.ready_count+1)]
                   + ['models-001', 'post-001'])
    stored_rows = [(slot, sha256(_bytes(ledger.receipt(slot)[1])).hexdigest().upper())
                   for slot in first_slots]
    if sha256(_bytes(stored_rows)).hexdigest().upper() != handoff.readiness_digest:
        raise ValueError('finite_handoff_digest')
    if transport.ledger is not ledger or transport.workload != workload:
        raise ValueError('finite_continuation_identity')
    events = milestones if milestones is not None else queue.SimpleQueue()
    transport.milestone = events.put_nowait
    stop_event = stop_event if stop_event is not None else threading.Event()
    life = workload.lifecycle(ledger.index)
    receipts, idle, waves = [], [], []
    boundaries = [(1, clock())]
    previous = {}
    failure = None
    workers_started = []
    append_lock = threading.Lock()

    def live():
        if stop_event.is_set() or not parent_alive() or clock() >= ledger.header['deadline']:
            raise ValueError('finite_client_lost_or_deadline')

    def one(n, disconnect=None):
        live()
        post = workload.post(ledger.index, n)
        key = (post.request_id, post.body_sha256, post.route)
        prior = previous.get(key) if json.loads(post.step_json).get('compare_repeated_body') else None
        receipt = _invoke(ledger, transport,
            lambda: transport.post(n, disconnect=disconnect, previous=prior), clock)
        value = receipt.result
        if value.classification in ('complete_positive', 'expected_rejection'):
            assessment = value.assessment or {}
            if value.classification == 'complete_positive':
                if (assessment.get('structural_success') is not True or
                        assessment.get('native_metrics_valid') is not True):
                    raise ValueError('finite_positive_invalid')
                previous[key] = assessment
            elif assessment.get('request_contract_pass') is not True:
                raise ValueError('finite_rejection_invalid')
        elif disconnect is not None:
            expected_class = ('local_headers_disconnect' if disconnect == 'headers'
                              else 'local_event_disconnect')
            if (value.classification != expected_class or
                    value.close_started_at is None or value.close_completed_at is None or
                    value.close_started_at > value.close_completed_at or
                    value.close_completed_at >= ledger.header['deadline']):
                raise ValueError('finite_cancel_unproven')
        else:
            raise ValueError('finite_post_invalid')
        with append_lock:
            receipts.append(receipt)
        return receipt

    def idle_after(n):
        start = clock()
        while clock() - start < 30:
            live()
            pause(min(.05, 30-(clock()-start)))
        end = clock()
        idle.append((n, start, end))

    def operation_deadline(worker):
        with ledger._locked():
            reservations, _, _ = ledger._scan()
        row = reservations.get(worker['slot'])
        return row['deadline'] if row is not None else min(
            worker['started']+60, ledger.header['deadline'])

    def await_event(slot, event, workers):
        while True:
            live()
            if any(clock() >= operation_deadline(worker) for worker in workers
                   if worker['thread'].is_alive()):
                raise ValueError('finite_wave_worker_deadline')
            try:
                item = events.get(timeout=.01)
            except queue.Empty:
                if any(worker['done'].is_set() and worker['error'] for worker in workers):
                    raise ValueError('finite_wave_worker_failed')
                if any(worker['slot'] == slot and worker['done'].is_set()
                       for worker in workers):
                    raise ValueError('finite_wave_milestone_missing')
                if workers and all(worker['done'].is_set() for worker in workers):
                    raise ValueError('finite_wave_milestone_missing')
                pause(.01)
                continue
            if item.event == 'terminal' and item.slot in (
                    f'post-{workers[0]["n"]:03d}' if workers else '',
                    f'post-{workers[1]["n"]:03d}' if len(workers) > 1 else ''):
                raise ValueError('finite_overlap_missed')
            if item.slot == slot and item.event == event:
                return item.at

    def wave(a, b, c):
        workers = []
        def join_live():
            while any(worker['thread'].is_alive() for worker in workers):
                live()
                if any(clock() >= operation_deadline(worker) for worker in workers
                       if worker['thread'].is_alive()):
                    raise ValueError('finite_wave_worker_deadline')
                for worker in workers:
                    worker['thread'].join(timeout=.01)
                pause(.01)
        def launch(n):
            worker = {'n': n, 'slot': f'post-{n:03d}', 'started': clock(),
                      'done': threading.Event(), 'receipt': None, 'error': None}
            def work():
                try:
                    worker['receipt'] = one(n)
                except BaseException as error:
                    worker['error'] = error
                finally:
                    worker['done'].set()
            worker['thread'] = threading.Thread(target=work, daemon=True,
                                                name=f'gufo-finite-wave-{n}')
            workers.append(worker)
            workers_started.append(worker)
            worker['thread'].start()
            return worker
        try:
            active = launch(a)
            first = await_event(f'post-{a:03d}', 'first_content', workers)
            pending = launch(b)
            sent_pending = await_event(f'post-{b:03d}', 'sent', workers)
            if active['done'].is_set() or pending['done'].is_set():
                raise ValueError('finite_overlap_missed')
            third = launch(c)
            sent_third = await_event(f'post-{c:03d}', 'sent', workers)
            join_live()
            if any(worker['thread'].is_alive() or worker['error'] for worker in workers):
                raise ValueError('finite_wave_worker_failed')
            ra, rb, rc = (worker['receipt'].result for worker in workers)
            if (not first <= sent_pending <= sent_third or
                    ra.terminal_at is None or rb.terminal_at is None or
                    not sent_third < ra.terminal_at or not sent_third < rb.terminal_at):
                raise ValueError('finite_overlap_missed')
            if (c == 45 and (rc.status != 429 or rc.classification != 'expected_rejection') or
                    c == 48 and (rc.status != 400 or rc.classification != 'expected_rejection')):
                raise ValueError('finite_wave_rejection')
            waves.append((c, first, sent_pending, sent_third))
        finally:
            if any(worker['thread'].is_alive() for worker in workers):
                transport.cancel.set()
                cleanup_end = min(clock()+1, ledger.header['deadline'])
                wall_end = time.monotonic()+1
                while (any(worker['thread'].is_alive() for worker in workers)
                       and clock() < cleanup_end and time.monotonic() < wall_end):
                    for worker in workers:
                        worker['thread'].join(timeout=.01)
                    pause(.01)

    try:
        for n in range(2, min(30, life['maximum_post_attempts'])+1):
            one(n)
            if n in (6,18,30):
                boundaries.append((n, clock()))
                if ledger.index == 1:
                    idle_after(n)
        if ledger.index == 1:
            triggers = {31:'headers',33:'headers',35:1,37:1,39:8,41:8}
            for cancel_n, trigger in triggers.items():
                one(cancel_n, trigger)
                one(cancel_n+1)
            boundaries.append((42, clock()))
            wave(43,44,45)
            boundaries.append((45, clock()))
            wave(46,47,48)
            boundaries.append((48, clock()))
            idle_after(48)
            for n in range(49,67):
                one(n)
            boundaries.append((66, clock()))
        live()
        snapshot = ledger.snapshot()
        expected = tuple(f'post-{n:03d}' for n in range(2, life['maximum_post_attempts']+1))
        actual = tuple(sorted((r.slot for r in receipts)))
        if (actual != expected or snapshot['pending'] or
                snapshot['counts'] != {'ready': handoff.ready_count,
                                       'models': 1, 'post': life['maximum_post_attempts']} or
                len(idle) != (4 if ledger.index == 1 else 0) or
                len(waves) != (2 if ledger.index == 1 else 0)):
            raise ValueError('finite_coverage_incomplete')
    except BaseException as error:
        failure = type(error).__name__ + ':' + str(error)
    try:
        final_count = ledger.snapshot()['counts']['post']
    except ValueError:
        final_count = len(receipts) + 1
        failure = failure or 'finite_ledger_unavailable'
    terminal = all(not worker['thread'].is_alive() for worker in workers_started)
    if not terminal:
        failure = failure or 'finite_worker_unjoined'
    return CoverageCertificate(ledger.header['run_id'], ledger.index,
        tuple(r.slot for r in receipts), handoff.ready_count, 1,
        final_count, terminal,
        tuple(boundaries), tuple(idle), tuple(waves),
        any((r.result.assessment or {}).get('answer_status') ==
            'pending_semantic_review' for r in receipts), failure,
        failure is None and terminal)
```

The code is a starting implementation and may be refined through RED/GREEN tests without weakening the frozen transport and workload limits. The `receipts` list is protected during wave returns; final coverage compares slot sets rather than worker return order. The certificate is never complete while a wave worker remains alive. A late-outcome ledger latch makes the certificate fail even if its snapshot cannot be read.

**Complete test module for Step 3.** The scripted scheduler double below creates real temporary `Ledger` rows and bounded sibling artifacts; the committed transport's own `ScriptedSocket` tests separately prove exact HTTP wire and answer parsing. All these tests use fake clock and no network.

```python
import queue
import json
import threading
import tempfile
import time
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from gufo_control.finite_ledger import Ledger
from gufo_control.finite_transport import OperationResult, Milestone
from gufo_control.finite_phase import (VerifiedHandoff, run_remaining,
    readiness_digest, start_readiness, verify_receipt, ReturnedReceipt,
    _durable, _bytes, _hash_file)
from dataclasses import replace
from gufo_control.finite_workload import WORKLOAD_SHA256, load_workload

class ScriptedTransport:
    def __init__(self, ledger, workload, clock, advance, fail_post=None,
                 ready_statuses=(200,), wrong_third=False,
                 fail_ready=None, late_ready=None, wrong_code=None,
                 drop_milestone=None, early_terminal=None, hang_post=None,
                 repeat_mismatch=None, pending_prose=False, on_started=None,
                 missing_return=None, third_early=False):
        self.ledger, self.workload, self.clock, self.advance = (
            ledger, workload, clock, advance)
        self.fail_post = fail_post
        self.ready_statuses = ready_statuses
        self.wrong_third = wrong_third
        self.fail_ready, self.late_ready = fail_ready, late_ready
        self.wrong_code = wrong_code
        self.drop_milestone, self.early_terminal = drop_milestone, early_terminal
        self.hang_post, self.repeat_mismatch = hang_post, repeat_mismatch
        self.pending_prose, self.on_started = pending_prose, on_started
        self.missing_return = missing_return
        self.third_early = third_early
        self.cancel = threading.Event()
        self.milestone = lambda event: None
        self.calls = []
        self.history = []
        self.priors = {}
        self.disconnects = {}
        self.evidence = ledger.root.with_name(ledger.root.name + '-finite-evidence')
        self.evidence.mkdir()
        self.wave_gates = {45: threading.Event(), 48: threading.Event()}
        self.third_returned = {45: threading.Event(), 48: threading.Event()}
        self.hang_release = threading.Event()

    def emit(self, slot, event, at):
        if (slot, event) != self.drop_milestone:
            self.milestone(Milestone(slot, event, at))

    def _operation(self, kind, ordinal, *, disconnect=None, previous=None):
        post = self.workload.post(self.ledger.index, ordinal) if kind == 'post' else None
        body = post.body if post else b''
        row = self.ledger.reserve(kind, ordinal, body=body)
        self.calls.append(row['slot'])
        self.history.append(('reserve', ordinal))
        if disconnect is not None:
            self.disconnects[ordinal] = disconnect
        now = self.clock()
        if self.on_started is not None:
            self.on_started(kind, ordinal)
        self.emit(row['slot'], 'sent', now)
        if post:
            self.emit(row['slot'], 'first_content', now)
        if kind == 'post' and ordinal == self.hang_post:
            self.hang_release.wait(timeout=30)
        if ordinal in (43,44) and kind == 'post' and ordinal != self.early_terminal:
            if not self.wave_gates[45].wait(timeout=1):
                raise TimeoutError('synthetic_wave_gate')
            if self.third_early and not self.third_returned[45].wait(timeout=1):
                raise TimeoutError('synthetic_third_return')
        if ordinal in (46,47) and kind == 'post' and ordinal != self.early_terminal:
            if not self.wave_gates[48].wait(timeout=1):
                raise TimeoutError('synthetic_wave_gate')
            if self.third_early and not self.third_returned[48].wait(timeout=1):
                raise TimeoutError('synthetic_third_return')
        if ordinal in (45,48) and kind == 'post':
            self.wave_gates[ordinal].set()
        wire = b'synthetic-wire'
        (self.evidence / (row['slot']+'.wire.bin')).write_bytes(wire)
        positive = post is not None and post.expected_status == 200 and disconnect is None
        answer_hash = None
        if positive:
            answer = b'{"visible_answer":"4","reasoning_content":"","tool_calls":[]}'
            (self.evidence / (row['slot']+'.answer.json')).write_bytes(answer)
            answer_hash = sha256(answer).hexdigest().upper()
        fail = ((kind == 'post' and ordinal == self.fail_post) or
                (kind == 'ready' and ordinal == self.fail_ready))
        step = json.loads(post.step_json) if post else {}
        fingerprint = (sha256(b'mismatch').hexdigest().upper()
                       if ordinal == self.repeat_mismatch else sha256(b'4').hexdigest().upper())
        repeat = ('not_compared' if previous is None else
                  'match' if previous.get('fingerprint') == fingerprint else 'mismatch')
        self.priors[ordinal] = previous
        structural = repeat != 'mismatch'
        prose = step.get('check') == 'english_two_sentence_semantic_review'
        answer_status = ('pending_semantic_review' if prose and self.pending_prose
                         else 'pass')
        assessment = (dict(request_id=post.request_id,
                           request_body_sha256=post.body_sha256, route=post.route,
                           check=step['check'], fingerprint=fingerprint, repeat=repeat,
                           structural_success=structural, native_metrics_valid=True,
                           answer_status=answer_status,
                           fully_validated=structural and answer_status == 'pass',
                           request_contract_pass=None,
                           errors=[] if structural else ['inconsistent_repeat_answer'])
                      if positive else
                      dict(structural_success=None, native_metrics_valid=None,
                           answer_status=None, fully_validated=None,
                           request_contract_pass=ordinal != self.wrong_code,
                           errors=[] if ordinal != self.wrong_code else ['wrong_code'])
                      if post is not None else None)
        status = (post.expected_status if post else
                  self.ready_statuses[ordinal-1] if kind == 'ready' else
                  200 if kind == 'models' else None)
        if self.wrong_third and kind == 'post' and ordinal == 45:
            status = 200
        if kind == 'ready' and ordinal == self.late_ready:
            self.advance(row['deadline']-self.clock())
        completed = self.advance(.01)
        classification = ('transport_failure' if fail else
                          'local_headers_disconnect' if disconnect == 'headers' else
                          'local_event_disconnect' if disconnect is not None else
                          'complete_positive' if positive else
                          'expected_rejection' if post else 'get_response')
        response = ({'status':'ready','model':'gufo-flash-next'}
                    if kind == 'ready' and status == 200 else
                    {'error':{'code':'not_ready'}} if kind == 'ready' else
                    {'data':[{'id':'gufo-flash-next'}]} if kind == 'models'
                    else None)
        result = OperationResult(row['slot'], not fail, classification, status,
            len(wire), sha256(wire).hexdigest().upper(),
            sha256(wire).hexdigest().upper(), answer_hash,
            sha256(b'4').hexdigest().upper() if positive else None,
            now, now, now if post else None, completed,
            completed, completed, 0 if disconnect else None,
            'scripted_failure' if fail else None, assessment, response)
        self.ledger.complete(row['slot'], _durable(result))
        if kind == 'post' and ordinal in self.third_returned:
            self.third_returned[ordinal].set()
        self.emit(row['slot'], 'terminal', completed)
        self.history.append(('return', ordinal))
        if kind == 'post' and ordinal == self.missing_return:
            raise ValueError('synthetic_return_lost')
        return result

    def get(self, kind, ordinal):
        return self._operation(kind, ordinal)

    def post(self, ordinal, *, disconnect=None, previous=None):
        return self._operation('post', ordinal, disconnect=disconnect,
                               previous=previous)

class PhaseScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = [100.0]
        self.time_lock = threading.Lock()
        def clock():
            with self.time_lock:
                return self.now[0]
        def advance(seconds):
            with self.time_lock:
                self.now[0] += seconds
                result = self.now[0]
            time.sleep(0)  # hand off to a barrier worker; no real-clock spin
            return result
        self.clock, self.advance = clock, advance
        self.pause = lambda seconds: advance(max(seconds, .5))

    def synthetic_setup(self, *, index, readiness_complete=False,
                        **options):
        workload = load_workload()
        root = Path(self.temp.name) / ('ledger-'+str(index))
        ledger = Ledger(root, workload, index, 'synthetic-run', 100.0,
                        create=True, clock=self.clock)
        transport = ScriptedTransport(ledger, workload, self.clock,
                                      self.advance, **options)
        if readiness_complete:
            transport.get('ready', 1)
            transport.get('models', 1)
            transport.post(1)
        return ledger, workload, transport

    def handoff(self, ledger, ready_count=1):
        slots = [f'ready-{n:03d}' for n in range(1, ready_count+1)]
        slots += ['models-001', 'post-001']
        rows = [(slot, sha256(_bytes(ledger.receipt(slot)[1])).hexdigest().upper())
                for slot in slots]
        return VerifiedHandoff(ledger.header['run_id'], WORKLOAD_SHA256,
            sha256(_bytes(rows)).hexdigest().upper(), ready_count, 1, 1,
            True, True)

    def start_task(self, *, ready_statuses=(200,), fail_ready=None,
                   late_ready=None):
        ledger, workload, transport = self.synthetic_setup(index=2,
            ready_statuses=ready_statuses, fail_ready=fail_ready,
            late_ready=late_ready)
        class Marker:
            def poll(self, deadline):
                return True
        task = start_readiness(workload, ledger, transport, Marker(),
            startup_deadline=580.0, lifetime_deadline=1000.0,
            clock=self.clock, pause=self.pause)
        task.thread.join(timeout=1)
        self.assertFalse(task.thread.is_alive())
        return ledger, workload, transport, task

    def test_handoff_requires_joined_worker_and_commit(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True)
        handoff = self.handoff(ledger)
        with self.assertRaisesRegex(ValueError, 'finite_handoff_invalid'):
            run_remaining(workload, ledger, transport,
                VerifiedHandoff(handoff.run_id, handoff.workload_sha256,
                    handoff.readiness_digest, 1, 1, 1, False, True))
        with self.assertRaisesRegex(ValueError, 'finite_handoff_invalid'):
            run_remaining(workload, ledger, transport,
                VerifiedHandoff(handoff.run_id, handoff.workload_sha256,
                    handoff.readiness_digest, 1, 1, 1, True, False))

    def test_second_lifecycle_exact_six_posts(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertTrue(certificate.complete, certificate.failure)
        self.assertEqual(certificate.post_count, 6)
        self.assertEqual(certificate.returned_slots,
                         tuple(f'post-{n:03d}' for n in range(2,7)))
        self.assertEqual(certificate.idle_windows, ())

    def test_parent_loss_after_handoff_stops_before_next_post(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause,
            parent_alive=lambda: False)
        self.assertFalse(certificate.complete)
        self.assertEqual(ledger.snapshot()['counts']['post'], 1)

    def test_early_stop_cannot_turn_readiness_into_coverage(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True)
        stopped = threading.Event()
        stopped.set()
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause,
            stop_event=stopped)
        self.assertFalse(certificate.complete)
        self.assertEqual(ledger.snapshot()['counts']['post'], 1)

    def test_failed_post_never_sends_next_case(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True, fail_post=2)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertEqual(ledger.snapshot()['counts']['post'], 2)

    def test_first_lifecycle_all_66_and_four_idle_windows(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertTrue(certificate.complete, certificate.failure)
        self.assertEqual(certificate.post_count, 66)
        self.assertEqual([row[0] for row in certificate.idle_windows],
                         [6,18,30,48])
        self.assertTrue(all(end-start >= 30 for _,start,end in
                            certificate.idle_windows))
        self.assertEqual([row[0] for row in certificate.wave_proofs], [45,48])
        self.assertEqual(transport.disconnects,
                         {31:'headers',33:'headers',35:1,37:1,39:8,41:8})
        for cancel_n in (31,33,35,37,39,41):
            self.assertLess(transport.history.index(('return',cancel_n)),
                            transport.history.index(('reserve',cancel_n+1)))
        self.assertEqual([transport.ledger.receipt(f'post-{n:03d}')[0]['body_sha256']
                          for n in (45,48)],
                         [workload.post(1,n).body_sha256 for n in (45,48)])

    def test_third_reply_may_precede_prior_terminals(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, third_early=True)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertTrue(certificate.complete, certificate.failure)
        for third, active, pending in ((45,43,44),(48,46,47)):
            third_outcome = ledger.receipt(f'post-{third:03d}')[1]['result']
            for earlier in (active,pending):
                prior = ledger.receipt(f'post-{earlier:03d}')[1]['result']
                self.assertLessEqual(third_outcome['terminal_at'],
                                     prior['terminal_at'])

    def test_wave_one_third_200_is_consumed_missed_overlap(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, wrong_third=True)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertEqual(ledger.snapshot()['counts']['post'], 45)
        self.assertNotIn('post-046', transport.calls)

    def test_wrong_queue_code_stops_after_consumed_third(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, wrong_code=45)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertEqual(ledger.snapshot()['counts']['post'], 45)
        self.assertNotIn('post-046', transport.calls)

    def test_wrong_context_code_stops_after_second_wave(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, wrong_code=48)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertEqual(ledger.snapshot()['counts']['post'], 48)
        self.assertNotIn('post-049', transport.calls)

    def test_missing_first_content_never_opens_pending(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True,
            drop_milestone=('post-043','first_content'))
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertNotIn('post-044', transport.calls)

    def test_missing_pending_sent_never_opens_third(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True,
            drop_milestone=('post-044','sent'))
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertNotIn('post-045', transport.calls)

    def test_early_active_terminal_never_opens_third(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, early_terminal=43)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertNotIn('post-045', transport.calls)

    def test_outcome_without_returned_wave_receipt_fails(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, missing_return=43)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertNotIn('post-046', transport.calls)

    def test_parent_loss_and_stop_during_wave_are_terminal(self):
        for stop_instead in (False, True):
            with self.subTest(stop_instead=stop_instead):
                # Each subcase owns a fresh temp ledger root.
                with tempfile.TemporaryDirectory() as directory:
                    old_temp = self.temp
                    self.temp = type('TempRoot', (), {'name':directory})()
                    try:
                        seen = threading.Event()
                        stopped = threading.Event()
                        def started(kind, ordinal):
                            if kind == 'post' and ordinal == 43:
                                seen.set()
                                if stop_instead:
                                    stopped.set()
                        ledger, workload, transport = self.synthetic_setup(index=1,
                            readiness_complete=True, on_started=started)
                        certificate = run_remaining(workload, ledger, transport,
                            self.handoff(ledger), clock=self.clock, pause=self.pause,
                            parent_alive=lambda: not seen.is_set() or stop_instead,
                            stop_event=stopped)
                        self.assertFalse(certificate.complete)
                        self.assertNotIn('post-044', transport.calls)
                    finally:
                        self.temp = old_temp

    def test_unjoined_wave_worker_never_completes(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, hang_post=43)
        try:
            certificate = run_remaining(workload, ledger, transport,
                self.handoff(ledger), clock=self.clock, pause=self.pause)
            self.assertFalse(certificate.complete)
            self.assertFalse(certificate.workers_terminal)
        finally:
            transport.hang_release.set()
            for thread in threading.enumerate():
                if thread.name == 'gufo-finite-wave-43':
                    thread.join(timeout=1)

    def test_readiness_is_post_one_and_worker_is_joined(self):
        ledger, workload, transport, task = self.start_task(
            ready_statuses=(503,200))
        self.assertTrue(task.result['success'], task.result)
        self.assertEqual(transport.calls,
            ['ready-001','ready-002','models-001','post-001'])
        self.assertEqual(len(readiness_digest(task, ledger, transport,
                                              clock=self.clock)), 64)

    def test_post_one_crossing_startup_deadline_cannot_be_ready(self):
        def started(kind, ordinal):
            if kind == 'post' and ordinal == 1:
                self.advance(580.0-self.clock())
        ledger, workload, transport = self.synthetic_setup(index=2,
            on_started=started)
        self.advance(579.96-self.clock())  # POST crosses startup, not its own 60s limit.
        class Marker:
            def poll(self, deadline):
                return True
        task = start_readiness(workload, ledger, transport, Marker(),
            startup_deadline=580.0, lifetime_deadline=1000.0,
            clock=self.clock, pause=self.pause)
        task.thread.join(timeout=1)
        self.assertFalse(task.thread.is_alive())
        self.assertFalse(task.result['success'])
        self.assertIn('post-001', transport.calls)

    def test_already_cancelled_readiness_does_not_issue_get(self):
        ledger, workload, transport = self.synthetic_setup(index=2)
        transport.cancel.set()
        class Marker:
            def poll(self, deadline):
                return True
        task = start_readiness(workload, ledger, transport, Marker(),
            startup_deadline=580.0, lifetime_deadline=1000.0,
            clock=self.clock, pause=self.pause)
        task.thread.join(timeout=1)
        self.assertFalse(task.thread.is_alive())
        self.assertFalse(task.result['success'])
        self.assertEqual(transport.calls, [])

    def test_refused_first_get_consumes_slot_and_stops(self):
        ledger, workload, transport, task = self.start_task(fail_ready=1)
        self.assertFalse(task.result['success'])
        self.assertEqual(transport.calls, ['ready-001'])
        with self.assertRaisesRegex(ValueError, 'finite_prior_failure'):
            ledger.reserve('ready', 2)

    def test_all_240_not_ready_polls_stop_without_post(self):
        ledger, workload, transport, task = self.start_task(
            ready_statuses=(503,)*240)
        self.assertFalse(task.result['success'])
        self.assertEqual(ledger.snapshot()['counts'],
                         {'ready':240,'models':0,'post':0})
        self.assertEqual(len(transport.calls), 240)

    def test_late_first_get_latches_without_retry(self):
        ledger, workload, transport, task = self.start_task(late_ready=1)
        self.assertFalse(task.result['success'])
        self.assertEqual(transport.calls, ['ready-001'])
        self.assertTrue((ledger.root/'transport-failed.json').exists())

    def test_repeat_mismatch_stops_and_prose_remains_pending(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, repeat_mismatch=16)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertFalse(certificate.complete)
        self.assertIsNotNone(transport.priors[16])
        self.assertEqual(ledger.snapshot()['counts']['post'], 16)
        self.assertNotIn('post-017', transport.calls)

    def test_pending_prose_is_structural_coverage_only(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True, pending_prose=True)
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertTrue(certificate.complete, certificate.failure)
        self.assertTrue(certificate.pending_semantic_review)
        self.assertEqual(transport.priors[16]['request_id'],
                         workload.post(1,16).request_id)

    def test_capture_tamper_rejects_live_return(self):
        ledger, workload, transport = self.synthetic_setup(index=2)
        result = transport.get('ready', 1)
        reservation, outcome = ledger.receipt('ready-001')
        receipt = ReturnedReceipt('ready-001', result, self.clock(),
            sha256(_bytes(reservation)).hexdigest().upper(),
            sha256(_bytes(outcome)).hexdigest().upper(), transport)
        verify_receipt(ledger, transport, receipt, clock=self.clock)
        (transport.evidence / 'ready-001.wire.bin').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'finite_capture_mismatch'):
            verify_receipt(ledger, transport, receipt, clock=self.clock)

    def test_answer_tamper_rejects_live_return(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True)
        result = transport.post(2)
        reservation, outcome = ledger.receipt('post-002')
        receipt = ReturnedReceipt('post-002', result, self.clock(),
            sha256(_bytes(reservation)).hexdigest().upper(),
            sha256(_bytes(outcome)).hexdigest().upper(), transport)
        verify_receipt(ledger, transport, receipt, clock=self.clock)
        (transport.evidence / 'post-002.answer.json').write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'finite_answer_mismatch'):
            verify_receipt(ledger, transport, receipt, clock=self.clock)

    def test_late_return_and_disk_only_row_are_not_receipts(self):
        ledger, workload, transport = self.synthetic_setup(index=2)
        result = transport.get('ready', 1)
        reservation, outcome = ledger.receipt('ready-001')
        digest_r = sha256(_bytes(reservation)).hexdigest().upper()
        digest_o = sha256(_bytes(outcome)).hexdigest().upper()
        with self.assertRaisesRegex(ValueError, 'finite_live_receipt_missing'):
            verify_receipt(ledger, transport, outcome, clock=self.clock)
        for bad in (float('nan'), -1.0, True):
            with self.subTest(returned_at=bad):
                invalid = ReturnedReceipt('ready-001', result, bad,
                                          digest_r, digest_o, transport)
                with self.assertRaisesRegex(ValueError, 'finite_receipt_chronology'):
                    verify_receipt(ledger, transport, invalid, clock=self.clock)
        impossible = ReturnedReceipt('ready-001',
            replace(result, terminal_at=self.clock()+1), self.clock(),
            digest_r, digest_o, transport)
        with self.assertRaisesRegex(ValueError, 'finite_receipt_chronology'):
            verify_receipt(ledger, transport, impossible, clock=self.clock)
        late = ReturnedReceipt('ready-001', result, reservation['deadline'],
                               digest_r, digest_o, transport)
        self.advance(reservation['deadline']-self.clock())
        with self.assertRaisesRegex(ValueError, 'finite_receipt_mismatch'):
            verify_receipt(ledger, transport, late, clock=self.clock)

    def test_hash_file_rejects_growth_during_read(self):
        path = Path(self.temp.name) / 'growing.bin'
        path.write_bytes(b'x'*16)
        original_open = Path.open
        class GrowOnRead:
            def __init__(self, stream):
                self.stream, self.grew = stream, False
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def read(self, size):
                data = self.stream.read(size)
                if not self.grew:
                    self.grew = True
                    with original_open(path, 'ab') as writer:
                        writer.write(b'z')
                return data
        def opening(candidate, *args, **kwargs):
            stream = original_open(candidate, *args, **kwargs)
            return GrowOnRead(stream) if candidate == path and args[0] == 'rb' else stream
        with patch.object(Path, 'open', opening):
            with self.assertRaisesRegex(ValueError, 'finite_evidence_size'):
                _hash_file(path, 16, 160.0, self.clock)

    def test_hash_file_rechecks_deadline_after_read(self):
        path = Path(self.temp.name) / 'deadline.bin'
        path.write_bytes(b'x')
        original_open = Path.open
        class LateRead:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def read(self, size):
                data = self.stream.read(size)
                self_clock[0] = 160.0
                return data
        self_clock = self.now
        def opening(candidate, *args, **kwargs):
            stream = original_open(candidate, *args, **kwargs)
            return LateRead(stream) if candidate == path and args[0] == 'rb' else stream
        with patch.object(Path, 'open', opening):
            with self.assertRaisesRegex(ValueError, 'finite_evidence_deadline'):
                _hash_file(path, 16, 160.0, self.clock)
```

The factory is deliberately a no-socket scheduler double and writes real temporary ledger/capture rows. The committed transport's `ScriptedSocket` tests separately cover HTTP wire and answer parsing. Its barrier keeps the two prior wave workers live until the third request is sent; it never pauses client response drain. The early-third-reply case remains valid when the third send falls within both prior in-flight intervals. The full first-lifecycle test checks the exact pinned body hashes for both third requests against their reservations.

- [ ] **Step 5: Run** `python -m unittest test_finite_phase test_finite_startup test_finite_ledger test_finite_transport.FiniteTransportTests test_finite_assessment -v` with the `PYTHONPATH` above, then `git diff --check`. Expected all GREEN without a real socket or listener. Inspect the four scoped paths and committed transport behavior. Do not run the broad live GUFO suite, launch a model, or publish.

- [ ] **Step 6: Commit the four scoped files after the tests and self-review.**

```powershell
git add scripts/gufo_control/finite_phase.py scripts/gufo_control/finite_ledger.py tests/gufo/test_finite_phase.py tests/gufo/test_finite_ledger.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m "feat: execute bounded GUFO qualification phases"
```

## Exact later integration boundary

The future finite guardian wrapper injects `start_readiness` as `_Guardian.http_start`, uses its own finite lifecycle deadline provider to capture `resumed_at` exactly, and obtains `run_dir` and private key from `on_started`. It joins the readiness thread **before** calling the authenticated IPC `on_ready`/handoff path and derives `readiness_digest` from live `ReturnedReceipt` objects plus the ledger/evidence checks. Only that authenticated wrapper constructs `VerifiedHandoff` with the exact run ID, counts, digest, joined-worker proof and committed IPC state. The continuation independently checks its ledger and consumes only the remaining scheduled POSTs; its certificate does not claim to have authenticated the wrapper. The wrapper tracks the continuation after handoff, treats early stop/parent death as failure, issues authenticated stop only after `certificate.complete`, then requires guardian terminal success, owned exit, clean workers, evidence and five-sample recovery before lifecycle 2. An uncertain handoff is resolved by exact-run authenticated status, never a second launch. Installed `_run_guardian`, installed profile pins and installed service behavior stay untouched.

Structural full coverage can coexist with pending manual prose review. It is not final semantic acceptance, service acceptance or a speed claim. Sampled per-phase memory and missing owned counters remain unknown until the later guardian evidence binding; no zero imputation or fabricated peak. The old failed recovery latch, fresh admission and full 68/4/20 envelope review remain separate gates.
