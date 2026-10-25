"""CPU-only regression for management stalls during independent memory guarding."""
import ast
from concurrent.futures import Future
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[2] / 'backends/halogen-wsl2-0.18.15/scripts/service.py'


class ManualExecutor:
    def __init__(self, **kwargs):
        self.jobs = []
        self.closed = False

    def submit(self, function):
        future = Future()
        self.jobs.append((function, future))
        return future

    def shutdown(self, **kwargs):
        self.closed = True
        for _, future in self.jobs:
            if not future.done():
                future.cancel()


class WatchdogTests(unittest.TestCase):
    def load(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        selected = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                    and n.name in ('OwnedInspection', 'guard')]
        self.assertTrue(any(n.name == 'OwnedInspection' for n in selected),
                        'Independent bounded ownership worker must exist')
        clock = types.SimpleNamespace(now=0.0)
        clock.monotonic = lambda: clock.now
        clock.time = lambda: clock.now
        clock.sleep = lambda seconds: setattr(clock, 'now', clock.now + seconds)
        scope = dict(time=clock, subprocess=subprocess, ThreadPoolExecutor=ManualExecutor,
                     json=json, sys=types.SimpleNamespace(stderr=None))
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), 'exec'), scope)
        return scope, clock

    def test_stalled_inspection_keeps_sampling_and_lease_then_expires_closed(self):
        scope, clock = self.load()
        writes, frames, stopped = [], [], []
        manifest = dict(sources={}, run_id='owned-run')
        def read(path):
            return {'manifest.json': manifest, 'container.json': {'id': 'owned-cid'},
                    'controller.json': {'run_id': 'owned-run'},
                    'current-service.json': {'run_id': 'owned-run', 'phase': 'ready'}}[path.name]
        def frame():
            frames.append(clock.now)
            return {'available_bytes': 32 * 2**30, 'commit_headroom_bytes': 64 * 2**30}
        def save(path, value):
            writes.append((clock.now, path.name, value))
        runner = types.SimpleNamespace(configure=lambda: None,
            inspect=lambda cid: {'State': {'Running': True}},
            load_module=lambda *args: types.SimpleNamespace(frame=frame))
        scope.update(r=runner, read=read, source_hashes=lambda: {},
            reject_unqualified_manifest_overrides=lambda m: None,
            logger=lambda *a, **kw: types.SimpleNamespace(info=lambda *a: None),
            ROOT=Path('.'), STATE_PATH=Path('current-service.json'), fresh=lambda *a: True,
            owned=lambda *a, **kw: None, check_runtime_frame=lambda *a: None,
            atomic=save, lease_record=lambda run, seq: {'sequence': seq},
            stop_owned=lambda *a: stopped.append(clock.now))
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(scope['guard'](Path(temporary)), 2)
        leases = [stamp for stamp, name, _ in writes if name == 'lease.json']
        failures = [value for _, name, value in writes if name == 'guard-failure.json']
        self.assertEqual(frames, list(range(31)))
        self.assertEqual(leases, list(range(30)))
        self.assertIn('ownership inspection stale', failures[0]['error'])
        self.assertEqual(stopped, [30])

    def test_changed_ownership_propagates_and_executor_is_closed(self):
        scope, clock = self.load()
        worker = scope['OwnedInspection'](lambda: None)
        worker.poll()
        self.assertEqual(len(worker.executor.jobs), 1)
        worker.executor.jobs[0][1].set_exception(ValueError('container ownership changed'))
        with self.assertRaisesRegex(ValueError, 'ownership changed'):
            worker.poll()
        worker.close()
        self.assertTrue(worker.executor.closed)

    def test_transient_timeout_does_not_extend_ownership_freshness(self):
        scope, clock = self.load()
        worker = scope['OwnedInspection'](lambda: None)
        worker.poll()
        worker.executor.jobs[0][1].set_exception(subprocess.TimeoutExpired('inspect', 10))
        clock.now = 10
        worker.poll()
        clock.now = 30
        with self.assertRaisesRegex(RuntimeError, 'ownership inspection stale'):
            worker.poll()
        worker.close()

    def test_completed_fresh_result_is_harvested_after_delayed_poll(self):
        scope, clock = self.load()
        worker = scope['OwnedInspection'](lambda: None)
        worker.poll()
        worker.executor.jobs[0][1].set_result(29)
        clock.now = 40
        worker.poll()
        self.assertEqual(worker.last_success, 29)
        worker.close()

    def test_completed_old_result_still_expires(self):
        scope, clock = self.load()
        worker = scope['OwnedInspection'](lambda: None)
        worker.poll()
        worker.executor.jobs[0][1].set_result(1)
        clock.now = 31
        with self.assertRaisesRegex(RuntimeError, 'ownership inspection stale'):
            worker.poll()
        worker.close()

    def test_inspect_timeout_uses_files_and_bounded_reap_without_pipe_drain(self):
        tree = ast.parse(SOURCE.with_name('runner.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'inspect')
        calls = []
        class Process:
            def wait(self, timeout=None):
                calls.append(('wait', timeout))
                if len([c for c in calls if c[0] == 'wait']) == 1:
                    raise subprocess.TimeoutExpired('fake-inspect', timeout)
                return 0
            def kill(self): calls.append(('kill',))
            def communicate(self, *a, **kw):
                raise AssertionError('Pipe drainage must never be used')
        def popen(argv, **kwargs):
            self.assertNotEqual(kwargs['stdout'], subprocess.PIPE)
            self.assertNotEqual(kwargs['stderr'], subprocess.PIPE)
            self.assertTrue(hasattr(kwargs['stdout'], 'fileno'))
            return Process()
        scope = dict(subprocess=subprocess, tempfile=tempfile, json=json, WSL=['fake-wsl'])
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), scope)
        with patch.object(subprocess, 'Popen', side_effect=popen):
            with self.assertRaises(subprocess.TimeoutExpired):
                scope['inspect']('owned-cid')
        self.assertEqual(calls, [('wait', 10), ('kill',), ('wait', 5)])


if __name__ == '__main__':
    unittest.main()
