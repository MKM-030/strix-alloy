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
        self.early_terminal_emitted = threading.Event()
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
        if kind == 'post' and ordinal == 44 and self.early_terminal == 43:
            if not self.early_terminal_emitted.wait(timeout=10):
                raise TimeoutError('synthetic_early_terminal')
        self.emit(row['slot'], 'sent', now)
        if post:
            self.emit(row['slot'], 'first_content', now)
        if kind == 'post' and ordinal == self.hang_post:
            self.hang_release.wait(timeout=30)
        if ordinal in (43,44) and kind == 'post' and ordinal != self.early_terminal:
            if not self.wave_gates[45].wait(timeout=10):
                raise TimeoutError('synthetic_wave_gate')
            if self.third_early and not self.third_returned[45].wait(timeout=10):
                raise TimeoutError('synthetic_third_return')
        if ordinal in (46,47) and kind == 'post' and ordinal != self.early_terminal:
            if not self.wave_gates[48].wait(timeout=10):
                raise TimeoutError('synthetic_wave_gate')
            if self.third_early and not self.third_returned[48].wait(timeout=10):
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
        if kind == 'post' and ordinal == 43 and self.early_terminal == 43:
            self.early_terminal_emitted.set()
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
                   late_ready=None, join_timeout=20):
        ledger, workload, transport = self.synthetic_setup(index=2,
            ready_statuses=ready_statuses, fail_ready=fail_ready,
            late_ready=late_ready)
        class Marker:
            def poll(self, deadline):
                return True
        task = start_readiness(workload, ledger, transport, Marker(),
            startup_deadline=580.0, lifetime_deadline=1000.0,
            clock=self.clock, pause=self.pause)
        task.thread.join(timeout=join_timeout)
        self.assertFalse(task.thread.is_alive(), f'completed {len(transport.calls)} calls')
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

    def test_final_snapshot_crossing_lifecycle_deadline_refuses_completion(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True)
        original_snapshot = ledger.snapshot
        calls = 0
        def crossing_snapshot():
            nonlocal calls
            calls += 1
            result = original_snapshot()
            if calls == 2:
                self.advance(ledger.header['deadline'] - .1 - self.clock())
            elif calls == 3:
                self.advance(ledger.header['deadline'] - self.clock())
            return result
        ledger.snapshot = crossing_snapshot
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause)
        self.assertEqual(calls, 3)
        self.assertEqual(certificate.post_count, 6)
        self.assertFalse(certificate.complete)
        self.assertIn('finite_client_lost_or_deadline', certificate.failure)
        self.assertEqual(transport.calls[-1], 'post-006')

    def test_stop_during_final_snapshot_refuses_completion(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True)
        stopped = threading.Event()
        original_snapshot = ledger.snapshot
        calls = 0
        def stopping_snapshot():
            nonlocal calls
            calls += 1
            result = original_snapshot()
            if calls == 3:
                stopped.set()
            return result
        ledger.snapshot = stopping_snapshot
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause,
            stop_event=stopped)
        self.assertEqual(calls, 3)
        self.assertEqual(certificate.post_count, 6)
        self.assertFalse(certificate.complete)
        self.assertIn('finite_client_lost_or_deadline', certificate.failure)
        self.assertEqual(transport.calls[-1], 'post-006')

    def test_parent_loss_during_final_snapshot_refuses_completion(self):
        ledger, workload, transport = self.synthetic_setup(index=2,
            readiness_complete=True)
        alive = [True]
        original_snapshot = ledger.snapshot
        calls = 0
        def losing_snapshot():
            nonlocal calls
            calls += 1
            result = original_snapshot()
            if calls == 3:
                alive[0] = False
            return result
        ledger.snapshot = losing_snapshot
        certificate = run_remaining(workload, ledger, transport,
            self.handoff(ledger), clock=self.clock, pause=self.pause,
            parent_alive=lambda: alive[0])
        self.assertEqual(calls, 3)
        self.assertEqual(certificate.post_count, 6)
        self.assertFalse(certificate.complete)
        self.assertIn('finite_client_lost_or_deadline', certificate.failure)
        self.assertEqual(transport.calls[-1], 'post-006')

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

    def test_certificate_joins_workers_that_finished_before_collection(self):
        ledger, workload, transport = self.synthetic_setup(index=1,
            readiness_complete=True)
        class DelayedThirdQueue:
            def __init__(self):
                self.items = queue.SimpleQueue()
            def put_nowait(self, item):
                self.items.put_nowait(item)
            def get(self, timeout):
                item = self.items.get(timeout=timeout)
                if item.slot in ('post-045', 'post-048') and item.event == 'sent':
                    end = time.monotonic() + 30
                    wave = ({43, 44, 45} if item.slot == 'post-045'
                            else {46, 47, 48})
                    while any(thread.name == f'gufo-finite-wave-{n}'
                              for thread in threading.enumerate() for n in wave):
                        if time.monotonic() >= end:
                            raise TimeoutError('synthetic_worker_finish')
                        threading.Event().wait(.001)
                return item
        joined = set()
        original_join = threading.Thread.join
        def recording_join(thread, *args, **kwargs):
            result = original_join(thread, *args, **kwargs)
            if thread.name.startswith('gufo-finite-wave-'):
                joined.add(thread.name)
            return result
        with patch.object(threading.Thread, 'join', recording_join):
            certificate = run_remaining(workload, ledger, transport,
                self.handoff(ledger), clock=self.clock, pause=self.pause,
                milestones=DelayedThirdQueue())
        self.assertTrue(certificate.complete, certificate.failure)
        self.assertEqual(joined, {f'gufo-finite-wave-{n}'
                                 for n in (43, 44, 45, 46, 47, 48)})

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

    def test_readiness_digest_rechecks_earlier_receipt_after_its_deadline(self):
        ledger, workload, transport = self.synthetic_setup(
            index=2, ready_statuses=(503, 200))
        original_get = transport.get
        def delayed_get(kind, ordinal):
            if kind == 'ready' and ordinal == 2:
                self.advance(61)
            return original_get(kind, ordinal)
        transport.get = delayed_get
        class Marker:
            def poll(self, deadline):
                return True
        task = start_readiness(workload, ledger, transport, Marker(),
            startup_deadline=580.0, lifetime_deadline=1000.0,
            clock=self.clock, pause=self.pause)
        task.thread.join(timeout=20)
        self.assertFalse(task.thread.is_alive())
        self.assertTrue(task.result['success'], task.result)
        self.assertEqual(len(readiness_digest(task, ledger, transport,
                                              clock=self.clock)), 64)

    def test_readiness_digest_stops_if_recheck_crosses_startup_deadline(self):
        ledger, workload, transport, task = self.start_task()
        self.advance(579.9 - self.clock())
        wire = transport.evidence / 'ready-001.wire.bin'
        original_open = Path.open
        advance = self.advance
        class LateRead:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def read(self, size):
                data = self.stream.read(size)
                advance(.2)
                return data
        def opening(candidate, *args, **kwargs):
            stream = original_open(candidate, *args, **kwargs)
            return LateRead(stream) if candidate == wire and args[0] == 'rb' else stream
        with patch.object(Path, 'open', opening):
            with self.assertRaisesRegex(ValueError, 'finite_evidence_deadline'):
                readiness_digest(task, ledger, transport, clock=self.clock)

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
            ready_statuses=(503,)*240, join_timeout=600)
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
