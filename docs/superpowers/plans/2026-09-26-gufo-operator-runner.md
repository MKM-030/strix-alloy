# Bounded GUFO Operator Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement these tasks with independent review between them. Planning creates only this private report; implementation/GPU execution is not performed here.

**Goal:** Run one pinned model-free operator under job ownership, an independent telemetry watchdog, durable evidence and fail-closed cleanup state.

**Architecture:** A small persistence/provenance module supports a foreground runner. The runner consumes the reviewed pure operator policy and OwnedProcess APIs; its main thread owns the process and deadlines while one daemon worker performs each non-overlapping telemetry query. No detached service, HTTP, general command runner or mutable model qualification.

**Tech Stack:** Existing Python standard library, Windows msvcrt lock, existing gufo_control modules, unittest.

## Global Constraints

- Integration root `C:\Projects\strix-alloy-research\integration`. All implementation paths below are relative to it.
- Before every test command, set `$env:PYTHONPATH = Join-Path $PWD 'scripts'` from that root in the child shell. This absolute path is mandatory because existing guardian tests launch Python from temporary working directories; a relative `scripts` path breaks their imports.
- Consume `operator_policy` exactly as specified in `reports/gufo-operator-policy-plan-20260926.md`: PROBES, Frame, Baseline, baseline, admission_reasons, runtime_reasons, recovery_reasons. No fake model revision or alteration of policy constants.
- Reviewed winjob at9d3ed93: `OwnedProcess(argv, cwd=..., env=..., stdout_path=..., stderr_path=...)`; `identity`; `resume()`; `wait(timeout_ms=0)`; `exit_code()`; `close(timeout_ms=...)`. Construction is suspended and job-assigned; both log paths exclusive. Construction exceptions may carry `.owner` requiring cleanup.
- Query duration<=2s; final prelaunch age<=2s; current sample age<=5s; active query watchdog2s independent of blocking collector. Physical49/24GiB and commit12GiB remain fixed. No more than one query at a time; starts>=1s apart.
- Only CLI `python -m gufo_control.operator_probe gdn` or `... iq-experts`. One launch maximum. Fixed paths and profiles; no override flags, reset flag, fake telemetry CLI or model/server target.
- A GDN successful outcome must precede IQ. Invocation of the IQ command follows the parent's review of GDN evidence; the CLI's hard gate requires that successful saved result. It does not manufacture a human review token. Repeating either stage or recovering a stale latch requires separate engineering review; no automatic retries.
- An OS process lock prevents concurrent invocations; durable latch survives crashes. Store original sequence Baseline after GDN; IQ collects a fresh stable series for eligibility but compares run/recovery against the saved original baseline.
- Source/hash verification is before final telemetry; executable/DLL metadata and source HEAD/clean status are rechecked after final telemetry and before creation. Freshness rechecked after suspended creation, before resume. No concurrent build/update is permitted. Metadata recheck does not defend against a malicious replacement preserving size/mtime; do not claim it does.
- Preserve full stdout/stderr, raw snapshots, manifest and failed results. Main-thread disk writes and OS APIs cannot provide hard real-time guarantees under an OS/driver/filesystem hang. Worker isolation avoids ordinary blocked collection delaying the watchdog; it cannot prevent a driver freeze.
- Future implementer runs only listed offline/mocked and harmless child tests, not the production CLI. No GPU/model/WSL work or publication. Commits only if authorized by parent.

### Task 1: Foreground watchdog, recovery and fixed CLI

**Create:** `scripts/gufo_control/operator_probe.py`, `tests/gufo/test_operator_probe.py`.

- [ ] Add the complete runner tests below first, observe focused import failure, then add this complete runner.

```python
"""Foreground guardian for exactly one allowlisted operator probe."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
import uuid

from . import operator_store as store
from .operator_policy import (PROBES, Frame, baseline, admission_reasons,
    runtime_reasons, recovery_reasons, MAX_QUERY_SECONDS, MAX_SAMPLE_AGE_SECONDS)
from .telemetry import collect_snapshot
from .winjob import OwnedProcess

POLL_SECONDS = 0.05
QUERY_INTERVAL = 1.0
RECOVERY_SECONDS = 60.0


def utcnow():
    return datetime.now(timezone.utc)


class Query:
    def __init__(self, collect):
        self.started = time.monotonic()
        self.ended = None
        self.value = None
        self.done = threading.Event()
        def work():
            try:
                snapshot = collect()
                self.ended = time.monotonic()
                self.value = Frame(snapshot, self.started, self.ended, utcnow())
            except BaseException as error:
                self.ended = time.monotonic()
                self.value = error
            finally:
                self.done.set()
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()

    def poll(self):
        # Deadline uses completion time if done; scheduling delay cannot hide a slow call.
        end = self.ended if self.done.is_set() else time.monotonic()
        if end - self.started > MAX_QUERY_SECONDS:
            raise TimeoutError('active_query_timeout')
        if not self.done.is_set():
            return None
        if isinstance(self.value, BaseException):
            raise RuntimeError('telemetry_error') from self.value
        return self.value


def log_frame(path, frame, phase):
    value = asdict(frame)
    value['validated_utc'] = frame.validated_utc.isoformat()
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'phase': phase, 'frame': value}, allow_nan=False)+'\n')
        stream.flush()


def collect_one(collect, log_path, phase, previous_start=None):
    if previous_start is not None:
        time.sleep(max(0, previous_start+QUERY_INTERVAL-time.monotonic()))
    query = Query(collect)
    while True:
        value = query.poll()
        if value is not None:
            log_frame(log_path, value, phase)
            return value
        time.sleep(POLL_SECONDS)


def collect_baseline(collect, log_path):
    frames = []
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        f = collect_one(collect, log_path, 'baseline', frames[-1].query_start if frames else None)
        frames.append(f)
        if len(frames) >= 5 and f.query_end-frames[0].query_start >= 10:
            return baseline(frames), frames[-1]
    raise TimeoutError('baseline_timeout')


def _run_owned(probe, base, final, run_dir, manifest, env, *,
               owned_factory=OwnedProcess, collect=collect_snapshot):
    """Private injection seam for offline tests; CLI never accepts replacements."""
    run_dir = Path(run_dir)
    child = None
    query = None
    last = final
    last_query_start = final.query_start
    code = None
    numerical_pass = False
    failure = None
    exited = False
    collector_terminal = True
    recovered = False
    identity = None
    runtime_samples = 0
    recovery_samples = []
    evidence = run_dir/'telemetry.jsonl'
    try:
        child = owned_factory([manifest['executable']], cwd=store.BUILD, env=env,
            stdout_path=run_dir/'stdout.log', stderr_path=run_dir/'stderr.log')
        identity = child.identity
        store.atomic_json(run_dir/'owned.json', identity)
        reasons = admission_reasons(probe, base, final, now=time.monotonic(), now_utc=utcnow())
        if reasons:
            raise ValueError('pre_resume:' + ','.join(reasons))
        # Persist before resume; root latch was written before construction.
        store.atomic_json(run_dir/'phase.json', {'phase': 'resuming', 'identity': identity})
        # I/O can consume freshness; check again directly before resume.
        reasons = admission_reasons(probe, base, final, now=time.monotonic(), now_utc=utcnow())
        if reasons:
            raise ValueError('pre_resume:' + ','.join(reasons))
        deadline = time.monotonic()+probe.deadline_seconds
        child.resume()
        while True:
            now = time.monotonic()
            if now >= deadline:
                raise TimeoutError('execution_timeout')
            if query is not None:
                f = query.poll()
                if f is not None:
                    reasons = runtime_reasons(probe, base, f, now=time.monotonic(), now_utc=utcnow())
                    log_frame(evidence, f, 'running')
                    if reasons:
                        raise ValueError('runtime:' + ','.join(reasons))
                    last = f
                    runtime_samples += 1
                    query = None
            # Revalidate the actual previous sample, including UTC age.
            reasons = runtime_reasons(probe, base, last, now=time.monotonic(), now_utc=utcnow())
            if reasons:
                raise ValueError('runtime:' + ','.join(reasons))
            if child.wait(0):
                code = child.exit_code()
                numerical_pass = code == 0
                if code != 0:
                    failure = 'nonzero_exit'
                break
            if query is None and now-last_query_start >= QUERY_INTERVAL:
                query = Query(collect)
                last_query_start = query.started
            time.sleep(POLL_SECONDS)
    except BaseException as error:
        failure = type(error).__name__ + ':' + str(error)
        if child is None:
            child = getattr(error, 'owner', None)
            if child is not None:
                identity = child.identity
    finally:
        if child is not None:
            try:
                child.close(timeout_ms=10000)
                exited = True
                if code is None:
                    code = child.exit_code()
            except BaseException as error:
                failure = (failure or '')+';cleanup:'+type(error).__name__+':'+str(error)
        else:
            # A construction failure without an owner means winjob confirmed cleanup.
            exited = True
        if query is not None:
            # Drain this SAME in-flight query only to its original deadline.
            # Child exit is independent from collector completion.
            try:
                while True:
                    pending = query.poll()
                    if pending is not None:
                        log_frame(evidence, pending, 'pending_after_exit')
                        reasons = runtime_reasons(probe, base, pending,
                            now=time.monotonic(), now_utc=utcnow())
                        if reasons:
                            raise ValueError('pending:' + ','.join(reasons))
                        break
                    time.sleep(POLL_SECONDS)
            except BaseException as error:
                failure = (failure or '')+';pending:'+type(error).__name__+':'+str(error)
            collector_terminal = query.done.is_set()
            if not collector_terminal:
                failure = (failure or '')+';collector_still_active'
    if exited and collector_terminal:
        end = time.monotonic()+RECOVERY_SECONDS
        try:
            while time.monotonic() < end:
                f = collect_one(collect, evidence, 'recovery', last_query_start)
                last_query_start = f.query_start
                recovery_samples = (recovery_samples+[f])[-5:]
                if time.monotonic() > end:
                    break
                fresh = not runtime_reasons(probe, base, f,
                    now=time.monotonic(), now_utc=utcnow())
                if (len(recovery_samples) == 5 and fresh
                        and not recovery_reasons(base, recovery_samples)):
                    recovered = True
                    break
        except BaseException as error:
            failure = (failure or '')+';recovery:'+type(error).__name__+':'+str(error)
    if not recovered:
        failure = (failure or '')+';recovery_unconfirmed'
    return {'success': failure is None and code == 0 and exited and recovered,
            'numerical_pass': numerical_pass,
            'exit_code': code, 'failure': failure, 'identity': identity,
            'owned_exit_confirmed': exited,
            'collector_terminal': collector_terminal,
            'cleanup_confirmed': exited and collector_terminal and recovered,
            'runtime_samples': runtime_samples,
            'runtime_peak_evidence': 'sampled_lower_bound' if runtime_samples else 'unknown',
            'original_baseline': asdict(base), 'manifest': manifest,
            'recovery_samples': len(recovery_samples)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='One pinned model-free GUFO operator probe')
    parser.add_argument('probe', choices=tuple(PROBES))
    args = parser.parse_args(argv)
    probe = PROBES[args.probe]
    if os.name != 'nt':
        parser.error('Windows required')
    try:
        with store.exclusive(store.EVIDENCE):
            original = store.sequence_baseline(store.EVIDENCE, probe.key)
            run_dir = store.EVIDENCE/(utcnow().strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
            run_dir.mkdir()
            try:
                manifest = store.verify(probe)
                env = store.child_environment(dict(os.environ))
                manifest['environment_changes'] = {
                    'cleared_gufo_names': sorted(k for k in os.environ
                                                if k.upper().startswith('GUFO_')),
                    'HIP_PATH': str(store.SDK),
                    'HIP_DEVICE_LIB_PATH': str(store.SDK/'lib/llvm/amdgcn/bitcode'),
                    'path_prefix': [str(store.SDK/'bin'), str(store.SDK/'lib/llvm/bin')]}
                store.atomic_json(run_dir/'manifest.json', manifest)
                observed, last = collect_baseline(collect_snapshot, run_dir/'telemetry.jsonl')
                base = observed if original is None else original
                # Original baseline identity/threshold validity is checked by policy below.
                store.recheck(manifest)
                final = collect_one(collect_snapshot, run_dir/'telemetry.jsonl',
                                    'final_prelaunch', last.query_start)
                store.recheck(manifest)
                reasons = admission_reasons(probe, base, final,
                                            now=time.monotonic(), now_utc=utcnow())
                if reasons:
                    raise ValueError('admission:' + ','.join(reasons))
                store.begin(store.EVIDENCE, run_dir, probe, base)
                result = _run_owned(probe, base, final, run_dir, manifest, env)
                store.finish(store.EVIDENCE, run_dir, probe, base, result)
                print(json.dumps({'run': str(run_dir), 'success': result['success'],
                                  'cleanup_confirmed': result['cleanup_confirmed']}))
                return 0 if result['success'] else 1
            except BaseException as error:
                store.atomic_json(run_dir/'refused.json',
                    {'error': type(error).__name__+':'+str(error)})
                raise
    except Exception as error:
        print(json.dumps({'refused': type(error).__name__+':'+str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
```

```python
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
    def resume(self):
        self.resumed = True
    def wait(self, timeout_ms=0):
        return self.finished
    def exit_code(self):
        return self.code
    def close(self, timeout_ms=5000):
        if self.close_error:
            raise TimeoutError('exit uncertain')
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
            if isinstance(child, BaseException):
                raise child
            return child
        with ExitStack() as stack:
            for key, value in settings.items():
                stack.enter_context(patch.object(runner, key, value))
            return runner._run_owned(probe or PROBES['gdn'], base, final, folder,
                {'executable': 'fake'}, {}, owned_factory=factory,
                collect=collect)

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
            self.assertFalse(child.resumed)
            self.assertTrue(child.closed)
            self.assertFalse(result['success'])

    def test_blocked_collector_cannot_block_owned_stop(self):
        release = threading.Event()
        def blocked():
            release.wait(3)
            return snapshot()
        try:
            with tempfile.TemporaryDirectory() as folder:
                child = FakeChild(finished=False)
                started = time.monotonic()
                result = self.invoke(folder, child, blocked, MAX_QUERY_SECONDS=0.05)
                self.assertLess(time.monotonic()-started, 1)
                self.assertTrue(child.closed)
                self.assertIn('active_query_timeout', result['failure'])
                self.assertFalse(result['cleanup_confirmed'])
        finally:
            release.set()

    def test_runtime_rejection_and_recovery_residual(self):
        with tempfile.TemporaryDirectory() as folder:
            child = FakeChild(finished=False)
            result = self.invoke(folder, child,
                runtime_reasons=lambda *a, **k: ['physical_envelope'],
                recovery_reasons=lambda *a, **k: ['gpu_not_recovered'])
            self.assertTrue(child.closed)
            self.assertIn('physical_envelope', result['failure'])
            self.assertFalse(result['cleanup_confirmed'])

    def test_cleanup_error_keeps_uncertainty(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.invoke(folder, FakeChild(close_error=True))
            self.assertFalse(result['cleanup_confirmed'])
            self.assertIn('cleanup', result['failure'])

    def test_execution_deadline_and_constructor_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            child = FakeChild(finished=False)
            result = self.invoke(folder, child,
                probe=replace(PROBES['gdn'], deadline_seconds=0.03))
            self.assertTrue(child.closed)
            self.assertIn('execution_timeout', result['failure'])
            owner = FakeChild()
            error = RuntimeError('setup uncertain')
            error.owner = owner
            result = self.invoke(folder, error)
            self.assertFalse(owner.resumed)
            self.assertTrue(owner.closed)
            self.assertFalse(result['success'])

    def test_owned_evidence_write_failure_stops_child(self):
        with tempfile.TemporaryDirectory() as folder:
            child = FakeChild()
            with patch.object(runner.store, 'atomic_json', side_effect=OSError('disk')):
                result = self.invoke(folder, child)
            self.assertFalse(child.resumed)
            self.assertTrue(child.closed)
            self.assertIn('disk', result['failure'])

    def test_unknown_cli_cannot_launch(self):
        with patch.object(runner, 'OwnedProcess') as process, redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit):
                runner.main(['anything-else'])
            process.assert_not_called()
            self.assertIn('invalid choice', errors.getvalue())

    def test_fast_exit_drains_same_query(self):
        started = threading.Event()
        class FastChild(FakeChild):
            def wait(self, timeout_ms=0):
                return started.is_set()
        calls = 0
        def collect():
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                time.sleep(0.04)
            return snapshot()
        with tempfile.TemporaryDirectory() as folder:
            result = self.invoke(folder, FastChild(), collect)
            self.assertTrue(result['success'])
            self.assertTrue(result['owned_exit_confirmed'])
            self.assertTrue(result['collector_terminal'])
            self.assertIn('pending_after_exit', (Path(folder)/'telemetry.jsonl').read_text())

    def test_real_policy_wiring_and_actual_recovery_cadence(self):
        now, utc = time.monotonic(), datetime.now(timezone.utc)
        history = []
        for i in range(6):
            offset = -20+2*i
            start = now+offset
            stamp = utc+timedelta(seconds=offset)
            history.append(Frame(valid_snapshot(start, stamp), start, start+1.5,
                                 stamp+timedelta(seconds=1.5)))
        base = baseline(history)
        start = time.monotonic()
        data = valid_snapshot()
        final = Frame(data, start, time.monotonic(), datetime.now(timezone.utc))
        child = FakeChild()
        with tempfile.TemporaryDirectory() as folder:
            result = runner._run_owned(PROBES['gdn'], base, final, folder,
                {'executable': 'private-fake-child'}, {},
                owned_factory=lambda *a, **k: child, collect=valid_snapshot)
            self.assertTrue(result['success'], result)
            self.assertEqual(result['recovery_samples'], 5)
            self.assertGreaterEqual(time.monotonic()-start, 4)
            self.assertEqual(result['original_baseline']['available_min'], 52*GIB)

    def test_query_completion_time_and_exception(self):
        def fail():
            raise ValueError('collector failed')
        query = runner.Query(fail)
        self.assertTrue(query.done.wait(1))
        with self.assertRaisesRegex(RuntimeError, 'telemetry_error'):
            query.poll()
        query = runner.Query(snapshot)
        self.assertTrue(query.done.wait(1))
        query.ended = query.started+2.001
        with self.assertRaisesRegex(TimeoutError, 'active_query_timeout'):
            query.poll()

    @unittest.skipUnless(os.name == 'nt', 'Windows owned harmless child')
    def test_real_python_child_output_under_runner(self):
        with tempfile.TemporaryDirectory() as folder:
            def factory(argv, *, cwd, env, stdout_path, stderr_path):
                return OwnedProcess([sys.executable, '-c',
                    "import sys; print('hello'); print('error-stream', file=sys.stderr)"],
                    cwd=folder, env=dict(os.environ), stdout_path=stdout_path, stderr_path=stderr_path)
            now = time.monotonic()
            f = Frame(snapshot(), now, now, datetime.now(timezone.utc))
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


if __name__ == '__main__':
    unittest.main()
```

- [ ] From the integration root set `$env:PYTHONPATH = Join-Path $PWD 'scripts'`, then run focused runner tests with `python -m unittest discover -s tests/gufo -p test_operator_probe.py -v`. Expect12 tests passing on Windows. Lifecycle isolation tests mock pure decisions; the additional valid-normalized-frame test uses real policy with actual1s recovery cadence and a fake child. The independent pure-policy suite covers boundary arithmetic. No production CLI call is made with an accepted profile.
- [ ] With the same absolute PYTHONPATH, run the entire `python -m unittest discover -s tests/gufo -v` once. Existing winjob tests cover guardian death, descendant kill, suspended creation, setup `.owner` cleanup, exclusive logs and cached exit codes. Require all tests passing; investigate failures without launching GUFO.
- [ ] Review this task's diff for only its two new owned files, fixed paths/allowlist, no model admissions, evidence preservation and no CLI bypass. Parent authorizes a local runner-task commit: `git add scripts/gufo_control/operator_probe.py tests/gufo/test_operator_probe.py` then `git commit -m "feat: add bounded GUFO operator probe runner"`; return commit and test summary for independent review. No numerical/GPU launch is part of this implementation dispatch. This plan itself performs no commit.

## Review concerns and limits

After owned-process cleanup, drain the same pending query only until its original2s deadline and validate/log its result. Do not start a recovery query until it is terminal. If it remains active, preserve the separate true owned-exit flag while marking collector completion and overall cleanup unconfirmed; the latch blocks another launch. A separate read-only recovery review may resolve that state; no automatic latch-reset command exists. Native process close gets10s and recovery gets60s; a single in-flight recovery query can consume up to2s before failing its watchdog, plus polling jitter. OS calls and disk writes can still block beyond those operational targets.

One known practical risk is source rechecking after a1.5s final query: it leaves only~0.5s before the strict2s prelaunch age. This may fail closed on slow Git/process startup. Do not silently shift capture time or weaken the age bound. If observed, review moving the costly source check before the final query while retaining cheap immutable-artifact stamp rechecks after it; that is a later reviewed implementation change, not an invitation to bypass freshness now.

The runtime evidence log contains all observed samples; observed extrema can be computed from it, but no claim of true instantaneous peak is made. A zero-exit probe without runtime samples reports unknown peak. Static DLL hashing records the existing SDK but does not prove dynamically loaded driver compatibility. Parent must inspect numerical logs and recovery evidence before IQ; passing operators does not qualify model/server execution.

Self-review: code/test blocks are complete with defined helpers; no placeholders or arbitrary production factory arguments. The main thread polls active-query2s and policy sample5s independently; original baseline persists. Tests use fake objects or harmless Python only. This plan has not been executed; independent review remains necessary before dispatch.
