"""Offline candidate adapter checks; no native executable or telemetry is run."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import replace
import importlib
import importlib.util
import io
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import admission, smoke_store, smoke_guard, smoke_http, runtime_package, operator_store
from gufo_control.benchmark_runtime import BoundPolicy
from gufo_control.operator_policy import baseline, GIB
from test_operator_policy import frame, series
from test_smoke_guard import Harness
from test_smoke_policy import Owner
from test_smoke_store import StoreFixture


class ServiceSmokeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.service_smoke'),
                             'finite service adapter is missing')
        self.service = importlib.import_module('gufo_control.service_smoke')
        self.store = importlib.import_module('gufo_control.service_smoke_store')

    def manifest(self):
        p = self.store.PINS
        return dict(profile=p.profile_id, source=p.source_commit,
            executable=str(p.build/p.executable_name), sdk=str(p.sdk),
            bounds=dict(p.bounds), model=dict(revision=p.model_revision,
            first_shard=str(p.first_shard)),
            qualification=smoke_store.expected_qualification(p, 'offline-review'),
            margin_report=dict(sha256=p.margin_sha256))

    def test_exact_argv_and_workload(self):
        p = self.store.PINS
        expected = smoke_guard.fixed_argv('private')
        expected[0] = str(p.build/p.executable_name)
        expected += ['--request-policy', 'ar4k-service-v1', '--preserve-thinking', 'off']
        self.assertEqual(self.service.fixed_argv('private'), expected)
        binding = smoke_store.expected_qualification(p, 'review')['service']
        self.assertEqual(binding['source_tree'], '273d84974a604c81023dae15d379a9bfc0b1c29b')
        self.assertEqual(binding['operator_source'], smoke_store.PINS.source_commit)
        self.assertEqual(binding['runtime_policy_sha256'],
            '5AA64C7E718619E4654DCF4B5997D77AAE47B41611DCAA897020224FD0F0A5E8')
        workload = binding['workload']
        self.assertEqual(workload['request'], smoke_http.REQUEST)
        self.assertEqual(workload['argv'], self.service.fixed_argv('[PRIVATE-PER-RUN]'))
        self.assertEqual(workload['max_prompt_tokens'], 512)
        self.assertEqual(workload['max_ready_polls'], 240)
        self.assertEqual(workload['generation_posts'], 1)
        self.assertEqual(workload['model_queries'], 1)

    def test_closed_pins_and_unchanged_defaults(self):
        p = self.store.PINS
        self.assertEqual(p.source_commit, '139aa9c58dadcb75c1bd0741aad0823fc65a0547')
        self.assertEqual(p.operator_source_commit, smoke_store.PINS.source_commit)
        self.assertIsNone(smoke_store.PINS.operator_source_commit)
        for changes in (dict(source_commit=smoke_store.PINS.source_commit),
                dict(executable=smoke_store.PINS.executable), dict(build=p.build.parent),
                dict(margin_sha256='A'*64), dict(operator_source_commit=p.source_commit),
                dict(profile_id='unknown'), dict(bounds=dict(p.bounds, gpu_gib=69))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                smoke_store.expected_qualification(replace(p, **changes), 'review')

    def test_bound_admission_keeps_candidate_and_public_default(self):
        bound = BoundPolicy(self.store.PINS)
        p = bound.profile_from_manifest(self.manifest())
        f = frame(12); b = baseline(series())
        kw = dict(now=f.query_end, now_utc=f.validated_utc)
        self.assertEqual(bound.admission_reasons(p, b, f, **kw), [])
        self.assertIn('invalid_profile_identity', admission.evaluate_admission(
            f.snapshot, dict(p.envelope), now=f.query_end)['reasons'])
        self.assertEqual(p.envelope['source_commit'], self.store.PINS.source_commit)
        self.assertEqual(bound.runtime_reasons(p, b, f, Owner(), **kw), [])
        boundary = frame(12, available_physical_bytes=49*GIB,
                         host_commit_limit_bytes=100*GIB)
        self.assertEqual(bound.admission_reasons(p, b, boundary, **kw), [])
        for change in (dict(telemetry_ok=False), dict(gpu_scope='process'),
                       dict(adapter_luid=None), dict(adapter_identity=None),
                       dict(other_inference_pids=None),
                       dict(available_physical_bytes=49*GIB-1),
                       dict(host_commit_limit_bytes=100*GIB-1)):
            bad = frame(12, **change)
            self.assertTrue(bound.admission_reasons(p, b, bad, **kw))
        self.assertTrue(bound.admission_reasons(p, b, f,
            now=f.query_end+6, now_utc=f.validated_utc))
        for key, value in [('available_physical_bytes', 24*GIB-1),
                           ('host_commit_limit_bytes', 28*GIB-1)]:
            bad = frame(12, **{key: value})
            self.assertTrue(bound.runtime_reasons(p, b, bad, Owner(), **kw))

    def test_historical_evidence_is_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            candidate = replace(f.pins, source_commit=self.store.PINS.source_commit,
                                operator_source_commit=f.pins.source_commit)
            actual, _ = smoke_store._operator_sequence(candidate)
            self.assertEqual(actual, f.base)
            with self.assertRaisesRegex(ValueError, 'operator_result_invalid'):
                smoke_store._operator_sequence(replace(candidate, operator_source_commit=None))

    def test_mutual_incomplete_latches(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            new_root = f.root/smoke_store.PROFILE_ROOTS[self.store.PROFILE_ID]
            new_root.mkdir()
            latch = new_root/'incomplete.json'; latch.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'incomplete'): f.verify()
            latch.unlink()
            old_root = f.root/smoke_store.PROFILE_ROOTS[smoke_store.PROFILE_ID]
            old_root.mkdir(); (old_root/'incomplete.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                smoke_store._incomplete_latches(replace(f.pins, evidence=new_root))

    def test_source_head_tree_and_cleanliness(self):
        from types import SimpleNamespace
        good = [self.store.PINS.source_commit, self.store.SOURCE_TREE, '']
        for responses, valid in [(good, True), (['bad', *good[1:]], False),
                                 ([good[0], 'bad', ''], False),
                                 ([*good[:2], ' M file'], False)]:
            with patch.object(self.store.subprocess, 'run', side_effect=[
                    SimpleNamespace(returncode=0, stdout=x) for x in responses]):
                if valid: self.store.source_identity()
                else:
                    with self.assertRaisesRegex(ValueError, 'source_identity_changed'):
                        self.store.source_identity()

    def test_service_guard_reuses_owned_cleanup_and_five_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            h = Harness(temp)
            h.pins = replace(self.store.PINS, evidence=h.root)
            with patch.object(self.store, 'PINS', h.pins):
                h.manifest.update(self.manifest())
                h.manifest.update(self.store.service_binding(h.pins))
                result = h.run(policy_module=BoundPolicy(h.pins),
                    argv_builder=self.service.fixed_argv, profile_id=self.store.PROFILE_ID)
            self.assertTrue(result['success'], result)
            self.assertTrue(result['cleanup_confirmed'])
            self.assertEqual(result['recovery_samples'], 5)
            self.assertEqual(len(h.children), 1)
            self.assertEqual(len(h.http_tasks), 1)
            self.assertTrue(h.children[0].closed)

    def test_service_guard_fail_closed_retains_failed_cleanup_latch(self):
        for unconfirmed in (False, True):
            with tempfile.TemporaryDirectory() as temp:
                h = Harness(temp)
                h.pins = replace(self.store.PINS, evidence=h.root)
                h.close_error = unconfirmed
                h.query_changes = lambda phase, index: (
                    dict(host_commit_limit_bytes=28*GIB-1) if phase == 'serving_attempt' else {})
                with patch.object(self.store, 'PINS', h.pins):
                    h.manifest.update(self.manifest())
                    h.manifest.update(self.store.service_binding(h.pins))
                    result = h.run(policy_module=BoundPolicy(h.pins),
                        argv_builder=self.service.fixed_argv, profile_id=self.store.PROFILE_ID)
                self.assertFalse(result['success'])
                self.assertEqual(result['cleanup_confirmed'], not unconfirmed)
                self.assertEqual((h.root/'incomplete.json').exists(), unconfirmed)
                self.assertTrue((h.root/'attempt.json').exists())

    def test_status_and_print_only_never_execute_or_authorize(self):
        with (patch.object(smoke_guard._Guardian, 'run', side_effect=AssertionError('launch')),
             patch.object(self.store.ServiceStore, 'verify_static',
                          side_effect=ValueError('guard_review_missing')),
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO())):
            self.assertEqual(self.service.main(['status']), 0)
            self.assertEqual(self.service.main(['print-only']), 2)
            with self.assertRaises(SystemExit): self.service.main(['status', '--profile', 'x'])

    @contextmanager
    def candidate_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            f.pins = replace(f.pins, profile_id=self.store.PROFILE_ID,
                source_commit=self.store.PINS.source_commit,
                operator_source_commit=f.pins.source_commit)
            def row(name, pin):
                return dict(name=name, size_bytes=pin[0], sha256=pin[1])
            policy = dict(schema=1, kind='gufo-native-static-runtime',
                source_commit=f.pins.source_commit, sdk_version='10.2.0',
                executable=row('gufo.exe', f.pins.executable),
                sdk_dlls=[row(n, p) for n, p in f.pins.sdk_dlls.items()],
                vcpkg_dlls=[row(n, p) for n, p in f.pins.vcpkg_dlls.items()],
                host_openmp=row(f.host_dll.name, f.pins.host_openmp_pin),
                trees=[dict(name=n, count=p[0], bytes=p[1], digest=p[2])
                       for n, p in f.pins.trees.items()])
            files = []
            for file in f.build.rglob('*'):
                if file.is_file():
                    a = operator_store.artifact_record(file)
                    files.append(dict(path=file.relative_to(f.build).as_posix(),
                        size_bytes=a['stamp'][1], sha256=a['sha256']))
            host = dict(path=str(f.host_dll), size_bytes=f.pins.host_openmp_pin[0],
                        sha256=f.pins.host_openmp_pin[1])
            package = dict(schema=1, kind=policy['kind'], status='staged-static-only',
                created_utc='2026-09-27T00:00:00+00:00',
                expected_source_commit=f.pins.source_commit, sdk_version='10.2.0',
                policy_sha256=self.store.RUNTIME_POLICY_SHA256,
                sources=dict(build_dir=str(f.build), sdk_dir=str(f.sdk),
                             vcpkg_dir=str(f.root/'vcpkg')),
                files=files, trees=policy['trees'], host_prerequisites=[host],
                runtime_qualified=False)
            operator_store.atomic_json(f.build/'runtime-manifest.json', package)
            with (patch.object(self.store, 'PINS', f.pins),
                  patch.object(self.store, 'source_identity', return_value=None),
                  patch.object(smoke_store, 'validate_ar4k_model', side_effect=lambda first:
                    smoke_store.ValidatedModel(first, f.pins.model_revision)),
                  patch.object(runtime_package, 'load_policy', return_value=policy),
                  patch.object(runtime_package, '_host_openmp_record', return_value=host)):
                f._write_qualification()
                yield f, self.store.ServiceStore()

    def test_complete_package_and_recheck_mutations(self):
        with self.candidate_fixture() as (f, candidate):
            manifest = candidate.verify_static()
            self.assertEqual(manifest['service']['operator_source'], 'source-commit')
            candidate.recheck_static(manifest)
            for target in (f.exe, f.build/'sdk-a.dll', f.margin, f.qualification,
                           f.build/'runtime-manifest.json'):
                original = target.read_bytes()
                target.write_bytes(original+b'changed')
                with self.subTest(target=target), self.assertRaises(ValueError):
                    candidate.recheck_static(manifest)
                target.write_bytes(original)
                manifest = candidate.verify_static()
            extra = f.build/'unreviewed.dll'; extra.write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError, 'payload_set'):
                candidate.recheck_static(manifest)
            extra.unlink()
            for directory in (f.model, f.model.parent):
                projector = directory/'mmproj-BF16.gguf'; projector.write_bytes(b'foreign')
                with self.assertRaisesRegex(ValueError, 'projector'): candidate.verify_static()
                with self.assertRaisesRegex(ValueError, 'projector'):
                    candidate.recheck_static(manifest)
                projector.unlink()
            f.qualification.unlink()
            with self.assertRaisesRegex(ValueError, 'guard_review_missing'):
                candidate.verify_static()

    def test_candidate_single_attempt_and_latch_are_inherited(self):
        with self.candidate_fixture() as (f, candidate):
            manifest = candidate.verify_static()
            run = f.evidence/'run'; run.mkdir()
            candidate.begin_run(run, manifest, f.base)
            candidate.recheck_static(manifest, current_run=run)
            candidate.finish_run(run, dict(success=False, cleanup_confirmed=False))
            self.assertTrue((f.evidence/'incomplete.json').exists())
            with self.assertRaisesRegex(ValueError, 'incomplete'): candidate.verify_static()
            candidate.finish_run(run, dict(success=True, cleanup_confirmed=True))
            self.assertFalse((f.evidence/'incomplete.json').exists())
            self.assertTrue((f.evidence/'attempt.json').exists())
            with self.assertRaisesRegex(ValueError, 'attempt'): candidate.verify_static()

    def test_wrong_runtime_policy_and_qualification_binding(self):
        with self.candidate_fixture() as (f, candidate):
            path = f.build/'runtime-manifest.json'
            package = operator_store.read_json(path)
            package['policy_sha256'] = runtime_package.REVIEWED_POLICY_SHA256
            operator_store.atomic_json(path, package)
            with self.assertRaisesRegex(ValueError, 'runtime_manifest_identity'):
                candidate.verify_static()
            package['policy_sha256'] = self.store.RUNTIME_POLICY_SHA256
            operator_store.atomic_json(path, package)
            q = operator_store.read_json(f.qualification)
            q['service']['source_tree'] = '0'*40
            operator_store.atomic_json(f.qualification, q)
            with self.assertRaisesRegex(ValueError, 'qualification_mismatch'):
                candidate.verify_static()


if __name__ == '__main__':
    unittest.main()
