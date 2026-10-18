from contextlib import ExitStack
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

    def test_real_lifecycle_ready_reply_durable_handoff_and_original_parent_commit(self):
        life, guardian, parent, identity = self.make_lifecycle()
        life.parent_event = None
        life.committed = False
        life.status = {'state': 'starting'}
        channel = SimpleNamespace(retained=False, receive=Mock())
        original = dict(command='handoff', channel=channel, peer=identity)
        life.server.events.append(original)
        self.assertIsNone(life.poll(time.monotonic()))
        self.assertIs(life.parent_event, original)
        self.assertFalse(life.commit_event.is_set())

        life.on_ready(dict(run=str(self.root), identity=life.record['child']))
        ready = life.server.replies[-1]
        self.assertEqual(ready['state'], 'ready')
        self.assertEqual(ready['finite_readiness_sha256'], 'A'*64)
        self.assertEqual(ready['finite_workload_sha256'], WORKLOAD_SHA256)

        wrong_channel = dict(command='commit', channel=object(), peer=identity)
        life.server.events.append(wrong_channel)
        self.assertIsNone(life.poll(time.monotonic()))
        self.assertEqual(life.server.replies[-1], {'state': 'refused'})
        self.assertFalse(life.commit_event.is_set())
        self.assertFalse((self.root/'handoff.json').exists())

        wrong_peer = dict(command='commit', channel=channel, peer=dict(identity, pid=88))
        life.server.events.append(wrong_peer)
        self.assertIsNone(life.poll(time.monotonic()))
        self.assertEqual(life.server.replies[-1], {'state': 'refused'})
        self.assertFalse(life.commit_event.is_set())

        life.server.events.append(dict(command='commit', channel=channel, peer=identity))
        self.assertIsNone(life.poll(time.monotonic()))
        self.assertTrue(life.committed)
        self.assertTrue(life.commit_event.is_set())
        import json
        handoff = json.loads((self.root/'handoff.json').read_text(encoding='utf-8'))
        self.assertEqual(handoff['state'], 'committed')
        self.assertEqual(handoff['finite_readiness_sha256'], 'A'*64)
        self.assertEqual(handoff['finite_workload_sha256'], WORKLOAD_SHA256)

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
