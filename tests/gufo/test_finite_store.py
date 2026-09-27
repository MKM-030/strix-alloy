from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import finite_profile as fp, finite_store as fs
from gufo_control import operator_store, service_store, smoke_store
from gufo_control.operator_policy import baseline
from test_operator_policy import frame, series
from test_finite_profile import candidate, qualified

REAL_REVIEW = fs._review


def coverage(run, index):
    count = 66 if index == 1 else 6
    return dict(run_id=run.name, lifecycle=index,
        returned_slots=[f'post-{n:03d}' for n in range(2, count+1)],
        ready_count=1, models_count=1, post_count=count, workers_terminal=True,
        phase_boundaries=[],
        idle_windows=[[n, 50.0+30*i, 80.0+30*i]
                      for i, n in enumerate((6, 18, 30, 48))] if index == 1 else [],
        wave_proofs=[[n, 70.0, 71.0, 72.0] for n in (45, 48)] if index == 1 else [],
        pending_semantic_review=index == 1, failure=None, complete=True)


class FiniteStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.evidence = self.root/'gufo-service-lifecycle-v1-runs'; self.evidence.mkdir()
        self.pins = replace(fp.PINS, evidence=self.evidence,
            operator_evidence=self.root/'operator-runs',
            qualification=self.root/'finite-review.json')
        self.anchor = self.root/'anchor.json'
        self.addCleanup(patch.stopall)
        patch.object(fp, 'PINS', self.pins).start()
        patch.object(fs, 'PINS', self.pins).start()
        patch.object(fs, 'ANCHOR_PATH', self.anchor).start()
        self.base = baseline(series())
        self.value = candidate()
        self.value['finite_profile'] = fp.finite_binding(self.pins)
        self.value['operator'] = dict(original_baseline=asdict(self.base), state={})
        self.manifest = qualified(self.value)
        patch.object(fs, '_candidate', return_value=deepcopy(self.value)).start()
        patch.object(fs, '_recheck_candidate').start()
        patch.object(fs, '_review', return_value=(
            self.manifest['qualification'], self.manifest['qualification_stamp'],
            self.manifest['qualification_anchor'], self.manifest['qualification_anchor_stamp'])).start()
        self.clock = patch.object(fs.time, 'monotonic', return_value=14.0).start()
        self.store = fs.FiniteStore()

    def prepared(self, name='run-1', *, start=20):
        m = self.store.verify_static()
        run = self.evidence/name; run.mkdir()
        current = baseline(series(start=start))
        f = frame(start+12)
        self.clock.return_value = f.query_end
        self.store.record_admission(run, m, current, f,
            now=f.query_end, now_utc=f.validated_utc)
        self.store.begin_run(run, m, self.base)
        return run, m

    def result(self, run, manifest, *, index=1, recovered=200.0):
        phase = fs.phase_record(run, manifest, index, coverage(run, index))
        fs._write(run/'phase-evidence.json', phase)
        flags = dict.fromkeys(('owned_exit_confirmed', 'collector_terminal',
            'collector_cleanup_confirmed', 'http_terminal', 'inspection_terminal',
            'inspection_duplicate_closed', 'evidence_write_confirmed', 'cleanup_confirmed'), True)
        return dict(profile=fp.PROFILE_ID, run=str(run), manifest=manifest,
            identity=dict(pid=123, creation_time_100ns=456, executable=manifest['executable']),
            success=True, exit_code=0, resumed_monotonic=40.0 if index == 1 else 240.0,
            recovery_samples=5, service_ready=True, stop_requested=True,
            original_baseline=manifest['operator']['original_baseline'],
            current_baseline=fs._read(run/'finite-admission.json')['current_baseline'],
            finite_phase_sha256=service_store._digest(phase),
            finite_recovery_completed_monotonic=recovered, **flags)

    def test_two_linked_attempts_then_permanent_exhaustion(self):
        first, m1 = self.prepared()
        r1 = self.result(first, m1)
        self.store.finish_run(first, r1)
        second, m2 = self.prepared('run-2', start=220)
        identity = fs._read(second/'identity.json')
        self.assertEqual(identity['previous_run'], str(first))
        self.assertEqual(identity['previous_result_sha256'], service_store._digest(r1))
        self.assertEqual(identity['lifecycle'], 2)
        self.store.finish_run(second, self.result(second, m2, index=2, recovered=300.0))
        with self.assertRaisesRegex(ValueError, 'finite_attempts_exhausted'):
            self.store.verify_static()
        self.assertFalse((self.evidence/'incomplete.json').exists())

    def test_failure_retains_result_and_latch_and_refuses_second(self):
        run, m = self.prepared(); result = self.result(run, m)
        result['success'] = False
        result['cleanup_confirmed'] = False
        self.store.finish_run(run, result)
        before = (run/'result.json').read_bytes()
        self.assertTrue((self.evidence/'incomplete.json').exists())
        with self.assertRaises(ValueError): self.store.verify_static()
        with self.assertRaises(ValueError): self.store.finish_run(run, dict(result, success=True))
        self.assertEqual((run/'result.json').read_bytes(), before)

    def test_result_or_phase_tampering_prevents_second(self):
        run, m = self.prepared(); self.store.finish_run(run, self.result(run, m))
        phase = fs._read(run/'phase-evidence.json'); phase['coverage']['post_count'] = 65
        operator_store.atomic_json(run/'phase-evidence.json', phase)
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_missing_structural_evidence_is_not_terminal_success(self):
        run, m = self.prepared()
        result = self.result(run, m)
        (run/'phase-evidence.json').unlink()  # Temporary fixture only.
        with self.assertRaisesRegex(ValueError, 'finite_success_incomplete'):
            self.store.finish_run(run, result)
        self.assertTrue((run/'result.json').exists())
        self.assertEqual(fs._read(run/'result.json'), json.loads(json.dumps(result)))
        self.assertTrue((self.evidence/'incomplete.json').exists())
        self.assertNotIn('result_sha256', fs._read(self.evidence/'current.json'))
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_tampered_phase_raises_after_preserving_incomplete_success(self):
        run, m = self.prepared(); result = self.result(run, m)
        phase = fs._read(run/'phase-evidence.json')
        phase['coverage']['post_count'] = 65
        operator_store.atomic_json(run/'phase-evidence.json', phase)
        with self.assertRaisesRegex(ValueError, 'finite_success_incomplete'):
            self.store.finish_run(run, result)
        self.assertEqual(fs._read(run/'result.json'), json.loads(json.dumps(result)))
        self.assertTrue((self.evidence/'incomplete.json').exists())
        self.assertNotIn('result_sha256', fs._read(self.evidence/'current.json'))
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_incomplete_terminal_flags_and_coverage_fail_closed(self):
        run = self.evidence/'candidate'; run.mkdir()
        c = coverage(run, 1)
        for key, value in (('complete', False), ('workers_terminal', False),
                           ('post_count', 65), ('ready_count', True),
                           ('failure', 'missed_overlap'), ('lifecycle', 2)):
            changed = deepcopy(c); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                fs.phase_record(run, self.manifest, 1, changed)
        good = fs.phase_record(run, self.manifest, 1, c)
        self.assertTrue(good['coverage']['pending_semantic_review'])
        self.assertEqual(good['acceptance'], 'structural_only')

    def test_old_failed_root_and_other_profile_latch_block_finite(self):
        for name in ('gufo-ar4k-connect-wait-smoke-runs', 'gufo-native-installed-v1-runs'):
            root = self.root/name; root.mkdir()
            operator_store.atomic_json(root/'incomplete.json', {'historical': True})
            before = (root/'incomplete.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'prior_smoke_incomplete'):
                self.store.verify_static()
            self.assertEqual((root/'incomplete.json').read_bytes(), before)
            (root/'incomplete.json').unlink()  # Temporary fixture only.

    def test_current_recheck_exempts_only_exact_owned_finite_latch(self):
        run, m = self.prepared()
        self.store.recheck_static(m, current_run=run)
        old = self.root/'gufo-ar4k-smoke-runs'; old.mkdir()
        operator_store.atomic_json(old/'incomplete.json', {'old': True})
        with self.assertRaises(ValueError): self.store.recheck_static(m, current_run=run)

    def test_finite_latch_is_visible_to_existing_profile(self):
        run, m = self.prepared()
        installed = replace(service_store.PINS, evidence=self.root/'gufo-native-installed-v1-runs',
                            operator_evidence=self.root/'operator-runs')
        with self.assertRaisesRegex(ValueError, 'prior_smoke_incomplete'):
            smoke_store._incomplete_latches(installed)

    def test_fresh_admission_required_and_first_recovery_precedes_second(self):
        first, m = self.prepared(); self.store.finish_run(first, self.result(first, m))
        run = self.evidence/'run-2'; run.mkdir()
        with self.assertRaises(ValueError): self.store.begin_run(run, m, self.base)
        f = frame(32)
        with self.assertRaisesRegex(ValueError, 'finite_admission_before_recovery'):
            self.store.record_admission(run, m, baseline(series(start=20)), f,
                now=f.query_end, now_utc=f.validated_utc)
        current = baseline(series(start=220)); f = frame(232)
        self.clock.return_value = f.query_end
        self.store.record_admission(run, m, current, f,
            now=f.query_end, now_utc=f.validated_utc)
        self.clock.return_value += 3
        with self.assertRaisesRegex(ValueError, 'finite_admission_stale'):
            self.store.begin_run(run, m, self.base)

    def test_orphan_and_link_cycle_rejected(self):
        run, m = self.prepared(); self.store.finish_run(run, self.result(run, m))
        orphan = self.evidence/'orphan'; orphan.mkdir()
        with self.assertRaisesRegex(ValueError, 'finite_orphan'):
            self.store.verify_static()
        orphan.rmdir()  # Temporary fixture only.
        pointer = fs._read(self.evidence/'current.json')
        identity = fs._read(run/'identity.json'); identity['previous_run'] = str(run)
        operator_store.atomic_json(run/'identity.json', identity)
        pointer['identity_sha256'] = service_store._digest(identity)
        operator_store.atomic_json(self.evidence/'current.json', pointer)
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_partial_begin_never_grants_another_attempt(self):
        run = self.evidence/'run-1'; run.mkdir()
        f = frame(32); self.clock.return_value = f.query_end
        self.store.record_admission(run, self.manifest, baseline(series(start=20)), f,
            now=f.query_end, now_utc=f.validated_utc)
        real = fs._write
        def fail_manifest(path, value):
            if Path(path).name == 'manifest.json': raise OSError('disk full')
            return real(path, value)
        with patch.object(fs, '_write', side_effect=fail_manifest), self.assertRaises(OSError):
            self.store.begin_run(run, self.manifest, self.base)
        self.assertTrue((self.evidence/'incomplete.json').exists())
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_read_only_inspection_never_creates_files(self):
        before = sorted(str(p) for p in self.root.rglob('*'))
        self.assertTrue(fs.inspect_finite_profile()['reviewed'])
        self.assertEqual(sorted(str(p) for p in self.root.rglob('*')), before)

    def test_absent_null_and_tampered_review_are_not_launch_authority(self):
        with patch.object(fs, '_review', wraps=REAL_REVIEW):
            with self.assertRaises((ValueError, OSError)):
                self.store.verify_static()
            operator_store.atomic_json(self.anchor, dict(schema=1, profile_id=fp.PROFILE_ID,
                                                         certificate_sha256=None))
            with self.assertRaisesRegex(ValueError, 'finite_review_absent'):
                self.store.verify_static()
            q = fp.review_record(service_store._digest(self.value), 'finite-review',
                                  'header-envelope', 'controller-footprint')
            operator_store.atomic_json(self.pins.qualification, q)
            digest = operator_store.artifact_record(self.pins.qualification)['sha256']
            operator_store.atomic_json(self.anchor, dict(schema=1, profile_id=fp.PROFILE_ID,
                                                         certificate_sha256=digest))
            self.assertEqual(self.store.verify_static()['qualification'], q)
            operator_store.atomic_json(self.pins.qualification, dict(q, review_id='tampered'))
            with self.assertRaises(ValueError): self.store.verify_static()

    def test_current_recheck_detects_prior_result_change(self):
        first, m1 = self.prepared(); self.store.finish_run(first, self.result(first, m1))
        second, m2 = self.prepared('run-2', start=220)
        previous = fs._read(first/'result.json'); previous['recovery_samples'] = 4
        operator_store.atomic_json(first/'result.json', previous)
        with self.assertRaises(ValueError): self.store.recheck_static(m2, current_run=second)

    def test_terminal_pointer_write_failure_keeps_incomplete_latch(self):
        run, m = self.prepared(); result = self.result(run, m)
        with patch.object(operator_store, 'atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.store.finish_run(run, result)
        self.assertTrue((run/'result.json').exists())
        self.assertTrue((self.evidence/'incomplete.json').exists())
        with self.assertRaises(ValueError): self.store.verify_static()


if __name__ == '__main__':
    unittest.main()
