"""Offline installed service identity and durable repeat-run checks."""
from dataclasses import asdict, replace
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from gufo_control import operator_probe as probe, operator_store, smoke_guard, smoke_store
from gufo_control import service_store
from gufo_control.benchmark_runtime import BoundPolicy
from gufo_control.operator_policy import baseline
from test_operator_policy import frame, series
from test_smoke_store import StoreFixture


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest().upper()


class InstalledFixture:
    def __init__(self, root):
        self.f = StoreFixture(root)
        self.f.pins = replace(self.f.pins,
            profile_id=service_store.PROFILE_ID,
            source_commit=service_store.PINS.source_commit,
            model_revision=service_store.PINS.model_revision,
            operator_source_commit=self.f.pins.source_commit,
            evidence=self.f.root/'gufo-native-installed-v1-runs',
            qualification=self.f.root/'service-acceptance.json')
        self.f.pins.evidence.mkdir()
        self.profile = self.f.root/'installed-profile.json'
        self.value = service_store.expected_profile(self.f.pins)
        operator_store.atomic_json(self.profile, self.value)
        self.anchor = self.f.root/'installed-acceptance-anchor.json'
        operator_store.atomic_json(self.anchor, service_store.expected_anchor(self.value))
        operator_store.atomic_json(self.f.build/'runtime-manifest.json',
                                   {'policy_sha256': service_store.RUNTIME_POLICY_SHA256})

    @staticmethod
    def workload():
        return dict(schema=1, kind='gufo-native-installed-finite-workload',
                    profile_id=service_store.PROFILE_ID, lifetime_seconds=1200,
                    max_generation_posts=2, max_model_queries=2,
                    max_prompt_tokens=2304, max_output_tokens=256,
                    context_tokens=4096, sessions=1, sole_client=True)

    def accepted(self, workload=None):
        workload = self.workload() if workload is None else workload
        record = service_store.expected_acceptance(self.value, 'independent-review',
                                                   'persistent-envelope-review', workload)
        before = service_store.controller_artifacts()
        operator_store.atomic_json(self.f.pins.qualification, record)
        anchor = service_store.expected_anchor(self.value)
        anchor['installed_workload'] = workload
        anchor['acceptance_sha256'] = operator_store.artifact_record(
            self.f.pins.qualification)['sha256']
        operator_store.atomic_json(self.anchor, anchor)
        assert before == service_store.controller_artifacts()


class InstalledStoreTests(unittest.TestCase):
    def test_installed_candidate_is_header_build_without_moving_historical_smoke(self):
        old = service_store.service_smoke_store.PINS
        new = service_store.PINS
        self.assertEqual(old.source_commit, '139aa9c58dadcb75c1bd0741aad0823fc65a0547')
        self.assertEqual(new.source_commit, 'e6feed7ca52df4661d10434c72a8ea5b5f054bc2')
        self.assertEqual(service_store.SOURCE_TREE, '7912be2688d6874c0e13f4723aad00a5c3cbe1cf')
        self.assertEqual(service_store.RUNTIME_VARIANT, 'service-ar4k-header-v1')
        self.assertEqual(new.executable, (42440192,
            '9682019A5198B19CA131D60298A1E896186099ACC971C17B04BB31E302F7FFE9'))
        self.assertEqual(new.margin_sha256,
            'DAF6C99521AC4B751CD13E3462E46FEBB8F33038E24FCF39DCAF8C6309991E9F')
        self.assertNotEqual(new.build, old.build)

    def test_installed_source_check_uses_its_own_exact_head_and_tree(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'source'
            source.mkdir()
            pins = replace(service_store.PINS, source=source)
            with patch.object(service_store, 'PINS', pins), patch.object(
                    service_store.service_smoke_store, 'source_identity',
                    side_effect=AssertionError('historical source used')), patch.object(
                    service_store.build_identity, 'verify_git', return_value={'status': ''}) as verify:
                service_store.source_identity()
            self.assertEqual(verify.call_args.args[0], source)
            self.assertEqual(verify.call_args.kwargs['head'], pins.source_commit)
            self.assertEqual(verify.call_args.kwargs['tree'], service_store.SOURCE_TREE)

    def test_installed_source_check_refuses_a_changed_source(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'source'
            source.mkdir()
            pins = replace(service_store.PINS, source=source)
            with patch.object(service_store, 'PINS', pins), patch.object(
                    service_store.build_identity, 'verify_git',
                    side_effect=ValueError('git_identity_mismatch')):
                with self.assertRaisesRegex(ValueError, 'git_identity_mismatch'):
                    service_store.source_identity()

    def test_on_disk_profile_and_empty_anchor_bind_header_candidate(self):
        profile = operator_store.read_json(service_store.PROFILE_PATH)
        anchor = operator_store.read_json(service_store.ANCHOR_PATH)
        executable = Path(profile['controller']['python_executable'])
        self.assertTrue(executable.is_absolute())
        if not executable.is_file():
            self.skipTest('Pinned installed service Python interpreter required')
        result = subprocess.run([str(executable), '-B', '-c',
            'import json,platform,sys; print(json.dumps(dict('
            'python_implementation=platform.python_implementation(),'
            'python_version=platform.python_version(),python_executable=sys.executable)))'],
            capture_output=True, text=True, check=True, timeout=10)
        expected = service_store.expected_profile(service_store.PINS)
        expected['controller'] = dict(id=service_store.CONTROLLER_ID, **json.loads(result.stdout))
        self.assertEqual(profile, expected)
        self.assertEqual(anchor, service_store.expected_anchor(profile))
        self.assertIsNone(anchor['acceptance_sha256'])
        self.assertIsNone(anchor['installed_workload'])

    def test_profile_digest_mismatch_refuses_even_with_empty_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            anchor = operator_store.read_json(f.anchor)
            anchor['profile_sha256'] = '0' * 64
            operator_store.atomic_json(f.anchor, anchor)
            with self.assertRaisesRegex(ValueError, 'acceptance_anchor_invalid'):
                f.store.verify_static()

    def fixture(self, root, *, accepted=False):
        fixture = InstalledFixture(root)
        self.enterContext(patch.object(service_store, 'PINS', fixture.f.pins))
        self.enterContext(patch.object(service_store, 'ANCHOR_PATH', fixture.anchor))
        self.enterContext(patch.object(service_store, 'source_identity', return_value=None))
        self.enterContext(patch.object(service_store.runtime_package, 'verify_runtime',
                                      return_value={'policy_sha256': service_store.RUNTIME_POLICY_SHA256}))
        self.enterContext(patch.object(smoke_store, 'validate_ar4k_model',
            side_effect=lambda first: smoke_store.ValidatedModel(first, fixture.f.pins.model_revision)))
        if accepted:
            fixture.accepted()
        fixture.store = service_store.InstalledStore(fixture.profile)
        return fixture

    def test_missing_acceptance_refuses_separately_from_valid_static_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            with (patch.object(smoke_guard, '_Guardian', side_effect=AssertionError('child factory')),
                  patch.object(probe, 'collect_one', side_effect=AssertionError('telemetry')),
                  patch.object(probe, 'collect_baseline', side_effect=AssertionError('telemetry'))):
                status = service_store.inspect_installed_profile(f.profile)
                with self.assertRaisesRegex(ValueError, 'persistent_service_unqualified'):
                    f.store.verify_static()
            self.assertTrue(status['artifacts_valid'], status)
            self.assertFalse(status['qualified'])
            self.assertIn('persistent_service_unqualified', status['refusals'])
            self.assertFalse((f.f.pins.evidence/'current.json').exists())

    def test_static_manifest_only_is_not_service_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            operator_store.atomic_json(f.f.pins.qualification,
                {'qualified': True, 'runtime_qualified': False})
            with self.assertRaisesRegex(ValueError, 'persistent_service_unqualified'):
                f.store.verify_static()

    def test_inspection_reports_independent_identity_qualification_and_latch_facts(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            bad = json.loads(json.dumps(f.value))
            bad['runtime']['variant'] = 'baseline'
            operator_store.atomic_json(f.profile, bad)
            sibling = f.f.root/smoke_store.PROFILE_ROOTS[smoke_store.SERVICE_SMOKE]
            sibling.mkdir()
            operator_store.atomic_json(sibling/'incomplete.json', {'run': 'failed-smoke'})
            state = service_store.inspect_installed_profile(f.profile)
            self.assertFalse(state['artifacts_valid'])
            self.assertFalse(state['qualified'])
            self.assertTrue(any('installed_profile_mismatch' in x for x in state['refusals']))
            self.assertIn('persistent_service_unqualified', state['refusals'])
            self.assertTrue(any('incomplete' in x for x in state['refusals']))

    def test_profile_rejects_wrong_candidate_identity_and_boolean_bound(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            changes = ((('runtime', 'variant'), 'baseline'),
                       (('runtime', 'policy_sha256'), '0'*64),
                       (('source', 'tree'), '0'*40),
                       (('model', 'revision'), 'wrong'),
                       (('profile_id',), 'wrong'),
                       (('envelope', 'gpu_gib'), True))
            for keys, value in changes:
                bad = json.loads(json.dumps(f.value))
                target = bad
                for key in keys[:-1]: target = target[key]
                target[keys[-1]] = value
                operator_store.atomic_json(f.profile, bad)
                with self.subTest(keys=keys), self.assertRaisesRegex(ValueError, 'installed_profile'):
                    f.store.verify_static()
            operator_store.atomic_json(f.profile, f.value)

    def test_projector_and_related_incomplete_marker_refuse(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            for directory in (f.f.model, f.f.model.parent):
                projector = directory/'mmproj-BF16.gguf'
                projector.write_bytes(b'projector')
                with self.assertRaisesRegex(ValueError, 'projector'):
                    f.store.verify_static()
                projector.unlink()
            sibling = f.f.root/smoke_store.PROFILE_ROOTS[smoke_store.SERVICE_SMOKE]
            sibling.mkdir()
            operator_store.atomic_json(sibling/'incomplete.json', {'run': 'failed-smoke'})
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                f.store.verify_static()

    def test_installed_latch_blocks_finite_profile(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            operator_store.atomic_json(f.f.pins.evidence/'incomplete.json', {'run': 'failed'})
            old = replace(f.f.pins, profile_id=smoke_store.SERVICE_SMOKE,
                evidence=f.f.root/smoke_store.PROFILE_ROOTS[smoke_store.SERVICE_SMOKE])
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                smoke_store._incomplete_latches(old)

    def test_source_history_is_not_candidate_source(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            self.assertNotEqual(f.value['source']['commit'], f.value['operator_history']['source_commit'])
            self.assertEqual(f.value['source']['commit'], service_store.PINS.source_commit)
            self.assertEqual(f.value['operator_history']['source_commit'], 'source-commit')

    def test_controller_sources_are_bound_into_acceptance_and_recheck(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            self.assertIn('controller_artifacts', manifest)
            self.assertGreaterEqual(len(manifest['controller_artifacts']), 4)
            self.assertEqual(manifest['qualification']['controller_artifacts'],
                             manifest['controller_artifacts'])
            with patch.object(service_store, 'controller_artifacts',
                              return_value=[{'module': 'changed', 'sha256': '0'*64}]):
                with self.assertRaisesRegex(ValueError, 'controller'):
                    f.store.recheck_static(manifest)

    def test_on_disk_anchor_approval_cycle_keeps_controller_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            before = service_store.controller_artifacts()
            f.accepted()
            manifest = f.store.verify_static()
            self.assertEqual(before, service_store.controller_artifacts())
            self.assertEqual(manifest['qualification_anchor']['installed_workload'],
                             f.workload())
            self.assertEqual(manifest['qualification_anchor']['acceptance_sha256'],
                             manifest['qualification_stamp']['sha256'])
            f.store.recheck_static(manifest)
            anchor = operator_store.read_json(f.anchor)
            anchor['acceptance_sha256'] = '0'*64
            operator_store.atomic_json(f.anchor, anchor)
            with self.assertRaises(ValueError):
                f.store.recheck_static(manifest)

    def test_missing_installed_workload_and_smoke_substitution_refuse(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'installed_workload'):
                service_store.expected_acceptance(f.value, 'review', 'envelope', None)
            smoke = service_store.service_smoke_store.service_binding(
                service_store.service_smoke_store.PINS)['service']['workload']
            with self.assertRaisesRegex(ValueError, 'installed_workload'):
                service_store.expected_acceptance(f.value, 'review', 'envelope', smoke)
            anchor = operator_store.read_json(f.anchor)
            anchor['acceptance_sha256'] = '0'*64
            operator_store.atomic_json(f.anchor, anchor)
            with self.assertRaisesRegex(ValueError, 'persistent_service_unqualified'):
                f.store.verify_static()

    def test_changed_or_malformed_on_disk_anchor_refuses(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            anchor = operator_store.read_json(f.anchor)
            anchor['installed_workload']['max_generation_posts'] += 1
            operator_store.atomic_json(f.anchor, anchor)
            with self.assertRaisesRegex(ValueError, 'anchor|acceptance'):
                f.store.recheck_static(manifest)
            with self.assertRaisesRegex(ValueError, 'service_acceptance'):
                f.store.verify_static()
            anchor['schema'] = True
            operator_store.atomic_json(f.anchor, anchor)
            with self.assertRaisesRegex(ValueError, 'acceptance_anchor_invalid'):
                f.store.verify_static()

    def test_temporary_safety_dependency_change_invalidates_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            copied = f.f.root/'controller-sources'
            shutil.copytree(service_store.CONTROLLER_SOURCE_DIR, copied,
                            ignore=shutil.ignore_patterns('__pycache__'))
            with patch.object(service_store, 'CONTROLLER_SOURCE_DIR', copied):
                f.accepted()
                manifest = f.store.verify_static()
                expected = {'operator_policy.py', 'winjob.py', 'operator_probe.py',
                    'telemetry.py', 'smoke_http.py', 'model_identity.py',
                    'runtime_package.py', 'windows_probe.ps1', 'windows_counters.cs'}
                self.assertTrue(expected.issubset({row['name'] for row in
                                                   manifest['controller_artifacts']}))
                target = copied/'operator_policy.py'
                target.write_bytes(target.read_bytes()+b'\n# changed safety behavior\n')
                with self.assertRaisesRegex(ValueError, 'controller'):
                    f.store.recheck_static(manifest)
                with self.assertRaisesRegex(ValueError, 'service_acceptance'):
                    f.store.verify_static()

    def test_new_nested_service_source_invalidates_controller_binding(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root)
            copied = f.f.root/'controller-sources'
            shutil.copytree(service_store.CONTROLLER_SOURCE_DIR, copied,
                            ignore=shutil.ignore_patterns('__pycache__'))
            with patch.object(service_store, 'CONTROLLER_SOURCE_DIR', copied):
                f.accepted()
                manifest = f.store.verify_static()
                future = copied/'future_service'
                future.mkdir()
                (future/'guardian.py').write_text('SAFE = False\n', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'controller'):
                    f.store.recheck_static(manifest)

    def test_bound_policy_admits_only_exact_installed_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            bound = BoundPolicy(f.f.pins)
            profile = bound.profile_from_manifest(manifest)
            sample = frame(12)
            self.assertEqual(bound.admission_reasons(profile, baseline(series()), sample,
                now=sample.query_end, now_utc=sample.validated_utc), [])
            changed = json.loads(json.dumps(manifest))
            changed['qualification']['profile_sha256'] = '0'*64
            with self.assertRaises(ValueError):
                bound.profile_from_manifest(changed)

    def test_bound_frame_policy_does_not_read_controller_sources_per_sample(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            bound = BoundPolicy(f.f.pins)
            profile = bound.profile_from_manifest(f.store.verify_static())
            sample = frame(12)
            with patch.object(service_store, 'controller_artifacts',
                              side_effect=AssertionError('source read during frame')):
                self.assertEqual(bound.admission_reasons(profile, baseline(series()), sample,
                    now=sample.query_end, now_utc=sample.validated_utc), [])

    def test_no_child_failed_result_cannot_retire_latch(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            run = f.f.pins.evidence/'no-child'; run.mkdir()
            f.store.begin_run(run, manifest, f.f.base)
            result = self.clean_result(run, manifest)
            result['success'] = False
            result['resumed_monotonic'] = None
            f.store.finish_run(run, result)
            self.assertTrue((f.f.pins.evidence/'incomplete.json').exists())
            self.assertEqual(operator_store.read_json(run/'result.json')['success'], False)

    def test_missing_child_identity_cannot_retire_latch(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            run = f.f.pins.evidence/'missing-child'; run.mkdir()
            f.store.begin_run(run, manifest, f.f.base)
            result = self.clean_result(run, manifest)
            result['identity'] = None
            f.store.finish_run(run, result)
            self.assertTrue((f.f.pins.evidence/'incomplete.json').exists())

    def test_clean_stop_allows_second_start_with_preserved_first_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            first = f.f.pins.evidence/'first'; first.mkdir()
            f.store.begin_run(first, manifest, f.f.base)
            f.store.recheck_static(manifest, current_run=first)
            self.assertFalse((f.f.pins.evidence/'attempt.json').exists())
            result = self.clean_result(first, manifest)
            f.store.finish_run(first, result)
            old = (first/'result.json').read_bytes()
            second = f.f.pins.evidence/'second'; second.mkdir()
            f.store.begin_run(second, manifest, f.f.base)
            self.assertNotEqual(operator_store.read_json(f.f.pins.evidence/'current.json')['run'], str(first))
            self.assertEqual((first/'result.json').read_bytes(), old)
            self.assertTrue((second/'manifest.json').exists())

    def test_failed_recovery_blocks_second_start_and_keeps_result(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            first = f.f.pins.evidence/'first'; first.mkdir()
            f.store.begin_run(first, manifest, f.f.base)
            result = self.clean_result(first, manifest)
            result['recovery_samples'] = 4
            f.store.finish_run(first, result)
            old = (first/'result.json').read_bytes()
            second = f.f.pins.evidence/'second'; second.mkdir()
            with self.assertRaisesRegex(ValueError, 'incomplete|prior|recovery'):
                f.store.begin_run(second, manifest, f.f.base)
            self.assertEqual((first/'result.json').read_bytes(), old)
            with self.assertRaises(ValueError):
                f.store.finish_run(first, self.clean_result(first, manifest))

    def test_simultaneous_starts_refuse_without_overwriting_first(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            first = f.f.pins.evidence/'first'; first.mkdir()
            second = f.f.pins.evidence/'second'; second.mkdir()
            barrier = threading.Barrier(2)
            def start(run):
                barrier.wait()
                try:
                    f.store.begin_run(run, manifest, f.f.base)
                    return 'started'
                except (ValueError, FileExistsError):
                    return 'refused'
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(start, (first, second)))
            self.assertCountEqual(results, ('started', 'refused'))
            pointer = operator_store.read_json(f.f.pins.evidence/'current.json')
            self.assertEqual(sum((run/'manifest.json').exists() for run in (first, second)), 1)
            self.assertTrue((Path(pointer['run'])/'manifest.json').exists())

    def test_stale_pointer_and_orphaned_evidence_refuse(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            orphan = f.f.pins.evidence/'orphan'; orphan.mkdir()
            operator_store.atomic_json(orphan/'phase.json', {'phase': 'before-create'})
            with self.assertRaisesRegex(ValueError, 'current_missing'):
                f.store.verify_static()
            other = f.f.pins.evidence/'other'; other.mkdir()
            with self.assertRaisesRegex(ValueError, 'current_missing'):
                f.store.begin_run(other, manifest, f.f.base)
            (orphan/'phase.json').unlink()
            operator_store.atomic_json(f.f.pins.evidence/'current.json', {'run': 'wrong'})
            with self.assertRaisesRegex(ValueError, 'current_invalid'):
                f.store.verify_static()

    def test_prepared_run_allows_its_own_prelaunch_log_only(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            run = f.f.pins.evidence/'prepared'; run.mkdir()
            operator_store.atomic_json(run/'phase.json', {'phase': 'baseline'})
            f.store.recheck_static(manifest, prepared_run=run)
            f.store.begin_run(run, manifest, f.f.base)
            self.assertTrue((run/'phase.json').exists())

    def test_abandoned_prelaunch_result_refuses_even_if_selected_as_prepared_run(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            run = f.f.pins.evidence/'abandoned'; run.mkdir()
            operator_store.atomic_json(run/'result.json', {'success': False})
            with self.assertRaises(ValueError):
                f.store.recheck_static(manifest, prepared_run=run)
            with self.assertRaises(ValueError):
                f.store.begin_run(run, manifest, f.f.base)

    def test_prepared_run_does_not_exempt_other_run_or_related_latch(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            pending = f.f.pins.evidence/'pending'; pending.mkdir()
            operator_store.atomic_json(pending/'phase.json', {'phase': 'baseline'})
            other = f.f.pins.evidence/'other'; other.mkdir()
            operator_store.atomic_json(other/'phase.json', {'phase': 'abandoned'})
            with self.assertRaisesRegex(ValueError, 'current_missing'):
                f.store.recheck_static(manifest, prepared_run=pending)
            (other/'phase.json').unlink()
            sibling = f.f.root/smoke_store.PROFILE_ROOTS[smoke_store.SERVICE_SMOKE]
            sibling.mkdir()
            operator_store.atomic_json(sibling/'incomplete.json', {'run': 'failed'})
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                f.store.recheck_static(manifest, prepared_run=pending)

    def test_prior_result_tamper_refuses_after_second_clean_stop(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.fixture(root, accepted=True)
            manifest = f.store.verify_static()
            first = f.f.pins.evidence/'first'; first.mkdir()
            f.store.begin_run(first, manifest, f.f.base)
            f.store.finish_run(first, self.clean_result(first, manifest))
            second = f.f.pins.evidence/'second'; second.mkdir()
            f.store.begin_run(second, manifest, f.f.base)
            f.store.finish_run(second, self.clean_result(second, manifest))
            first_result = operator_store.read_json(first/'result.json')
            first_result['failure'] = 'tampered'
            operator_store.atomic_json(first/'result.json', first_result)
            with self.assertRaisesRegex(ValueError, 'prior_result'):
                f.store.verify_static()

    @staticmethod
    def clean_result(run, manifest):
        return dict(profile=service_store.PROFILE_ID, run=str(run), manifest=manifest,
            success=True, owned_exit_confirmed=True, collector_terminal=True,
            collector_cleanup_confirmed=True, http_terminal=True,
            inspection_terminal=True, inspection_duplicate_closed=True,
            evidence_write_confirmed=True, cleanup_confirmed=True,
            recovery_samples=5, resumed_monotonic=1, exit_code=0,
            identity=dict(pid=1234, creation_time_100ns=5678,
                          executable=manifest['executable']))


if __name__ == '__main__':
    unittest.main()
