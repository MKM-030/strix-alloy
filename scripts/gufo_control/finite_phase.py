"""Finite readiness and fixed workload schedule; structural evidence only."""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import queue
import threading
import time

from .build_identity import checked_path
from .finite_transport import FiniteTransport, OperationResult
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

def verify_receipt(ledger, transport, receipt, *, clock=time.monotonic,
                   evidence_deadline=None):
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
    digest_deadline = (reservation['deadline'] if evidence_deadline is None
                       else evidence_deadline)
    if (type(digest_deadline) not in (int, float) or
            not math.isfinite(digest_deadline) or
            digest_deadline > ledger.header['deadline']):
        raise ValueError('finite_evidence_deadline')
    if _hash_file(wire, reservation['wire_allowance'], digest_deadline, clock) != receipt.result.capture_sha256:
        raise ValueError('finite_capture_mismatch')
    if receipt.result.answer_sha256 is not None:
        answer = evidence / (receipt.slot + '.answer.json')
        limit = ledger.limits['generated_text_or_tool_argument_utf8_bytes']
        if _hash_file(answer, limit, digest_deadline, clock) != receipt.result.answer_sha256:
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
        # Each return was checked against its operation deadline by _invoke.
        # A joined task may recheck earlier evidence after that deadline,
        # but the entire readiness digest still ends by resume + 480.
        verify_receipt(ledger, transport, receipt, clock=clock,
                       evidence_deadline=min(clock() + 60,
                           ledger.header['resumed_at'] + 480))
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
        # The worker starts before its reservation. This bound is conservative,
        # and avoids holding the ledger lock while waiting for worker milestones.
        return min(worker['started'] + 60, ledger.header['deadline'])

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
    terminal = True
    for worker in workers_started:
        thread = worker['thread']
        try:
            thread.join(timeout=0)
        except RuntimeError:  # a thread that failed to start was never joined
            terminal = False
            continue
        if thread.is_alive():
            terminal = False
    if not terminal:
        failure = failure or 'finite_worker_unjoined'
    return CoverageCertificate(ledger.header['run_id'], ledger.index,
        tuple(r.slot for r in receipts), handoff.ready_count, 1,
        final_count, terminal,
        tuple(boundaries), tuple(idle), tuple(waves),
        any((r.result.assessment or {}).get('answer_status') ==
            'pending_semantic_review' for r in receipts), failure,
        failure is None and terminal)
