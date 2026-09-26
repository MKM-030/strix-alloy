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
        # Completion time, not polling time, determines whether a query was slow.
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


def finish_query(query, log_path, phase):
    while True:
        value = query.poll()
        if value is not None:
            log_frame(log_path, value, phase)
            return value
        time.sleep(POLL_SECONDS)


def collect_one(collect, log_path, phase, previous_start=None):
    if previous_start is not None:
        time.sleep(max(0, previous_start+QUERY_INTERVAL-time.monotonic()))
    return finish_query(Query(collect), log_path, phase)


def collect_baseline(collect, log_path):
    frames = []
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        frame = collect_one(collect, log_path, 'baseline',
                            frames[-1].query_start if frames else None)
        frames.append(frame)
        if len(frames) >= 5 and frame.query_end-frames[0].query_start >= 10:
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
                frame = query.poll()
                if frame is not None:
                    reasons = runtime_reasons(probe, base, frame,
                                               now=time.monotonic(), now_utc=utcnow())
                    log_frame(evidence, frame, 'running')
                    if reasons:
                        raise ValueError('runtime:' + ','.join(reasons))
                    last = frame
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
            # Construction failure without an owner means winjob confirmed cleanup.
            exited = True
        if query is not None:
            # Drain this same in-flight query only to its original deadline.
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
                time.sleep(max(0, last_query_start+QUERY_INTERVAL-time.monotonic()))
                query = Query(collect)
                try:
                    frame = finish_query(query, evidence, 'recovery')
                finally:
                    collector_terminal = query.done.is_set()
                    if not collector_terminal:
                        failure = (failure or '')+';collector_still_active'
                last_query_start = frame.query_start
                recovery_samples = (recovery_samples+[frame])[-5:]
                if time.monotonic() > end:
                    break
                fresh = not runtime_reasons(probe, base, frame,
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
