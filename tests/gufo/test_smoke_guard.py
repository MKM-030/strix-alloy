"""Offline lifecycle tests: fixed policy, synthetic counters, no model or endpoint."""
from contextlib import contextmanager, ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from gufo_control import smoke_guard as guard
from gufo_control import operator_probe, operator_store, smoke_store
from gufo_control import smoke_http
from gufo_control.operator_policy import baseline, GIB
from test_operator_policy import EPOCH, frame, series
from test_smoke_policy import manifest


class Clock:
    def __init__(self): self.value = 100.0
    def monotonic(self): return self.value
    def sleep(self, duration): self.value += max(0.00001, duration)
    def utcnow(self): return EPOCH + timedelta(seconds=self.value)


class Event:
    def __init__(self, predicate): self.predicate = predicate
    def is_set(self): return self.predicate()


class Harness:
    def __init__(self, root):
        self.root = Path(root)
        self.clock = Clock()
        self.base = baseline(series())
        self.manifest = manifest()
        self.manifest['operator'] = dict(original_baseline=asdict(self.base))
        self.events, self.queries, self.children, self.http_tasks = [], [], [], []
        self.query_changes = lambda phase, index: {}
        self.query_delay = lambda phase, index: 0.1
        self.query_error = lambda phase, index: None
        self.recheck_hook = lambda current: None
        self.port_error = None
        self.static_error = None
        self.create_error = None
        self.identity_error = False
        self.close_error = False
        self.close_delay = 0
        self.child_exit = float('inf')
        self.http_delay = 3.0
        self.http_stuck = False
        self.http_cancel_delay = 0
        self.http_result = dict(success=True, error=None, post_attempted=True, timestamps={})
        self.module_status = 'verified'
        self.module_delay = 0.1
        self.module_start_error = False
        self.duplicate_closed = True
        self.pins = replace(smoke_store.PINS, evidence=self.root)
        self.store = SimpleNamespace(EVIDENCE=self.root, BUILD=smoke_store.BUILD,
            verify_static=self.verify, recheck_static=self.recheck,
            load_original_operator_baseline=lambda: self.base,
            begin_run=self.begin, finish_run=self.finish)

    def verify(self):
        if self.static_error: raise ValueError(self.static_error)
        if (self.root/'incomplete.json').exists(): raise ValueError('prior_smoke_incomplete')
        if (self.root/'attempt.json').exists(): raise ValueError('prior_smoke_attempt')
        return deepcopy(self.manifest)

    def recheck(self, manifest, *, current_run=None):
        self.recheck_hook(current_run)
        if current_run is None:
            self.verify()
        else:
            smoke_store._current_run_markers(manifest, self.pins, current_run)

    def begin(self, run, manifest, base):
        self.recheck(manifest)
        smoke_store._begin_run(run, manifest, base, self.pins)
        self.events.append('begin')

    def finish(self, run, result):
        smoke_store._finish_run(run, result, self.pins)

    def port(self):
        self.events.append('port')
        if self.port_error: raise ValueError(self.port_error)

    @contextmanager
    def lock(self, root):
        name = 'smoke' if Path(root) == self.root else 'operator'
        self.events.append('lock:'+name)
        try: yield
        finally: self.events.append('unlock:'+name)

    def query(self, collect):
        h = self
        phase = self.guard.phase
        index = sum(q.phase == phase for q in self.queries)
        class Query:
            def __init__(self):
                self.started = h.clock.monotonic()
                self.phase = phase
                delay = h.query_delay(phase, index)
                self.ended = self.started + delay
                self.value = h.query_error(phase, index) or frame(self.started, delay,
                    **h.query_changes(phase, index))
                self.done = Event(lambda: h.clock.monotonic() >= self.ended)
            def poll(self):
                end = self.ended if self.done.is_set() else h.clock.monotonic()
                if end-self.started > 2: raise TimeoutError('active_query_timeout')
                if not self.done.is_set(): return None
                if isinstance(self.value, BaseException): raise self.value
                return self.value
        value = Query()
        self.queries.append(value)
        return value

    def owned(self, argv, *, cwd, env, stdout_path, stderr_path):
        h = self
        self.events.append('create')
        assert (self.root/'attempt.json').exists()
        assert (self.root/'incomplete.json').exists()
        class Child:
            def __init__(self):
                self.identity = dict(pid=42, creation_time_100ns=1234, executable=argv[0])
                self.resumed = self.closed = False
            def verify_live_identity(self):
                if h.identity_error or self.closed or self.wait(): raise RuntimeError('identity_lost')
                return deepcopy(self.identity)
            def resume(self):
                assert (Path(stdout_path).parent/'owned.json').exists()
                self.resumed = True
                h.events.append('resume')
                self.resume_at = h.clock.monotonic()
            def wait(self, timeout_ms=0):
                return self.closed or (self.resumed and h.clock.monotonic()-self.resume_at >= h.child_exit)
            def exit_code(self): return 1 if self.closed else 0
            def close(self, timeout_ms=0):
                h.events.append('close')
                self.closed_at = h.clock.monotonic()
                if h.close_error: raise TimeoutError('owned_exit_timeout')
                self.closed = True
                if h.close_delay: h.clock.sleep(h.close_delay)
            def inspect_modules(self, *, app_local_dir):
                h.events.append('inspect')
                start = h.clock.monotonic()
                class Inspection:
                    deadline = start+2
                    done = Event(lambda: h.clock.monotonic() >= start+h.module_delay)
                    def snapshot(self, *, now=None):
                        return dict(status=h.module_status if self.done.is_set() else 'pending',
                            reason='synthetic_module_observation', terminal=self.done.is_set(),
                            duplicate_handle_closed=self.duplicate_closed.is_set())
                inspection = Inspection()
                inspection.duplicate_closed = Event(lambda: inspection.done.is_set() and h.duplicate_closed)
                if h.module_start_error: raise RuntimeError('inspection_start_uncertain')
                return inspection
        child = Child()
        self.children.append(child)
        if self.create_error:
            error = RuntimeError(self.create_error)
            error.owner = child
            raise error
        return child

    def http(self, **kwargs):
        h = self
        h.events.append('http')
        start = h.clock.monotonic()
        class HTTP:
            cancel = kwargs['cancel']
            @property
            def result(self):
                assert self.done.is_set(), 'read before done'
                return deepcopy(h.http_result)
        task = HTTP()
        task.done = Event(lambda: not h.http_stuck and (
            (task.cancel.is_set() and h.clock.monotonic() >=
             getattr(h.children[0], 'closed_at', float('inf'))+h.http_cancel_delay) or
            h.clock.monotonic() >= start+h.http_delay))
        task.args = kwargs
        h.http_tasks.append(task)
        return task

    def run(self, **bindings):
        with ExitStack() as stack:
            stack.enter_context(patch.object(guard, 'time', self.clock))
            stack.enter_context(patch.object(operator_probe, 'time', self.clock))
            stack.enter_context(patch.object(guard, 'utcnow', self.clock.utcnow))
            stack.enter_context(patch.object(operator_store, 'exclusive', self.lock))
            self.guard = guard._Guardian(store=self.store, owned_factory=self.owned,
                query_factory=self.query, http_start=self.http, collect=lambda: None,
                port_check=self.port, **bindings)
            return self.guard.run()


class GuardianTests(unittest.TestCase):
    def test_injected_profile_mismatch_refuses_before_child_or_collection(self):
        result = self.h.run(profile_id='ar4k-iq4xs-correctness-pp1-v2')
        self.assertFalse(result['success'])
        self.assertEqual(result['profile'], 'ar4k-iq4xs-correctness-pp1-v2')
        self.assertEqual(self.h.children, [])
        self.assertEqual(self.h.queries, [])

    def test_injected_policy_and_argv_keep_deadlines_and_cleanup(self):
        injected = Mock(wraps=guard.policy)
        argv = Mock(side_effect=lambda key: guard.fixed_argv(key)+['test-binding'])
        result = self.h.run(policy_module=injected, argv_builder=argv)
        self.assertTrue(result['success'], result)
        self.assertEqual(argv.call_count, 2)
        self.assertTrue(injected.profile_from_manifest.called)
        self.assertTrue(injected.admission_reasons.called)
        self.assertTrue(injected.runtime_decision.called)
        self.assertTrue(injected.recovery_reasons.called)
        args = self.h.http_tasks[0].args
        self.assertEqual(args['lifetime_deadline']-args['startup_deadline'], 120)
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['recovery_samples'], 5)
        self.assertTrue(self.h.children[0].closed)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.h = Harness(self.temp.name)

    def assert_single(self):
        self.assertLessEqual(len(self.h.children), 1)
        self.assertLessEqual(len(self.h.http_tasks), 1)

    def test_exact_fixed_argv_and_redaction(self):
        p = smoke_store.PINS
        expected = [str(p.build/p.executable_name), 'serve', '--host','127.0.0.1',
            '--port','8836','--sessions','1','--max-connections','3','--max-request-bytes',
            '16384','--api-key','private','llm','--model',str(p.first_shard),
            '--served-model-name','gufo-flash-next','--context','4096','--max-tokens','64',
            '--think','off','--speculative','off','--max-pending','1',
            '--max-pending-per-client','1','--request-timeout-ms','60000',
            '--max-output-bytes','1048576']
        self.assertEqual(guard.fixed_argv('private'), expected)

    def test_success_one_lifetime_evidence_and_original_recovery(self):
        result = self.h.run()
        self.assertTrue(result['success'], result)
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['recovery_samples'], 5)
        self.assertGreater(result['runtime_samples'], 0)
        self.assertEqual(result['original_baseline'], json.loads(json.dumps(asdict(self.h.base))))
        self.assertEqual(self.h.events[:2], ['lock:operator', 'lock:smoke'])
        self.assertEqual(self.h.events[-2:], ['unlock:smoke', 'unlock:operator'])
        self.assertTrue((self.h.root/'attempt.json').exists())
        self.assertFalse((self.h.root/'incomplete.json').exists())
        task = self.h.http_tasks[0]
        self.assertEqual(task.args['startup_deadline']-self.h.children[0].resume_at, 480)
        self.assertEqual(task.args['lifetime_deadline']-self.h.children[0].resume_at, 600)
        self.assertNotIn(task.args['api_key'], json.dumps(result))
        for path in self.h.root.rglob('*.json*'):
            self.assertNotIn(task.args['api_key'], path.read_text())
        self.assert_single()
        second = self.h.run()
        self.assertFalse(second['success'])
        self.assert_single()

    def test_static_and_port_refuse_before_collection_or_process(self):
        for attr in ('static_error', 'port_error'):
            with self.subTest(attr=attr):
                setattr(self.h, attr, 'refused_gate')
                result = self.h.run()
                self.assertIn('refused_gate', result['failure'])
                self.assertEqual(self.h.children, [])
                self.assertEqual(self.h.queries, [])
                setattr(self.h, attr, None)

    def test_fresh_stable_background_recovers_without_rewriting_original(self):
        original_bytes = json.dumps(self.h.manifest, sort_keys=True).encode()
        self.h.query_changes = lambda phase, index: dict(available_physical_bytes=50*GIB,
            host_committed_bytes=20*GIB)
        result = self.h.run()
        self.assertTrue(result['success'], result)
        self.assertEqual(result['recovery_samples'], 5)
        self.assertEqual(json.dumps(self.h.manifest, sort_keys=True).encode(), original_bytes)
        saved = json.loads((Path(result['run'])/'baseline.json').read_text())
        self.assertEqual(result['original_baseline'],
                         json.loads(original_bytes)['operator']['original_baseline'])
        self.assertEqual(saved['original'], result['original_baseline'])
        self.assertEqual(saved['current'], result['current_baseline'])
        self.assertEqual(saved['effective'], result['runtime_baseline'])
        self.assertEqual(saved['current_kind'], 'observed_current_baseline')
        self.assertEqual(saved['effective_kind'], 'synthetic_stricter_runtime_limits')
        self.assertEqual(result['runtime_baseline_kind'], saved['effective_kind'])
        self.assertEqual(saved['effective']['committed_max'], 16*GIB)
        self.assertEqual(saved['current']['committed_max'], 20*GIB)
        self.assertEqual(result['sampled_peak_delta_baseline'], 'original_operator_baseline')
        self.assertEqual(result['sampled_peak_deltas']['host_committed_rise_bytes'], 4*GIB)
        recovery = [q.value for q in self.h.queries if q.phase == 'recovery']
        self.assertEqual(len(recovery), 5)
        self.assertGreater(recovery[0].query_start, self.h.children[0].closed_at)
        self.assertGreater(recovery[0].query_start, saved['current']['last_end'])

    def test_fresh_baseline_cannot_cross_original_live_ceiling(self):
        self.h.query_changes = lambda p, i: dict(host_committed_bytes=88*GIB+1)
        result = self.h.run()
        self.assertIn('original_baseline:commit_envelope', result['failure'])
        self.assertEqual(self.h.children, [])

    def test_early_baseline_frame_is_checked_against_original_ceiling(self):
        self.h.query_changes = lambda p, i: dict(host_committed_bytes=
            88*GIB+(1 if p == 'baseline' and i == 0 else 0))
        result = self.h.run()
        self.assertIn('original_baseline:commit_envelope', result['failure'])
        self.assertEqual(self.h.children, [])

    def test_rising_fresh_baseline_is_not_admitted(self):
        self.h.query_changes = lambda p, i: dict(host_committed_bytes=20*GIB+i)
        result = self.h.run()
        self.assertIn('rising_residual', result['failure'])
        self.assertEqual(self.h.children, [])

    def test_original_or_lower_current_ceilings_apply_in_all_later_phases(self):
        for current_commit in (12*GIB, 20*GIB):
            for phase in ('final_precreate', 'final_preresume', 'serving_attempt', 'pending_after_exit', 'recovery'):
                with self.subTest(current_commit=current_commit, phase=phase), tempfile.TemporaryDirectory() as root:
                    h = Harness(root)
                    ceiling = min(16*GIB, current_commit)+72*GIB
                    if phase == 'pending_after_exit':
                        h.child_exit = 1.2
                        h.query_delay = lambda p, i: 1.5 if p == 'serving_attempt' else .1
                    def changes(p, i):
                        breach = p == phase or (phase == 'pending_after_exit' and p == 'serving_attempt')
                        return dict(host_committed_bytes=ceiling+1 if breach else current_commit)
                    h.query_changes = changes
                    result = h.run()
                    if phase == 'recovery':
                        self.assertFalse(result['cleanup_confirmed'])
                        self.assertEqual(result['recovery_samples'], 0)
                    else:
                        self.assertIn('commit_envelope', result['failure'] or '')
                    if phase == 'final_precreate': self.assertEqual(h.children, [])
                    if phase == 'final_preresume': self.assertFalse(h.children[0].resumed)

    def test_fresh_baseline_preserves_absolute_admission_and_runtime_floors(self):
        for phase, changes, reason in (
                ('final_precreate', dict(available_physical_bytes=49*GIB-1), 'prelaunch_physical_floor'),
                ('final_precreate', dict(host_commit_limit_bytes=104*GIB-1), 'commit_floor'),
                ('serving_attempt', dict(available_physical_bytes=24*GIB-1), 'runtime_physical_floor'),
                ('serving_attempt', dict(host_commit_limit_bytes=32*GIB-1), 'commit_floor')):
            with self.subTest(phase=phase, reason=reason), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                h.query_changes = lambda p, i: dict(host_committed_bytes=20*GIB,
                    **(changes if p == phase else {}))
                result = h.run()
                self.assertIn(reason, result['failure'])
                self.assertFalse(result['success'])

    def test_fresh_recovery_requires_five_later_valid_frames(self):
        for invalid in ('four', 'identity', 'duplicate'):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                def changes(p, i):
                    values = dict(host_committed_bytes=20*GIB)
                    if p == 'recovery' and invalid == 'identity':
                        identity = deepcopy(frame(0).snapshot['adapter_identity'])
                        identity['luid'] = '0x00000000_0x000111c2'
                        values.update(adapter_identity=identity, adapter_luid=identity['luid'])
                    return values
                h.query_changes = changes
                if invalid == 'four':
                    h.query_error = lambda p, i: RuntimeError('only_four') if p == 'recovery' and i == 4 else None
                if invalid == 'duplicate':
                    query = h.query
                    def duplicate(collect):
                        value = query(collect)
                        if value.phase == 'recovery':
                            first = next(q for q in h.queries if q.phase == 'recovery')
                            value.value = first.value
                        return value
                    h.query = duplicate
                result = h.run()
                self.assertEqual(len(h.children), 1)
                self.assertTrue(h.children[0].resumed)
                self.assertFalse(result['cleanup_confirmed'])
                self.assertTrue((h.root/'incomplete.json').exists())

    def test_precreate_ages_during_recheck_and_never_creates(self):
        def recheck(current):
            if self.h.guard.phase == 'final_precreate': self.h.clock.sleep(2.1)
        self.h.recheck_hook = recheck
        result = self.h.run()
        self.assertIn('stale_or_future_sample', result['failure'])
        self.assertEqual(self.h.children, [])

    def test_setup_delay_refreshes_final_precreate_before_owned_create(self):
        h = self.h
        begin = h.store.begin_run
        def slow_begin(*args):
            begin(*args)
            h.clock.sleep(.7)
        h.store.begin_run = slow_begin
        h.query_delay = lambda p, i: 1.45 if p == 'final_precreate' else .1
        create_at = []
        owned = h.owned
        def record_create(*args, **kwargs):
            create_at.append(h.clock.monotonic())
            return owned(*args, **kwargs)
        h.owned = record_create
        result = h.run()
        self.assertTrue(result['success'], result)
        final = [q for q in h.queries if q.phase == 'final_precreate']
        self.assertEqual(len(final), 2)
        self.assertEqual(len(create_at), 1)
        self.assertGreater(create_at[0] - final[0].started, 2)
        self.assertLessEqual(create_at[0] - final[1].started, 2)
        self.assertGreaterEqual(final[1].started - final[0].started, 1)
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['recovery_samples'], 5)

    def test_slow_replacement_precreate_refuses_before_owned_create(self):
        self.h.query_delay = lambda p, i: 2.1 if p == 'final_precreate' and i == 1 else .1
        result = self.h.run()
        self.assertFalse(result['success'])
        self.assertEqual(self.h.children, [])
        self.assertEqual(len([q for q in self.h.queries if q.phase == 'final_precreate']), 2)
        self.assertTrue((self.h.root/'attempt.json').exists())
        self.assertTrue((self.h.root/'incomplete.json').exists())
        self.assertFalse(result['cleanup_confirmed'])
        self.assertEqual(result['recovery_samples'], 0)

    def test_replacement_precreate_below_floor_refuses_before_owned_create(self):
        self.h.query_changes = lambda p, i: dict(available_physical_bytes=49*GIB-1) if p == 'final_precreate' and i == 1 else {}
        result = self.h.run()
        self.assertFalse(result['success'])
        self.assertIn('prelaunch_physical_floor', result['failure'])
        self.assertEqual(self.h.children, [])
        self.assertTrue((self.h.root/'attempt.json').exists())
        self.assertFalse((self.h.root/'incomplete.json').exists())
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['recovery_samples'], 5)

    def test_static_change_after_replacement_precreate_refuses_before_owned_create(self):
        def recheck(current):
            if current is not None and len([q for q in self.h.queries if q.phase == 'final_precreate']) == 2:
                raise ValueError('artifact_changed')
        self.h.recheck_hook = recheck
        result = self.h.run()
        self.assertFalse(result['success'])
        self.assertIn('artifact_changed', result['failure'])
        self.assertEqual(self.h.children, [])
        self.assertTrue((self.h.root/'attempt.json').exists())
        self.assertFalse((self.h.root/'incomplete.json').exists())
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['recovery_samples'], 5)

    def test_recheck_ages_replacement_precreate_and_refuses_before_owned_create(self):
        def recheck(current):
            if current is not None and len([q for q in self.h.queries if q.phase == 'final_precreate']) == 2:
                self.h.clock.sleep(2.1)
        self.h.recheck_hook = recheck
        result = self.h.run()
        self.assertFalse(result['success'])
        self.assertIn('stale_or_future_sample', result['failure'])
        self.assertEqual(self.h.children, [])
        self.assertTrue((self.h.root/'attempt.json').exists())
        self.assertFalse((self.h.root/'incomplete.json').exists())
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['recovery_samples'], 5)

    def test_precreate_decision_io_cannot_expire_admission(self):
        decide = guard._Guardian._decision
        def slow(g, phase, frame, decision):
            decide(g, phase, frame, decision)
            if g.attempt_started and g.phase == 'final_precreate': self.h.clock.sleep(2.1)
        with patch.object(guard._Guardian, '_decision', slow):
            result = self.h.run()
        self.assertEqual(self.h.children, [])
        self.assertIn('stale_or_future_sample', result['failure'])

    def test_pending_frame_keeps_raw_pid_and_historical_proof(self):
        for breach in (False, True):
            with self.subTest(breach=breach), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                h.child_exit = 1.2
                h.query_delay = lambda p, i: 1.5 if p == 'serving_attempt' else .1
                h.query_changes = lambda p, i: dict(other_inference_pids=[42],
                    available_physical_bytes=(23 if breach else 52)*GIB) if p == 'serving_attempt' else {}
                result = h.run()
                self.assertTrue(result['collector_terminal'])
                self.assertTrue(result['cleanup_confirmed'], result)
                self.assertEqual(result['runtime_samples'], 0)
                logs = [json.loads(line) for line in (Path(result['run'])/'telemetry.jsonl').read_text().splitlines()]
                pending = [v for v in logs if v['phase'] == 'pending_after_exit']
                self.assertEqual(pending[0]['frame']['snapshot']['other_inference_pids'], [42])
                decisions = [json.loads(line) for line in (Path(result['run'])/'decisions.jsonl').read_text().splitlines()]
                d = next(v['decision'] for v in decisions if v['phase'] == 'pending_after_exit')
                self.assertEqual(d['owned_inventory_proof']['status'], 'historical_query_start')
                self.assertEqual('runtime_physical_floor' in d['reasons'], breach)

    def test_pending_alien_and_missing_start_proof_never_excluded(self):
        f = frame(12, other_inference_pids=[42,7])
        identity = dict(pid=42, creation_time_100ns=1234, executable='fake')
        proof = dict(status='verified', identity=identity, verified_monotonic=11.9)
        scoped = guard._historical_frame(f, proof, identity, 12)
        self.assertEqual(scoped.snapshot['other_inference_pids'], [7])
        self.assertEqual(guard._historical_frame(f, None, identity, 12).snapshot['other_inference_pids'], [42,7])
        with self.assertRaisesRegex(ValueError, 'historical_ownership_unverified'):
            guard._historical_frame(f, dict(proof, verified_monotonic=13), identity, 12)

    def test_last_actual_sample_age_has_independent_watchdog(self):
        self.h.http_delay = 100
        with patch.object(guard, 'QUERY_INTERVAL', 6):
            result = self.h.run()
        self.assertIn('stale_or_future_sample', result['failure'])
        child = self.h.children[0]
        self.assertLess(child.closed_at-child.resume_at, 5.1)

    def test_breach_is_in_sampled_lower_bound_peak(self):
        self.h.query_changes = lambda p, i: dict(adapter_shared_bytes=self.h.base.gpu_max[1]+21*GIB) if p == 'serving_attempt' else {}
        result = self.h.run()
        self.assertEqual(result['sampled_peak_deltas'].get('adapter_shared_bytes'), 21*GIB)
        self.assertEqual(result['runtime_samples'], 1)

    def test_evidence_failure_never_clears_latch_or_resumes(self):
        write = operator_store.atomic_json
        for name in ('owned.json', 'result.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                def fail(path, value):
                    if Path(path).name == name: raise OSError('synthetic_disk_failure')
                    return write(path, value)
                with patch.object(operator_store, 'atomic_json', fail): result = h.run()
                self.assertFalse(result['cleanup_confirmed'])
                self.assertTrue((h.root/'incomplete.json').exists())
                self.assertTrue(h.children[0].closed)
                if name == 'owned.json': self.assertFalse(h.children[0].resumed)

    def test_unstarted_query_constructor_is_tracked(self):
        self.h.query = lambda collect: (_ for _ in ()).throw(RuntimeError('query_start_failed'))
        result = self.h.run()
        self.assertFalse(result['collector_terminal'])
        self.assertFalse(result['cleanup_confirmed'])
        self.assertTrue((self.h.root/'incomplete.json').exists())

    def test_worker_start_exception_is_not_terminal_proof(self):
        for kind in ('http', 'inspection'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                if kind == 'http':
                    start = h.http
                    def fail(**kwargs):
                        start(**kwargs)
                        raise RuntimeError('http_start_uncertain')
                    h.http = fail
                else:
                    h.module_start_error = True
                result = h.run()
                self.assertFalse(result['cleanup_confirmed'])
                self.assertFalse(result[kind+'_terminal'])
                self.assertTrue(h.children[0].closed)
                self.assertTrue((h.root/'incomplete.json').exists())

    def test_late_collector_cannot_be_reclassified_clean_after_worker_wait(self):
        self.h.query_delay = lambda p, i: 3 if p == 'serving_attempt' else .1
        self.h.http_delay = 1000
        self.h.http_cancel_delay = 9
        result = self.h.run()
        self.assertFalse(result['cleanup_confirmed'])
        self.assertTrue((self.h.root/'incomplete.json').exists())
        logs = [json.loads(line) for line in (Path(result['run'])/'telemetry.jsonl').read_text().splitlines()]
        self.assertTrue(any(v['phase'] == 'pending_after_exit' for v in logs))

    def test_overdue_query_completing_during_owned_close_keeps_latch(self):
        self.h.query_delay = lambda p, i: 3 if p == 'serving_attempt' else .1
        self.h.http_delay = 1000
        self.h.close_delay = 1.5
        result = self.h.run()
        self.assertIn('active_query_timeout', result['failure'])
        self.assertTrue(result['collector_terminal'])
        self.assertFalse(result['collector_cleanup_confirmed'])
        self.assertFalse(result['cleanup_confirmed'])
        self.assertTrue((self.h.root/'incomplete.json').exists())
        query = next(q for q in self.h.queries if q.phase == 'serving_attempt')
        self.assertLess(self.h.children[0].closed_at, query.ended)
        self.assertLess(query.ended, self.h.children[0].closed_at+self.h.close_delay)
        logs = [json.loads(line) for line in (Path(result['run'])/'telemetry.jsonl').read_text().splitlines()]
        self.assertTrue(any(v['phase'] == 'pending_after_exit' for v in logs))

    def test_on_time_query_first_observed_after_close_remains_clean(self):
        self.h.query_delay = lambda p, i: 1.5 if p == 'serving_attempt' else .1
        self.h.http_delay = 1.2
        self.h.http_result = dict(success=False, error='synthetic_http_failure', post_attempted=True)
        self.h.close_delay = 2.5
        result = self.h.run()
        self.assertTrue(result['collector_terminal'])
        self.assertTrue(result['collector_cleanup_confirmed'])
        self.assertTrue(result['cleanup_confirmed'], result)
        self.assertFalse((self.h.root/'incomplete.json').exists())
        query = next(q for q in self.h.queries if q.phase == 'serving_attempt')
        self.assertLess(query.ended-query.started, 2)
        self.assertGreater(self.h.children[0].closed_at+self.h.close_delay-query.started, 2)
        logs = [json.loads(line) for line in (Path(result['run'])/'telemetry.jsonl').read_text().splitlines()]
        self.assertTrue(any(v['phase'] == 'pending_after_exit' for v in logs))

    def test_overdue_terminal_query_first_encountered_in_drain_keeps_latch(self):
        self.h.query_delay = lambda p, i: 3 if p == 'serving_attempt' else .1
        self.h.http_delay = 1.2
        self.h.http_result = dict(success=False, error='synthetic_http_failure', post_attempted=True)
        self.h.close_delay = 3.1
        result = self.h.run()
        self.assertIn('query_timeout', result['failure'])
        self.assertTrue(result['collector_terminal'])
        self.assertFalse(result['collector_cleanup_confirmed'])
        self.assertFalse(result['cleanup_confirmed'])
        self.assertTrue((self.h.root/'incomplete.json').exists())
        logs = [json.loads(line) for line in (Path(result['run'])/'telemetry.jsonl').read_text().splitlines()]
        self.assertTrue(any(v['phase'] == 'pending_after_exit' for v in logs))

    def test_rising_residual_below_tolerance_still_refuses_cleanup(self):
        self.h.query_changes = lambda p, i: dict(host_committed_bytes=16*GIB+i) if p == 'recovery' else {}
        result = self.h.run()
        self.assertFalse(result['cleanup_confirmed'])
        self.assertIn('recovery_unconfirmed', result['failure'])

    def test_http_worker_owns_exact_startup_and_post_deadlines(self):
        clock = Clock()
        class Cancel:
            def is_set(self): return False
            def wait(self, delay): clock.sleep(delay)
        class Thread:
            def __init__(self, *, target, **kwargs): self.target = target
            def start(self): self.target()
        calls = []
        def exchange(method, path, body, key, deadline, cancel):
            calls.append((method, path, deadline))
            now = clock.monotonic()
            if path == '/ready':
                return 200, {}, b'{"status":"ready","model":"gufo-flash-next"}', now, now, []
            if path == '/v1/models':
                return 200, {}, b'{"data":[{"id":"gufo-flash-next"}]}', now, now, []
            clock.sleep(60.01)
            raise smoke_http.SmokeError('deadline_exceeded')
        with patch.object(smoke_http, 'time', clock), \
             patch.object(smoke_http, 'threading', SimpleNamespace(Thread=Thread, Event=threading.Event)), \
             patch.object(smoke_http, '_exchange', exchange):
            task = smoke_http.start_smoke(api_key='offline-key', startup_deadline=580,
                lifetime_deadline=700, cancel=Cancel())
        self.assertTrue(task.done.is_set())
        self.assertEqual([c[0] for c in calls], ['GET','GET','POST'])
        self.assertEqual([c[2] for c in calls], [580,580,160])
        self.assertTrue(task.result['post_attempted'])
        self.assertFalse(task.result['success'])
        clock.value = 100
        calls.clear()
        def unavailable(method, path, body, key, deadline, cancel):
            calls.append((method,path,deadline))
            return 503, {}, b'{"error":{"code":"not_ready"}}', clock.value, clock.value, []
        with patch.object(smoke_http, 'time', clock), \
             patch.object(smoke_http, 'threading', SimpleNamespace(Thread=Thread, Event=threading.Event)), \
             patch.object(smoke_http, '_exchange', unavailable):
            task = smoke_http.start_smoke(api_key='offline-key', startup_deadline=580,
                lifetime_deadline=700, cancel=Cancel())
        self.assertFalse(task.result['post_attempted'])
        self.assertEqual(len(calls), 240)
        self.assertEqual(clock.value, 580)
        self.assertTrue(all(c[2] == 580 for c in calls))

    def test_recovery_deadline_begins_at_owned_exit(self):
        self.h.child_exit = .2
        self.h.http_delay = 1000
        self.h.http_cancel_delay = 9
        def changes(p, i):
            if p == 'recovery' and self.h.clock.monotonic() < self.h.children[0].closed_at+57:
                return dict(available_physical_bytes=49*GIB)
            return {}
        self.h.query_changes = changes
        result = self.h.run()
        self.assertFalse(result['cleanup_confirmed'])
        self.assertLessEqual(self.h.clock.monotonic()-self.h.children[0].closed_at, 60.1)

    def test_suspended_failures_close_without_resume(self):
        for case in ('assignment', 'identity', 'stale', 'stamp'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                if case == 'assignment': h.create_error = 'job_assignment'
                if case == 'identity': h.identity_error = True
                if case == 'stale':
                    h.recheck_hook = lambda current: h.clock.sleep(2.1) if h.guard.phase == 'final_preresume' else None
                if case == 'stamp':
                    def changed(current):
                        if h.guard.phase == 'final_preresume': raise ValueError('artifact_changed')
                    h.recheck_hook = changed
                result = h.run()
                self.assertFalse(result['success'])
                self.assertFalse(h.children[0].resumed)
                self.assertTrue(h.children[0].closed)
                self.assertEqual(h.http_tasks, [])

    def test_http_failures_are_consumed_without_retry(self):
        for error in ('startup_timeout', 'wrong_ready_model', 'malformed_sse',
                      'unsupported_sampler', 'prompt_token_limit', 'output_token_limit', 'post_failed'):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                h.http_result = dict(success=False, error=error, post_attempted=True)
                result = h.run()
                self.assertIn(error, result['failure'])
                self.assertFalse(result['success'])
                self.assertTrue(result['cleanup_confirmed'])
                self.assertEqual(len(h.children), 1)
                self.assertEqual(len(h.http_tasks), 1)
                self.assertTrue(result['http']['post_attempted'])

    def test_pressure_stops_before_waiting_on_blocked_http(self):
        self.h.http_stuck = True
        self.h.query_changes = lambda phase, index: dict(available_physical_bytes=23*GIB) if phase == 'serving_attempt' else {}
        result = self.h.run()
        child = self.h.children[0]
        self.assertLess(child.closed_at-child.resume_at, 3)
        self.assertIn('runtime_physical_floor', result['failure'])
        self.assertFalse(result['http_terminal'])
        self.assertFalse(result['cleanup_confirmed'])
        self.assertTrue((self.h.root/'incomplete.json').exists())

    def test_guardian_lifetime_is_independent_of_http(self):
        self.h.http_delay = 1000
        result = self.h.run()
        self.assertIn('lifetime_timeout', result['failure'])
        child = self.h.children[0]
        self.assertLessEqual(child.closed_at-child.resume_at, 600.051)
        self.assertTrue(result['evidence_write_confirmed'])
        self.assertTrue(result['cleanup_confirmed'])
        self.assert_single()

    def test_stuck_collector_in_each_phase_is_retained(self):
        for phase in ('baseline', 'final_precreate', 'final_preresume', 'serving_attempt', 'recovery'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                h.query_delay = lambda p, i: 1000 if p == phase else 0.1
                result = h.run()
                self.assertIn('active_query_timeout', result['failure'])
                self.assertFalse(result['collector_terminal'])
                self.assertFalse(result['cleanup_confirmed'])
                self.assertTrue((h.root/'incomplete.json').exists())
                if h.children: self.assertTrue(h.children[0].closed)
                if phase in ('baseline', 'final_precreate'):
                    self.assertFalse((h.root/'attempt.json').exists())

    def test_inventory_duplicate_alien_and_owner_exit(self):
        for pids in ([42,42], [42,7]):
            with self.subTest(pids=pids), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                h.query_changes = lambda phase, index: dict(other_inference_pids=pids) if phase == 'serving_attempt' else {}
                result = h.run()
                self.assertIn('other_inference_active', result['failure'])
                self.assertTrue(h.children[0].closed)
        self.h.child_exit = 0.2
        result = self.h.run()
        self.assertIn('child_exited_before_completion', result['failure'])
        self.assert_single()

    def test_modules_unknown_wrong_path_timeout_and_unclosed_duplicate(self):
        for status, delay, closed in [('failed', .1, True), ('unknown', .1, True),
                                      ('verified', 1000, True), ('verified', .1, False)]:
            with self.subTest(status=status, delay=delay, closed=closed), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                h.module_status, h.module_delay, h.duplicate_closed = status, delay, closed
                result = h.run()
                self.assertFalse(result['success'])
                self.assertTrue(h.children[0].closed)
                if delay > 2 or not closed: self.assertFalse(result['cleanup_confirmed'])

    def test_exit_timeout_and_insufficient_recovery_keep_latch(self):
        for mode in ('exit', 'four', 'residual', 'live_pid'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                if mode == 'exit': h.close_error = True
                if mode == 'four': h.query_error = lambda p, i: RuntimeError('telemetry_error') if p == 'recovery' and i == 4 else None
                if mode == 'residual': h.query_changes = lambda p, i: dict(available_physical_bytes=49*GIB) if p == 'recovery' else {}
                if mode == 'live_pid': h.query_changes = lambda p, i: dict(other_inference_pids=[42]) if p == 'recovery' else {}
                result = h.run()
                self.assertFalse(result['cleanup_confirmed'])
                self.assertTrue((h.root/'incomplete.json').exists())

    def test_print_status_and_invalid_options_never_launch(self):
        with patch.object(guard, 'OwnedProcess') as owned, \
             patch.object(guard.smoke_store, 'EVIDENCE', self.h.root), \
             patch.object(guard.smoke_store, 'verify_static', side_effect=ValueError('unqualified')), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            guard.main(['status'])
            guard.main(['print-only'])
            with self.assertRaises(SystemExit): guard.main(['run', '--model', 'other'])
            owned.assert_not_called()
        self.assertEqual(list(self.h.root.iterdir()), [])


if __name__ == '__main__': unittest.main()
