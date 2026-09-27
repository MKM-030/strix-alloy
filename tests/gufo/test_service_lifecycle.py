"""Offline persistent supervision through the single existing guardian."""
from copy import deepcopy
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
import json
import inspect
import importlib
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_smoke_guard import Harness
from gufo_control import smoke_guard as guard
from gufo_control import operator_store, operator_probe
from gufo_control import service_store, smoke_store, service_lifecycle
from gufo_control.benchmark_runtime import BoundPolicy
from gufo_control.operator_policy import GIB
from test_service_store import InstalledFixture


@contextmanager
def installed_harness(*, accepted=True):
    with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
        fixture = InstalledFixture(root)
        h = Harness(fixture.f.pins.evidence)
        fixture.f.base = h.base
        for path in (fixture.f.failed, fixture.f.gdn, fixture.f.iq):
            record = operator_store.read_json(path)
            record['original_baseline'] = asdict(h.base)
            operator_store.atomic_json(path, record)
        sequence = fixture.f.operators/'sequence.json'
        record = operator_store.read_json(sequence)
        record['baseline'] = asdict(h.base)
        operator_store.atomic_json(sequence, record)
        fixture.f.pins = replace(fixture.f.pins,
            failed_result_sha256=operator_store.artifact_record(fixture.f.failed)['sha256'],
            gdn_result_sha256=operator_store.artifact_record(fixture.f.gdn)['sha256'],
            iq_result_sha256=operator_store.artifact_record(fixture.f.iq)['sha256'])
        fixture.value = service_store.expected_profile(fixture.f.pins)
        operator_store.atomic_json(fixture.profile, fixture.value)
        operator_store.atomic_json(fixture.anchor, service_store.expected_anchor(fixture.value))
        stack.enter_context(patch.object(service_store, 'PINS', fixture.f.pins))
        stack.enter_context(patch.object(service_store, 'ANCHOR_PATH', fixture.anchor))
        stack.enter_context(patch.object(service_store, 'source_identity', return_value=None))
        stack.enter_context(patch.object(service_store.runtime_package, 'verify_runtime',
            return_value={'policy_sha256': service_store.RUNTIME_POLICY_SHA256}))
        stack.enter_context(patch.object(smoke_store, 'validate_ar4k_model',
            side_effect=lambda first: smoke_store.ValidatedModel(first, fixture.f.pins.model_revision)))
        if accepted: fixture.accepted()
        h.store = service_store.InstalledStore(fixture.profile)
        h.base = fixture.f.base
        life = Lifecycle(h, duration=1200)
        bindings = dict(lifecycle=life, profile_id=service_store.PROFILE_ID,
            policy_module=BoundPolicy(fixture.f.pins),
            argv_builder=lambda key: [str(fixture.f.exe), '--api-key', key])
        yield h, life, bindings, fixture


class Lifecycle:
    def __init__(self, harness, *, duration=30, stop_after=8):
        self.h = harness
        self.duration, self.stop_after = duration, stop_after
        self.started, self.ready, self.results = [], [], []

    def deadline(self, resumed_at):
        return resumed_at+self.duration

    def on_started(self, run_dir, child_identity, api_key):
        assert (run_dir/'owned.json').exists()
        assert not self.h.children[0].resumed
        self.started.append(deepcopy(child_identity))

    def on_ready(self, snapshot):
        assert self.h.guard.module_result['status'] == 'verified'
        assert not self.h.children[0].closed
        self.ready.append(deepcopy(snapshot))

    def poll(self, now):
        if now-self.h.guard.resumed_at >= self.stop_after:
            return 'stop'

    def on_result(self, result):
        assert not self.h.children or self.h.children[0].closed
        self.results.append(deepcopy(result))


class ServiceLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.h = Harness(self.temp.name)
        self.lifecycle = Lifecycle(self.h)

    def test_service_keeps_sampling_after_one_ready_until_stop(self):
        self.assertIn('lifecycle', inspect.signature(guard._Guardian).parameters)
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertTrue(result['success'], result)
        self.assertEqual(len(self.lifecycle.started), 1)
        self.assertEqual(len(self.lifecycle.ready), 1)
        self.assertEqual(len(self.lifecycle.results), 1)
        self.assertGreaterEqual(result['runtime_samples'], 7)
        self.assertGreater(result['runtime_samples'], self.lifecycle.ready[0]['runtime_samples'])
        self.assertGreaterEqual(self.h.children[0].closed_at-self.h.children[0].resume_at, 8)
        self.assertEqual(len(self.h.http_tasks), 1)
        self.assertEqual(result['recovery_samples'], 5)

    def test_deadlines_invalid_or_expired_refuse_before_resume(self):
        for value in (0, -1, True, math.inf, -math.inf, math.nan, 100):
            with self.subTest(deadline=value), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                life = Lifecycle(h)
                life.deadline = lambda now: value
                result = h.run(lifecycle=life)
                self.assertFalse(h.children[0].resumed)
                self.assertTrue(h.children[0].closed)
                self.assertIn('service_deadline_invalid', result['failure'])

    def test_deadline_callback_io_precedes_last_freshness_admission(self):
        def deadline(now):
            self.h.clock.sleep(2.1)
            return now+30
        self.lifecycle.deadline = deadline
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertFalse(self.h.children[0].resumed)
        self.assertIn('stale_or_future_sample', result['failure'])

    def test_finite_service_lease_expiry_is_failure(self):
        self.lifecycle.duration, self.lifecycle.stop_after = 5, 100
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertIn('lifetime_timeout', result['failure'])
        self.assertFalse(result['success'])
        self.assertTrue(result['cleanup_confirmed'])

    def test_deadline_crossed_during_control_poll_cannot_become_successful_stop(self):
        def stop(now):
            if self.lifecycle.ready:
                self.h.clock.sleep(40)
                return 'stop'
        self.lifecycle.poll = stop
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertFalse(result['success'])
        self.assertIn('lifetime_timeout', result['failure'])

    def test_telemetry_aging_during_control_poll_cannot_become_successful_stop(self):
        def stop(now):
            if self.lifecycle.ready:
                self.h.clock.sleep(5.1)
                return 'stop'
        self.lifecycle.poll = stop
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertFalse(result['success'])
        self.assertIn('stale_or_future_sample', result['failure'])

    def test_deadline_expiring_in_final_admission_refuses_resume(self):
        self.lifecycle.duration = .01
        admission = guard.policy.admission_reasons
        def delayed(*args, **kwargs):
            result = admission(*args, **kwargs)
            if self.h.guard.lifetime_deadline is not None: self.h.clock.sleep(.02)
            return result
        with patch.object(guard.policy, 'admission_reasons', delayed):
            result = self.h.run(lifecycle=self.lifecycle)
        self.assertFalse(self.h.children[0].resumed)
        self.assertIn('service_deadline_invalid', result['failure'])

    def test_on_started_io_is_followed_by_replacement_fresh_admission(self):
        started = self.lifecycle.on_started
        def slow(*args):
            started(*args)
            self.h.clock.sleep(20)
        self.lifecycle.on_started = slow
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertTrue(result['success'], result['failure'])
        self.assertEqual(len(self.lifecycle.ready), 1)

    def test_ready_and_terminal_notifications_cannot_mutate_guardian_identity(self):
        ready, terminal = self.lifecycle.on_ready, self.lifecycle.on_result
        def changed(snapshot):
            ready(snapshot)
            snapshot['identity']['pid'] = -1
        def ended(result):
            terminal(result)
            result['identity']['pid'] = -2
        self.lifecycle.on_ready, self.lifecycle.on_result = changed, ended
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertTrue(result['success'], result['failure'])
        self.assertEqual(result['identity']['pid'], 42)

    def test_callbacks_fail_into_owned_cleanup(self):
        for callback in ('on_started', 'on_ready', 'on_result'):
            with self.subTest(callback=callback), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                life = Lifecycle(h)
                def fail(*args): raise OSError('callback_failed')
                setattr(life, callback, fail)
                result = h.run(lifecycle=life)
                self.assertFalse(result['success'])
                self.assertIn('callback_failed', result['failure'])
                self.assertTrue(h.children[0].closed)
                if callback == 'on_started': self.assertFalse(h.children[0].resumed)

    def test_stop_or_disconnect_before_readiness_never_hands_off(self):
        for request in ('stop', 'handoff_failed', 'invalid'):
            with self.subTest(request=request), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                life = Lifecycle(h)
                life.poll = lambda now: request
                result = h.run(lifecycle=life)
                self.assertFalse(result['success'])
                self.assertFalse(result['service_ready'])
                self.assertEqual(life.ready, [])
                self.assertTrue(result['cleanup_confirmed'])

    def test_pressure_after_ready_closes_promptly(self):
        self.h.query_changes = lambda p, i: (dict(available_physical_bytes=23*GIB)
            if p == 'serving_attempt' and i >= 5 else {})
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertEqual(len(self.lifecycle.ready), 1)
        self.assertIn('runtime_physical_floor', result['failure'])
        self.assertLess(self.h.children[0].closed_at-self.h.children[0].resume_at, 8)

    def test_pending_query_stop_retains_raw_evidence_and_start_proof(self):
        self.lifecycle.stop_after = 4.2
        self.h.query_delay = lambda p, i: 1.5 if p == 'serving_attempt' and i >= 3 else .1
        self.h.query_changes = lambda p, i: dict(other_inference_pids=[42]) if p == 'serving_attempt' else {}
        result = self.h.run(lifecycle=self.lifecycle)
        pending = [e for e in self.h.guard.entries if getattr(e, 'pending_after_exit', False)]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].proof['identity'], self.h.children[0].identity)
        self.assertEqual(pending[0].frame.snapshot['other_inference_pids'], [42])
        self.assertTrue(result['cleanup_confirmed'], result)
        self.assertIn('pending_after_exit', (Path(result['run'])/'telemetry.jsonl').read_text())

    def test_telemetry_fsync_failure_keeps_entries_and_latch(self):
        real_fsync = guard.os.fsync
        def fail_telemetry(fd):
            if self.h.guard.phase == 'serving_attempt' and self.h.guard.runtime_samples >= 1:
                raise OSError('telemetry_durability_failed')
            return real_fsync(fd)
        with patch.object(guard.os, 'fsync', fail_telemetry):
            result = self.h.run(lifecycle=self.lifecycle)
        self.assertIn('telemetry_durability_failed', result['failure'])
        self.assertFalse(result['evidence_write_confirmed'])
        self.assertFalse(result['cleanup_confirmed'])
        self.assertTrue((self.h.root/'incomplete.json').exists())
        self.assertTrue(any(e.phase == 'serving_attempt' for e in self.h.guard.entries))

    def test_terminal_callback_observes_result_write_failure(self):
        write = operator_store.atomic_json
        def fail(path, value):
            if Path(path).name == 'result.json': raise OSError('result_write_failed')
            return write(path, value)
        with patch.object(operator_store, 'atomic_json', fail):
            result = self.h.run(lifecycle=self.lifecycle)
        self.assertFalse(result['success'])
        self.assertFalse(self.lifecycle.results[0]['success'])
        self.assertIn('result_write_failed', self.lifecycle.results[0]['failure'])

    def test_retention_only_summarizes_terminal_measured_durable_entries(self):
        self.lifecycle.stop_after = 40
        self.lifecycle.duration = 60
        result = self.h.run(lifecycle=self.lifecycle)
        self.assertLessEqual(len(self.h.guard.entries), 6)
        self.assertEqual(result['collector_queries'], len(self.h.queries))
        self.assertEqual(result['collector_completed_queries'], len(self.h.queries))
        self.assertTrue(all(e.logged and e.measured and e.done.is_set() for e in self.h.guard.entries))
        self.assertTrue(result['cleanup_confirmed'])

    def test_qualified_deadline_rejects_absent_acceptance(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.service_lifecycle'))
        lifecycle = importlib.import_module('gufo_control.service_lifecycle')
        with self.assertRaisesRegex(ValueError, 'persistent_service_unqualified'):
            lifecycle._qualified_deadline({}, 100)

    def test_installed_prepared_run_then_begun_markers_and_qualified_lease(self):
        with installed_harness() as (h, life, bindings, fixture):
            recheck = h.store.recheck_static
            checks = []
            def checked(manifest, **kwargs):
                checks.append((h.guard.attempt_started, dict(kwargs)))
                return recheck(manifest, **kwargs)
            h.store.recheck_static = checked
            life.deadline = lambda now: service_lifecycle._qualified_deadline(h.guard.manifest, now)
            result = h.run(**bindings)
            self.assertTrue(result['success'], result)
            preparing = [kw for begun, kw in checks if not begun]
            self.assertEqual(len(preparing), 3)  # Two guardian rechecks and begin_run.
            self.assertTrue(all(kw == {'prepared_run': h.guard.run_dir} for kw in preparing))
            self.assertTrue(all(kw == {'current_run': h.guard.run_dir} for begun, kw in checks if begun))
            self.assertEqual(h.guard.lifetime_deadline-h.guard.resumed_at, 1200)
            self.assertFalse((h.root/'incomplete.json').exists())
            self.assertTrue((h.root/'current.json').exists())
            self.assertFalse((h.root/'attempt.json').exists())

    def test_installed_missing_acceptance_refuses_before_activity(self):
        with installed_harness(accepted=False) as (h, life, bindings, fixture):
            result = h.run(**bindings)
            self.assertFalse(result['success'])
            self.assertIn('persistent_service_unqualified', result['failure'])
            self.assertEqual(h.children, [])
            self.assertEqual(h.queries, [])
            self.assertEqual(life.started, [])

    def test_installed_exact_lease_cannot_use_finite_smoke_600_seconds(self):
        with installed_harness() as (h, life, bindings, fixture):
            life.duration = 600
            result = h.run(**bindings)
            self.assertIn('service_deadline_qualification_mismatch', result['failure'])
            self.assertFalse(h.children[0].resumed)
            self.assertTrue(h.children[0].closed)

    def test_qualified_deadline_binds_entire_workload_anchor(self):
        with installed_harness() as (h, life, bindings, fixture):
            manifest = h.store.verify_static()
            self.assertEqual(service_lifecycle._qualified_deadline(manifest, 100), 1300)
            for field, value in (('lifetime_seconds', 600), ('max_generation_posts', 3),
                                 ('lifetime_seconds', True), ('lifetime_seconds', 0)):
                changed = deepcopy(manifest)
                changed['qualification']['installed_workload'][field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'persistent_service_unqualified'):
                    service_lifecycle._qualified_deadline(changed, 100)

    def test_installed_finish_failure_never_replaces_first_terminal_file(self):
        with installed_harness() as (h, life, bindings, fixture):
            write = operator_store.atomic_json
            captured = []
            def fail(path, value):
                if Path(path) == h.root/'current.json' and 'result_sha256' in value:
                    captured.append((h.guard.run_dir/'result.json').read_bytes())
                    raise OSError('finish_after_immutable_result')
                return write(path, value)
            with patch.object(operator_store, 'atomic_json', fail):
                result = h.run(**bindings)
            self.assertEqual(len(captured), 1)
            self.assertEqual((h.guard.run_dir/'result.json').read_bytes(), captured[0])
            self.assertTrue(json.loads(captured[0])['success'])
            self.assertFalse(result['success'])
            self.assertFalse(result['evidence_write_confirmed'])
            self.assertIn('finish_after_immutable_result', result['failure'])
            self.assertTrue((h.root/'incomplete.json').exists())
            failures = list(h.guard.run_dir.glob('result-failure-*.json'))
            self.assertEqual(len(failures), 1)
            self.assertEqual(json.loads(failures[0].read_text()), result)
            self.assertFalse(life.results[0]['success'])

    def test_service_staleness_and_identity_remain_independent_after_ready(self):
        for failure in ('stale', 'identity', 'telemetry', 'exit'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                h = Harness(root)
                life = Lifecycle(h, stop_after=30, duration=40)
                poll = life.poll
                def changed(now):
                    if life.ready:
                        if failure == 'stale': h.clock.sleep(5.1)
                        elif failure == 'identity': h.identity_error = True
                        elif failure == 'exit': h.child_exit = 0
                    return poll(now)
                life.poll = changed
                if failure == 'telemetry':
                    h.query_changes = lambda p, i: dict(telemetry_ok=False) if p == 'serving_attempt' and i >= 5 else {}
                result = h.run(lifecycle=life)
                self.assertEqual(len(life.ready), 1)
                self.assertFalse(result['success'])
                self.assertTrue(h.children[0].closed)

    def test_failures_after_pruning_keep_cleanup_unconfirmed(self):
        for failure in ('late', 'constructor', 'module_handle', 'http_hang', 'telemetry_log'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                h = Harness(root, query_history_limit=8)
                life = Lifecycle(h, stop_after=40, duration=60)
                if failure == 'late':
                    h.query_delay = lambda p, i: 3 if p == 'serving_attempt' and i >= 15 else .1
                    h.close_delay = 2
                elif failure == 'constructor':
                    query = h.query
                    def broken(collect):
                        if h.query_counts['serving_attempt'] >= 15: raise RuntimeError('constructor_uncertain')
                        return query(collect)
                    h.query = broken
                elif failure == 'module_handle': h.duplicate_closed = False
                elif failure == 'http_hang': h.http_stuck = True
                log = operator_probe.log_frame
                def logged(path, frame, phase):
                    if failure == 'telemetry_log' and phase == 'serving_attempt' and h.guard.runtime_samples >= 15:
                        raise OSError('telemetry_log_failed')
                    return log(path, frame, phase)
                with patch.object(operator_probe, 'log_frame', logged):
                    result = h.run(lifecycle=life)
                self.assertGreater(h.guard.summarized_queries, 0)
                self.assertFalse(result['success'])
                self.assertFalse(result['cleanup_confirmed'])
                self.assertTrue((h.root/'incomplete.json').exists())
                self.assertTrue(h.children[0].closed)
                if failure == 'late':
                    self.assertTrue(result['collector_terminal'])
                    self.assertFalse(result['collector_cleanup_confirmed'])
                    self.assertTrue(any(e.pending_after_exit for e in h.guard.entries))
                if failure == 'constructor': self.assertFalse(result['collector_terminal'])

    def test_100000_samples_have_bounded_retention_durable_counts_and_fresh_status(self):
        h = Harness(self.temp.name, query_history_limit=8)
        life = Lifecycle(h, duration=300000, stop_after=300000)
        max_entries = 0
        fresh = []
        def stop(now):
            nonlocal max_entries
            max_entries = max(max_entries, len(h.guard.entries))
            if h.guard.runtime_samples >= 100000:
                last = next(e.frame for e in reversed(h.guard.entries) if e.frame is not None)
                fresh.append(now-last.snapshot['captured_monotonic'])
                return 'stop'
        life.poll = stop
        with patch.object(guard, 'POLL_SECONDS', 1):
            result = h.run(lifecycle=life)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['runtime_samples'], 100000)
        self.assertLessEqual(max_entries, 2)
        self.assertLessEqual(len(h.guard.entries), 6)
        self.assertEqual(len(h.queries), 8)
        self.assertEqual(result['collector_queries'], sum(h.query_counts.values()))
        self.assertEqual(result['collector_queries'], 100019)
        self.assertEqual(result['collector_queries'], result['collector_completed_queries'])
        self.assertEqual(result['recovery_samples'], 5)
        self.assertLessEqual(fresh[0], 1)
        self.assertEqual(len(life.ready), 1)
        self.assertEqual(len(h.http_tasks), 1)
        phases = {}
        with (Path(result['run'])/'telemetry.jsonl').open() as stream:
            for line in stream:
                phase = json.loads(line)['phase']
                phases[phase] = phases.get(phase, 0)+1
        self.assertEqual(phases['serving_attempt'], 100000)
        self.assertEqual(sum(phases.values()), result['collector_queries'])


if __name__ == '__main__':
    unittest.main()
