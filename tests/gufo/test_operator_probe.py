from contextlib import ExitStack, redirect_stderr
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from gufo_control import operator_probe as runner
from gufo_control.operator_policy import Frame, Baseline, PROBES, baseline, GIB, MIB
from gufo_control.winjob import OwnedProcess


class FakeChild:
    def __init__(self, code=0, finished=True, close_error=False):
        self.identity = {'pid': 123, 'creation_time_100ns': 456, 'executable': 'fake'}
        self.code, self.finished, self.close_error = code, finished, close_error
        self.resumed = self.closed = False
    def resume(self): self.resumed = True
    def wait(self, timeout_ms=0): return self.finished
    def exit_code(self): return self.code
    def close(self, timeout_ms=5000):
        if self.close_error: raise TimeoutError('exit uncertain')
        self.closed = True


def snapshot():
    return {'captured_monotonic': time.monotonic()}


def valid_snapshot(at=None, at_utc=None):
    at = time.monotonic() if at is None else at
    at_utc = datetime.now(timezone.utc) if at_utc is None else at_utc
    identity = dict(luid='0x00000000_0x000111c1', vendor_id=0x1002,
        device_id=0x1586, subsystem_id=0x801d2014, flags=0,
        description='AMD Radeon(TM) 8060S Graphics', dedicated_video_memory=64*GIB)
    return dict(available_physical_bytes=52*GIB, host_committed_bytes=16*GIB,
        host_commit_limit_bytes=240*GIB, commit_headroom_bytes=224*GIB,
        dedicated_capacity_bytes=64*GIB, adapter_dedicated_bytes=600*MIB,
        adapter_shared_bytes=70*MIB, adapter_total_committed_bytes=800*MIB,
        adapter_luid=identity['luid'], adapter_identity=identity,
        captured_monotonic=at, sample_utc_min=at_utc.isoformat(),
        sample_utc_max=at_utc.isoformat(), telemetry_ok=True,
        provider='PDH/Get-Counter;DXGI/EnumAdapters1', gpu_scope='adapter_aggregate',
        host_scope='host_global', inventory_scope='known_engine_and_guest_names',
        other_inference_pids=[])


class RunnerTests(unittest.TestCase):
    def invoke(self, folder, child, collect=snapshot, probe=None, **patches):
        now = time.monotonic()
        final = Frame(snapshot(), now, now, datetime.now(timezone.utc))
        base = Baseline(('synthetic',), 100, 200, (1, 2, 3), 0, 11)
        settings = dict(QUERY_INTERVAL=0.001, POLL_SECONDS=0.001, RECOVERY_SECONDS=0.2,
                        admission_reasons=lambda *a, **k: [],
                        runtime_reasons=lambda *a, **k: [],
                        recovery_reasons=lambda *a, **k: [])
        settings.update(patches)
        def factory(*args, **kwargs):
            if isinstance(child, BaseException): raise child
            return child
        with ExitStack() as stack:
            for key, value in settings.items(): stack.enter_context(patch.object(runner, key, value))
            return runner._run_owned(probe or PROBES['gdn'], base, final, folder,
                {'executable': 'fake'}, {}, owned_factory=factory, collect=collect)

    def test_success_and_nonzero_preserve_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            for code in (0, 1):
                child = FakeChild(code=code)
                result = self.invoke(folder, child)
                self.assertEqual(result['success'], code == 0)
                self.assertTrue(result['cleanup_confirmed'])
                self.assertTrue(child.resumed and child.closed)

    def test_pre_resume_rejection_never_resumes(self):
        with tempfile.TemporaryDirectory() as folder:
            child = FakeChild()
            result = self.invoke(folder, child, admission_reasons=lambda *a, **k: ['stale'])
            self.assertFalse(child.resumed); self.assertTrue(child.closed)
            self.assertFalse(result['success'])

    def test_blocked_collector_cannot_block_owned_stop(self):
        release = threading.Event()
        def blocked(): release.wait(3); return snapshot()
        try:
            with tempfile.TemporaryDirectory() as folder:
                child = FakeChild(finished=False); started = time.monotonic()
                result = self.invoke(folder, child, blocked, MAX_QUERY_SECONDS=0.05)
                self.assertLess(time.monotonic()-started, 1); self.assertTrue(child.closed)
                self.assertIn('active_query_timeout', result['failure'])
                self.assertFalse(result['cleanup_confirmed'])
        finally: release.set()

    def test_blocked_recovery_reports_collector_nonterminal(self):
        release = threading.Event()
        finished = threading.Event()
        def blocked():
            try:
                release.wait(3)
                return snapshot()
            finally:
                finished.set()
        try:
            with tempfile.TemporaryDirectory() as folder:
                child = FakeChild(finished=True)
                result = self.invoke(folder, child, blocked, MAX_QUERY_SECONDS=0.05)
                self.assertTrue(child.closed)
                self.assertTrue(result['owned_exit_confirmed'])
                self.assertFalse(finished.is_set())
                self.assertFalse(result['collector_terminal'])
                self.assertFalse(result['cleanup_confirmed'])
                self.assertFalse(result['success'])
                self.assertIn('active_query_timeout', result['failure'])
                self.assertIn('collector_still_active', result['failure'])
        finally:
            release.set()
            self.assertTrue(finished.wait(1))

    def test_runtime_rejection_and_recovery_residual(self):
        with tempfile.TemporaryDirectory() as folder:
            child = FakeChild(finished=False)
            result = self.invoke(folder, child,
                runtime_reasons=lambda *a, **k: ['physical_envelope'],
                recovery_reasons=lambda *a, **k: ['gpu_not_recovered'])
            self.assertTrue(child.closed); self.assertIn('physical_envelope', result['failure'])
            self.assertFalse(result['cleanup_confirmed'])

    def test_cleanup_error_keeps_uncertainty(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.invoke(folder, FakeChild(close_error=True))
            self.assertFalse(result['cleanup_confirmed']); self.assertIn('cleanup', result['failure'])

    def test_execution_deadline_and_constructor_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            child = FakeChild(finished=False)
            result = self.invoke(folder, child, probe=replace(PROBES['gdn'], deadline_seconds=0.03))
            self.assertTrue(child.closed); self.assertIn('execution_timeout', result['failure'])
            owner = FakeChild(); error = RuntimeError('setup uncertain'); error.owner = owner
            result = self.invoke(folder, error)
            self.assertFalse(owner.resumed); self.assertTrue(owner.closed); self.assertFalse(result['success'])

    def test_owned_evidence_write_failure_stops_child(self):
        with tempfile.TemporaryDirectory() as folder:
            child = FakeChild()
            with patch.object(runner.store, 'atomic_json', side_effect=OSError('disk')):
                result = self.invoke(folder, child)
            self.assertFalse(child.resumed); self.assertTrue(child.closed)
            self.assertIn('disk', result['failure'])

    def test_unknown_cli_cannot_launch(self):
        with patch.object(runner, 'OwnedProcess') as process, redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit): runner.main(['anything-else'])
            process.assert_not_called(); self.assertIn('invalid choice', errors.getvalue())

    def test_fast_exit_drains_same_query(self):
        started = threading.Event()
        class FastChild(FakeChild):
            def wait(self, timeout_ms=0): return started.is_set()
        calls = 0
        def collect():
            nonlocal calls
            calls += 1
            if calls == 1: started.set(); time.sleep(0.04)
            return snapshot()
        with tempfile.TemporaryDirectory() as folder:
            result = self.invoke(folder, FastChild(), collect)
            self.assertTrue(result['success']); self.assertTrue(result['owned_exit_confirmed'])
            self.assertTrue(result['collector_terminal'])
            self.assertIn('pending_after_exit', (Path(folder)/'telemetry.jsonl').read_text())

    def test_real_policy_wiring_and_actual_recovery_cadence(self):
        now, utc = time.monotonic(), datetime.now(timezone.utc); history = []
        for i in range(6):
            offset = -20+2*i; start = now+offset; stamp = utc+timedelta(seconds=offset)
            history.append(Frame(valid_snapshot(start, stamp), start, start+1.5,
                                 stamp+timedelta(seconds=1.5)))
        base = baseline(history); start = time.monotonic()
        final = Frame(valid_snapshot(), start, time.monotonic(), datetime.now(timezone.utc))
        child = FakeChild()
        with tempfile.TemporaryDirectory() as folder:
            result = runner._run_owned(PROBES['gdn'], base, final, folder,
                {'executable': 'private-fake-child'}, {}, owned_factory=lambda *a, **k: child,
                collect=valid_snapshot)
            self.assertTrue(result['success'], result); self.assertEqual(result['recovery_samples'], 5)
            self.assertGreaterEqual(time.monotonic()-start, 4)
            self.assertEqual(result['original_baseline']['available_min'], 52*GIB)

    def test_query_completion_time_and_exception(self):
        def fail(): raise ValueError('collector failed')
        query = runner.Query(fail); self.assertTrue(query.done.wait(1))
        with self.assertRaisesRegex(RuntimeError, 'telemetry_error'): query.poll()
        query = runner.Query(snapshot); self.assertTrue(query.done.wait(1))
        query.ended = query.started+2.001
        with self.assertRaisesRegex(TimeoutError, 'active_query_timeout'): query.poll()

    @unittest.skipUnless(os.name == 'nt', 'Windows owned harmless child')
    def test_real_python_child_output_under_runner(self):
        with tempfile.TemporaryDirectory() as folder:
            def factory(argv, *, cwd, env, stdout_path, stderr_path):
                return OwnedProcess([sys.executable, '-c',
                    "import sys; print('hello'); print('error-stream', file=sys.stderr)"],
                    cwd=folder, env=dict(os.environ), stdout_path=stdout_path, stderr_path=stderr_path)
            now = time.monotonic(); f = Frame(snapshot(), now, now, datetime.now(timezone.utc))
            b = Baseline(('synthetic',), 100, 200, (1, 2, 3), 0, 11)
            with patch.object(runner, 'QUERY_INTERVAL', 0.001), \
                 patch.object(runner, 'POLL_SECONDS', 0.005), \
                 patch.object(runner, 'admission_reasons', return_value=[]), \
                 patch.object(runner, 'runtime_reasons', return_value=[]), \
                 patch.object(runner, 'recovery_reasons', return_value=[]):
                result = runner._run_owned(PROBES['gdn'], b, f, folder,
                    {'executable': 'unused-private-test'}, {}, owned_factory=factory, collect=snapshot)
            self.assertTrue(result['success'])
            self.assertIn('hello', (Path(folder)/'stdout.log').read_text())
            self.assertIn('error-stream', (Path(folder)/'stderr.log').read_text())


if __name__ == '__main__': unittest.main()
