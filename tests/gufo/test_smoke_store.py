"""CPU-only checks for the one-attempt AR4k provenance store."""

from dataclasses import asdict, replace
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import operator_store
from gufo_control.operator_policy import Baseline
from gufo_control import smoke_store as store
from gufo_control.model_identity import SidecarPin


def digest(data):
    return sha256(data).hexdigest().upper()


def tree_digest(contents):
    lines = [f'library/gfx1151/{name}|{len(data)}|{sha256(data).hexdigest()}\n'
             for name, data in sorted(contents.items())]
    return digest(''.join(lines).encode())


class StoreFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.sdk = self.root / 'sdk'
        self.build = self.root / 'build'
        self.model = self.root / 'model'
        self.host = self.root / 'system32'
        self.evidence = self.root / 'smoke'
        self.operators = self.root / 'operators'
        for path in (self.sdk / 'bin', self.build, self.model, self.host,
                     self.evidence, self.operators):
            path.mkdir(parents=True, exist_ok=True)
        self.base = Baseline(('adapter', 1, 2, 3, 4, 'name', 5),
                             100, 200, (3, 4, 5), 0, 15)
        self.exe = self.build / 'gufo.exe'
        self.exe.write_bytes(b'exe')
        self.dlls = {'sdk-a.dll': (b'sdk-a',), 'sdk-b.dll': (b'sdk-b',)}
        self.vcpkg = {'vcpkg-a.dll': (b'vcpkg-a',)}
        self.host_dll = self.host / 'libomp140.x86_64.dll'
        self.host_dll.write_bytes(b'host-openmp')
        for name, (content,) in self.dlls.items():
            (self.sdk / 'bin' / name).write_bytes(content)
            (self.build / name).write_bytes(content)
        for name, (content,) in self.vcpkg.items():
            (self.build / name).write_bytes(content)
        self.trees = {}
        for name in ('hipblaslt', 'rocblas'):
            contents = {'a.bin': b'a', 'B.bin': b'B'}
            self.trees[name] = contents
            for base in (self.sdk / 'bin', self.build):
                path = base / name / 'library' / 'gfx1151'
                path.mkdir(parents=True)
                for filename, content in contents.items():
                    (path / filename).write_bytes(content)
        self.shards = []
        for n in range(3):
            path = self.model / f'shard-{n}.gguf'
            path.write_bytes(f'shard-{n}'.encode())
            self.shards.append(path)
        self.failed, self.gdn, self.iq = self._operator_results()
        self.margin = self.root / 'margin.md'
        self.margin.write_bytes(b'accepted margin')
        self.qualification = self.root / 'qualification.json'
        self.pins = store.StorePins(
            profile_id='ar4k-iq4xs-http-slots-smoke-v3', source=self.source,
            source_commit='source-commit', sdk=self.sdk, build=self.build,
            executable_name='gufo.exe', executable=(3, digest(b'exe')),
            sdk_dlls={n: (len(c[0]), digest(c[0])) for n, c in self.dlls.items()},
            vcpkg_dlls={n: (len(c[0]), digest(c[0])) for n, c in self.vcpkg.items()},
            host_openmp=self.host_dll,
            host_openmp_pin=(len(b'host-openmp'), digest(b'host-openmp')),
            trees={n: (2, 2, tree_digest(c))
                   for n, c in self.trees.items()},
            first_shard=self.shards[0], model_revision='model-revision',
            shard_names=tuple(p.name for p in self.shards),
            model_descriptors=tuple({'name': p.name,
                                     'size_bytes': p.stat().st_size,
                                     'descriptor_sha256': digest(p.read_bytes())}
                                    for p in self.shards),
            evidence=self.evidence, operator_evidence=self.operators,
            failed_run=self.failed.parent, gdn_run=self.gdn.parent,
            iq_run=self.iq.parent,
            failed_result_sha256=digest(self.failed.read_bytes()),
            gdn_result_sha256=digest(self.gdn.read_bytes()),
            iq_result_sha256=digest(self.iq.read_bytes()),
            margin_report=self.margin, margin_sha256=digest(self.margin.read_bytes()),
            qualification=self.qualification,
            bounds={'gpu_gib': 68, 'host_gib': 4, 'shared_gib': 20,
                    'prelaunch_gib': 49, 'runtime_gib': 24,
                    'commit_reserve_gib': 12},
        )
        self._write_qualification()

    def _operator_results(self):
        base = json.loads(json.dumps(asdict(self.base)))
        failed_run = self.operators / 'failed-gdn'
        failed_run.mkdir()
        operator_store.atomic_json(failed_run / 'result.json', {
            'success': False, 'cleanup_confirmed': True,
            'owned_exit_confirmed': True, 'collector_terminal': True,
            'recovery_samples': 5, 'original_baseline': base,
        })
        for probe in ('gdn', 'iq-experts'):
            run = self.operators / probe
            run.mkdir()
            result = {
                'success': True, 'cleanup_confirmed': True,
                'owned_exit_confirmed': True, 'collector_terminal': True,
                'recovery_samples': 5, 'original_baseline': base,
                'manifest': {'policy': operator_store.POLICY_ID,
                             'source': 'source-commit', 'probe': probe,
                             'executable': str(operator_store.BUILD /
                                               operator_store.PROBES[probe].filename),
                             'sdk': str(self.sdk),
                             'runtime_policy': operator_store.RUNTIME_POLICY,
                             'artifacts': [
                                 {'sha256': operator_store.PROBES[probe].sha256},
                                 *({'sha256': operator_store.DLL_SHA256[name]}
                                   for name in operator_store.DLLS),
                                 *({'sha256': operator_store.DLL_SHA256[name]}
                                   for name in operator_store.DLLS)],
                             },
            }
            operator_store.atomic_json(run / 'result.json', result)
        operator_store.atomic_json(self.operators / 'sequence.json', {
            'stage': 'iq-experts', 'success': True,
            'policy': operator_store.POLICY_ID, 'source': 'source-commit',
            'binary': operator_store.PROBES['iq-experts'].sha256,
            'baseline': base, 'run': str(self.operators / 'iq-experts'),
        })
        return (failed_run / 'result.json', self.operators / 'gdn' / 'result.json',
                self.operators / 'iq-experts' / 'result.json')

    def _write_qualification(self):
        operator_store.atomic_json(self.qualification,
                                   store.expected_qualification(self.pins, 'review-123'))

    def verify(self):
        return store._verify_static(
            self.pins,
            source_validator=lambda: None,
            model_validator=lambda first: store.ValidatedModel(
                first, self.pins.model_revision),
        )

    def recheck(self, manifest, *, current_run=None):
        return store._recheck_static(manifest, self.pins,
                                     source_validator=lambda: None,
                                     current_run=current_run)


class SmokeStoreTests(unittest.TestCase):
    def test_sibling_incomplete_blocks_verify_recheck_and_begin(self):
        for name in ('gufo-ar4k-smoke-runs', 'gufo-ar4k-connect-wait-smoke-runs',
                     'gufo-ar4k-http-slots-smoke-runs', 'gufo-ar4k-benchmark-runs',
                     'gufo-ar4k-benchmark-v2-runs',
                     'gufo-ar16k-benchmark-runs', 'gufo-ar16k-benchmark-v2-runs',
                     'gufo-ar16k-benchmark-v3-runs', 'gufo-mtp4k-stage-v1-runs'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                f = StoreFixture(temp)
                manifest = f.verify()
                sibling = f.root/name
                sibling.mkdir()
                operator_store.atomic_json(sibling/'attempt.json', {'run': 'old-clean-run'})
                f.verify()  # A clean consumed sibling does not consume this profile.
                f.recheck(manifest)
                operator_store.atomic_json(sibling/'incomplete.json', {})
                old_attempt = (sibling/'attempt.json').read_bytes()
                old_latch = (sibling/'incomplete.json').read_bytes()
                run = f.evidence/'new-run'; run.mkdir()
                for action in (f.verify, lambda: f.recheck(manifest),
                               lambda: store._begin_run(run, manifest, f.base, f.pins)):
                    with self.assertRaisesRegex(ValueError, 'incomplete'): action()
                    if name == 'gufo-ar16k-benchmark-v2-runs':
                        self.assertEqual((sibling/'attempt.json').read_bytes(), old_attempt)
                        self.assertEqual((sibling/'incomplete.json').read_bytes(), old_latch)
                self.assertFalse((f.evidence/'attempt.json').exists())

    def test_sidecar_stamp_change_refuses_static_recheck(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            sidecar = f.model/'MTP'/'mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
            sidecar.parent.mkdir()
            sidecar.write_bytes(b'fake-descriptor')
            pin = SidecarPin(sidecar, sidecar.stat().st_size, 4, 'A'*64, 1)
            f.pins = replace(f.pins, sidecar=pin)
            manifest['model']['sidecar'] = dict(path=str(sidecar), size_bytes=pin.size_bytes,
                descriptor_end=pin.descriptor_end, tensor_count=pin.tensor_count,
                descriptor_sha256=pin.descriptor_sha256, stamp=operator_store.stamp(sidecar))
            with patch.object(store, '_binding', return_value={}), patch.object(
                    store, 'expected_qualification', return_value=manifest['qualification']):
                f.recheck(manifest)
                sidecar.write_bytes(b'changed-descriptor')
                with self.assertRaisesRegex(ValueError, 'model_sidecar_changed'):
                    f.recheck(manifest)

    def test_current_16k_mapping_is_v3(self):
        self.assertEqual(store.BENCHMARK_16K, 'ar16k-iq4xs-pp1-cache-v3')
        self.assertEqual(store.PROFILE_ROOTS[store.BENCHMARK_16K],
                         'gufo-ar16k-benchmark-v3-runs')

    def test_only_exact_current_latch_is_exempt(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp); manifest = f.verify()
            run = f.evidence/'new-run'; run.mkdir()
            store._begin_run(run, manifest, f.base, f.pins)
            f.recheck(manifest, current_run=run)
            other = f.evidence/'other-run'; other.mkdir()
            with self.assertRaises(ValueError): f.recheck(manifest, current_run=other)
            sibling = f.root/'gufo-ar16k-benchmark-runs'; sibling.mkdir()
            operator_store.atomic_json(sibling/'incomplete.json', {'run': str(run)})
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                f.recheck(manifest, current_run=run)

    def test_next_profile_uses_distinct_exact_evidence_and_qualification(self):
        self.assertEqual(store.PROFILE_ID, 'ar4k-iq4xs-http-slots-smoke-v3')
        self.assertEqual(store.EVIDENCE, store.ROOT / 'reports/gufo-ar4k-http-slots-smoke-runs')
        self.assertEqual(store.QUALIFICATION, store.ROOT /
                         'reports/gufo-ar4k-http-slots-smoke-qualification.json')
        self.assertEqual(store.PINS.profile_id, store.PROFILE_ID)
        self.assertEqual(store.PINS.evidence, store.EVIDENCE)
        self.assertEqual(store.PINS.qualification, store.QUALIFICATION)
        self.assertNotEqual(store.EVIDENCE, store.ROOT / 'reports/gufo-ar4k-smoke-runs')
        self.assertNotEqual(store.QUALIFICATION, store.ROOT /
                            'reports/gufo-ar4k-smoke-qualification.json')
        self.assertNotEqual(store.EVIDENCE, store.ROOT /
                            'reports/gufo-ar4k-connect-wait-smoke-runs')
        self.assertNotEqual(store.QUALIFICATION, store.ROOT /
                            'reports/gufo-ar4k-connect-wait-smoke-qualification.json')
        self.assertEqual(store.BOUNDS, {'gpu_gib': 68, 'host_gib': 4, 'shared_gib': 20,
                                        'prelaunch_gib': 49, 'runtime_gib': 24,
                                        'commit_reserve_gib': 12})

    def test_qualification_binds_exact_per_run_recovery_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            expected = store.expected_qualification(f.pins, 'review-123')
            self.assertEqual(expected.get('recovery_policy'), 'per-run-recovery-stricter-runtime-v1')
            for value in (None, 'historical-recovery', 'per-run-recovery-stricter-runtime-v2'):
                changed = deepcopy(expected)
                if value is None:
                    changed.pop('recovery_policy')
                else:
                    changed['recovery_policy'] = value
                operator_store.atomic_json(f.qualification, changed)
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'qualification_mismatch'):
                    f.verify()
            operator_store.atomic_json(f.qualification, expected)
            manifest = f.verify()
            self.assertEqual(manifest['qualification'], expected)
            del manifest['qualification']['recovery_policy']
            with self.assertRaisesRegex(ValueError, 'qualification_mismatch'):
                f.recheck(manifest)

    def test_valid_manifest_and_recheck(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            self.assertEqual(manifest['profile'], 'ar4k-iq4xs-http-slots-smoke-v3')
            self.assertEqual(manifest['model']['revision'], 'model-revision')
            self.assertEqual(len(manifest['model']['shards']), 3)
            self.assertEqual(manifest['qualification']['model_descriptors'][0],
                             f.pins.model_descriptors[0])
            self.assertEqual(manifest['qualification']['guard_review_id'], 'review-123')
            self.assertEqual(len(manifest['artifacts']), 15)
            f.recheck(manifest)
            self.assertEqual(store._load_original_operator_baseline(f.pins), f.base)

    def test_profile_and_source_are_fixed(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            with self.assertRaisesRegex(ValueError, 'source_identity_changed'):
                store._verify_static(f.pins,
                    source_validator=lambda: (_ for _ in ()).throw(
                        ValueError('source_identity_changed')),
                    model_validator=lambda first: None)
            changed = replace(f.pins, profile_id='second-profile')
            with self.assertRaisesRegex(ValueError, 'profile'):
                store._verify_static(changed, source_validator=lambda: None,
                                     model_validator=lambda first: None)

    def test_binary_and_runtime_fail_before_model_validator(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            targets = [f.exe, *(f.sdk / 'bin' / n for n in f.dlls),
                       *(f.build / n for n in f.dlls),
                       *(f.build / n for n in f.vcpkg), f.host_dll]
            for target in targets:
                original = target.read_bytes()
                for mode in ('wrong', 'missing'):
                    with self.subTest(target=target, mode=mode):
                        if mode == 'wrong':
                            target.write_bytes(b'bad')
                        else:
                            target.unlink()
                        with self.assertRaisesRegex((ValueError, OSError),
                                                    'artifact|missing'):
                            f.verify()
                        target.write_bytes(original)

    def test_tree_checks_path_content_and_ordinal_sort(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            self.assertNotEqual(tree_digest(
                {'a.bin': b'a', 'B.bin': b'B'}), tree_digest(
                {'A.bin': b'a', 'b.bin': b'B'}))
            for base in (f.sdk / 'bin', f.build):
                target = base / 'hipblaslt/library/gfx1151/B.bin'
                original = target.read_bytes()
                target.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'tree'):
                    f.verify()
                target.write_bytes(original)
                target.rename(target.with_name('C.bin'))
                with self.assertRaisesRegex(ValueError, 'tree'):
                    f.verify()
                target.with_name('C.bin').rename(target)

    def test_operator_results_and_sequence_are_authenticated(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            for target in (f.failed, f.gdn, f.iq):
                original = target.read_bytes()
                target.write_bytes(original + b' ')
                with self.assertRaisesRegex(ValueError, 'operator_result_hash'):
                    f.verify()
                target.write_bytes(original)
            result = operator_store.read_json(f.gdn)
            result['cleanup_confirmed'] = False
            operator_store.atomic_json(f.gdn, result)
            f.pins = replace(f.pins, gdn_result_sha256=digest(f.gdn.read_bytes()))
            with self.assertRaisesRegex(ValueError, 'operator_result_invalid'):
                f.verify()

    def test_sequence_stage_baseline_and_latch(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            sequence = f.operators / 'sequence.json'
            state = operator_store.read_json(sequence)
            state['stage'] = 'gdn'
            operator_store.atomic_json(sequence, state)
            with self.assertRaisesRegex(ValueError, 'operator_sequence'):
                f.verify()
            state['stage'] = 'iq-experts'
            state['baseline']['available_min'] += 1
            operator_store.atomic_json(sequence, state)
            with self.assertRaisesRegex(ValueError, 'operator_baseline'):
                f.verify()
            state['baseline']['available_min'] -= 1
            operator_store.atomic_json(sequence, state)
            operator_store.atomic_json(f.operators / 'incomplete.json', {})
            with self.assertRaisesRegex(ValueError, 'operator_incomplete'):
                f.verify()

    def test_failed_gdn_baseline_is_original(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            failed = operator_store.read_json(f.failed)
            failed['original_baseline']['available_min'] += 1
            operator_store.atomic_json(f.failed, failed)
            f.pins = replace(f.pins, failed_result_sha256=digest(f.failed.read_bytes()))
            with self.assertRaisesRegex(ValueError, 'operator_baseline'):
                f.verify()

    def test_qualification_is_fail_closed_and_stamped(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            record = operator_store.read_json(f.qualification)
            record['guard_review_id'] = ''
            operator_store.atomic_json(f.qualification, record)
            with self.assertRaisesRegex(ValueError, 'guard_review'):
                f.verify()
            with self.assertRaisesRegex(ValueError, 'qualification_changed'):
                f.recheck(manifest)

    def test_recheck_detects_all_artifact_model_and_state_stamps(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            for target in [f.exe, f.sdk / 'bin/sdk-a.dll',
                           f.build / 'rocblas/library/gfx1151/B.bin',
                           *f.shards, f.failed, f.gdn, f.iq,
                           f.operators / 'sequence.json', f.margin,
                           f.qualification]:
                with self.subTest(target=target):
                    manifest = f.verify()
                    original = target.read_bytes()
                    target.write_bytes(original + b'changed')
                    with self.assertRaises(ValueError):
                        f.recheck(manifest)
                    target.write_bytes(original)
            manifest = f.verify()
            (f.model / 'mmproj-BF16.gguf').write_bytes(b'projector')
            with self.assertRaisesRegex(ValueError, 'projector'):
                f.recheck(manifest)

    def test_recheck_rejects_manifest_omission_and_new_tree_file(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            changed = deepcopy(manifest)
            changed['artifacts'].pop()
            with self.assertRaisesRegex(ValueError, 'manifest'):
                f.recheck(changed)
            changed = deepcopy(manifest)
            changed['artifacts'][0]['stamp'][0] = str(f.margin)
            with self.assertRaisesRegex(ValueError, 'manifest'):
                f.recheck(changed)
            target = f.build / 'hipblaslt/library/gfx1151/new.bin'
            target.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError, 'manifest'):
                f.recheck(manifest)

    def test_one_attempt_marker_survives_confirmed_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            run = f.evidence / 'run-one'
            run.mkdir()
            store._begin_run(run, manifest, f.base, f.pins)
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                store._begin_run(f.evidence / 'run-two', manifest, f.base, f.pins)
            store._finish_run(run, {'cleanup_confirmed': True, 'success': True}, f.pins)
            self.assertFalse((f.evidence / 'incomplete.json').exists())
            self.assertTrue((f.evidence / 'attempt.json').exists())
            with self.assertRaisesRegex(ValueError, 'attempt'):
                store._begin_run(f.evidence / 'run-two', manifest, f.base, f.pins)

    def test_public_begin_rechecks_before_consuming_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            run = f.evidence / 'run-one'
            run.mkdir()
            f.shards[0].write_bytes(b'changed')
            with patch.object(store, 'PINS', f.pins), patch.object(
                    operator_store, 'source_identity', return_value=None):
                with self.assertRaisesRegex(ValueError, 'model_shard_changed'):
                    store.begin_run(run, manifest, f.base)
            self.assertFalse((f.evidence / 'attempt.json').exists())

    def test_public_current_run_recheck_is_exact_and_strict_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            run = f.evidence / 'run-one'
            run.mkdir()
            other = f.evidence / 'run-two'
            other.mkdir()
            with patch.object(store, 'PINS', f.pins), patch.object(
                    operator_store, 'source_identity', return_value=None):
                store.begin_run(run, manifest, f.base)
                store.recheck_static(manifest, current_run=run)
                with self.assertRaisesRegex(ValueError, 'prior_smoke_incomplete'):
                    store.recheck_static(manifest)
                with self.assertRaises(ValueError):
                    store.recheck_static(manifest, current_run=other)
                with self.assertRaises(ValueError):
                    store.begin_run(other, manifest, f.base)

    def test_current_run_recheck_rejects_marker_and_manifest_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            run = f.evidence / 'run-one'
            run.mkdir()
            with patch.object(store, 'PINS', f.pins), patch.object(
                    operator_store, 'source_identity', return_value=None):
                store.begin_run(run, manifest, f.base)
                marker_paths = (f.evidence / 'attempt.json',
                                f.evidence / 'incomplete.json',
                                run / 'manifest.json')
                for path in marker_paths:
                    original = path.read_bytes()
                    try:
                        path.unlink()
                        with self.subTest(path=path, change='missing'):
                            with self.assertRaises(ValueError):
                                store.recheck_static(manifest, current_run=run)
                        path.write_bytes(b'{invalid json')
                        with self.subTest(path=path, change='malformed'):
                            with self.assertRaises(ValueError):
                                store.recheck_static(manifest, current_run=run)
                        changed = json.loads(original)
                        if path.name == 'manifest.json':
                            changed['profile'] = 'other-profile'
                        elif path.name == 'attempt.json':
                            changed['profile'] = 'other-profile'
                        else:
                            changed['original_baseline']['available_min'] += 1
                        operator_store.atomic_json(path, changed)
                        with self.subTest(path=path, change='mismatched'):
                            with self.assertRaises(ValueError):
                                store.recheck_static(manifest, current_run=run)
                    finally:
                        path.write_bytes(original)
                marker = operator_store.read_json(f.evidence / 'attempt.json')
                marker['run'] = str(f.evidence / 'run-two')
                operator_store.atomic_json(f.evidence / 'attempt.json', marker)
                with self.assertRaises(ValueError):
                    store.recheck_static(manifest, current_run=run)

    def test_current_run_recheck_rejects_changed_input_and_completed_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            run = f.evidence / 'run-one'
            run.mkdir()
            with patch.object(store, 'PINS', f.pins), patch.object(
                    operator_store, 'source_identity', return_value=None):
                store.begin_run(run, manifest, f.base)
                changed = deepcopy(manifest)
                changed['operator']['original_baseline']['available_min'] += 1
                with self.assertRaises(ValueError):
                    store.recheck_static(changed, current_run=run)
                changed = deepcopy(manifest)
                changed['profile'] = 'other-profile'
                with self.assertRaises(ValueError):
                    store.recheck_static(changed, current_run=run)
                store.finish_run(run, {'cleanup_confirmed': True})
                with self.assertRaises(ValueError):
                    store.recheck_static(manifest, current_run=run)
                with self.assertRaisesRegex(ValueError, 'attempt'):
                    store.begin_run(run, manifest, f.base)

    def test_begin_write_failure_keeps_consumed_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            f = StoreFixture(temp)
            manifest = f.verify()
            run = f.evidence / 'run-one'
            run.mkdir()
            original_atomic = operator_store.atomic_json

            def fail_manifest(path, value):
                if Path(path) == run / 'manifest.json':
                    raise OSError('simulated_manifest_write_failure')
                return original_atomic(path, value)

            with patch.object(store, 'PINS', f.pins), patch.object(
                    operator_store, 'source_identity', return_value=None), patch.object(
                    operator_store, 'atomic_json', side_effect=fail_manifest):
                with self.assertRaisesRegex(OSError, 'simulated_manifest_write_failure'):
                    store.begin_run(run, manifest, f.base)
            self.assertTrue((f.evidence / 'attempt.json').exists())
            self.assertTrue((f.evidence / 'incomplete.json').exists())
            self.assertFalse((run / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
