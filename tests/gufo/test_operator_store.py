from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import operator_store as store
from gufo_control.operator_policy import Baseline, PROBES


@contextmanager
def runtime_fixture():
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
        root = Path(folder)
        sdk, build = root/'sdk', root/'build'
        build.mkdir()
        for part in ('bin', 'lib/llvm/bin', 'lib/llvm/amdgcn/bitcode'):
            (sdk/part).mkdir(parents=True, exist_ok=True)
        pins = {}
        for name in store.DLLS:
            content = ('test-runtime:' + name).encode()
            pins[name] = hashlib.sha256(content).hexdigest().upper()
            (sdk/'bin'/name).write_bytes(content)
            (build/name).write_bytes(content)
        probes = {}
        for key, probe in PROBES.items():
            content = ('test-executable:' + key).encode()
            (build/probe.filename).write_bytes(content)
            probes[key] = replace(probe, sha256=hashlib.sha256(content).hexdigest().upper())
        for name, value in (('SDK', sdk), ('BUILD', build), ('DLL_SHA256', pins),
                            ('PROBES', probes)):
            stack.enter_context(patch.object(store, name, value))
        stack.enter_context(patch.object(store, 'source_identity'))
        yield sdk, build, probes


@contextmanager
def retry_fixture():
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
        root = Path(folder)
        run = root/'reviewed-failure'
        run.mkdir()
        base = Baseline(('original',), 100, 200, (1, 2, 3), 0, 11)
        values = json.loads(json.dumps(asdict(base)))
        result = {
            'success': False, 'cleanup_confirmed': True,
            'owned_exit_confirmed': True, 'collector_terminal': True,
            'recovery_samples': 5, 'exit_code': 0xC0000005,
            'failure': 'nonzero_exit', 'numerical_pass': False,
            'original_baseline': values,
            'manifest': {
                'policy': 'operator-bootstrap-v1', 'source': store.SOURCE_COMMIT,
                'probe': 'gdn', 'executable': str(store.BUILD/PROBES['gdn'].filename),
                'sdk': str(store.SDK),
                'artifacts': [
                    {'sha256': PROBES['gdn'].sha256},
                    *({'sha256': store.DLL_SHA256[name]} for name in store.DLLS),
                ],
            },
        }
        state = {'stage': 'gdn', 'policy': 'operator-bootstrap-v1',
                 'source': store.SOURCE_COMMIT, 'binary': PROBES['gdn'].sha256,
                 'success': False, 'baseline': values, 'run': str(run)}
        store.atomic_json(run/'result.json', result)
        store.atomic_json(root/'sequence.json', state)
        digest = hashlib.sha256((run/'result.json').read_bytes()).hexdigest().upper()
        for name, value in (('EVIDENCE', root), ('REVIEWED_FAILED_RUN', run),
                            ('REVIEWED_RESULT_SHA256', digest)):
            stack.enter_context(patch.object(store, name, value))
        yield root, run, base, result, state


class StoreTests(unittest.TestCase):
    def test_atomic_and_latch_and_failed_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root/'run'
            run.mkdir()
            base = Baseline(('test',), 100, 200, (1, 2, 3), 0, 11)
            store.begin(root, run, PROBES['gdn'], base)
            with self.assertRaisesRegex(ValueError, 'cleanup'):
                store.sequence_baseline(root, 'gdn')
            store.finish(root, run, PROBES['gdn'], base,
                         {'success': False, 'cleanup_confirmed': True})
            self.assertFalse((root/'incomplete.json').exists())
            with self.assertRaisesRegex(ValueError, 'review'):
                store.sequence_baseline(root, 'iq-experts')
            self.assertFalse(store.read_json(run/'result.json')['success'])

    def test_write_failure_keeps_latch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = Baseline(('test',), 100, 200, (1, 2, 3), 0, 11)
            store.begin(root, root, PROBES['gdn'], base)
            with patch.object(store, 'atomic_json', side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    store.finish(root, root, PROBES['gdn'], base,
                                 {'success': True, 'cleanup_confirmed': True})
            self.assertTrue((root/'incomplete.json').exists())

    def test_sequence_keeps_original_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = Baseline(('original',), 100, 200, (1, 2, 3), 0, 11)
            self.assertIsNone(store.sequence_baseline(root, 'gdn'))
            with self.assertRaisesRegex(ValueError, 'gdn_required'):
                store.sequence_baseline(root, 'iq-experts')
            store.begin(root, root, PROBES['gdn'], base)
            store.finish(root, root, PROBES['gdn'], base,
                         {'success': True, 'cleanup_confirmed': True})
            self.assertEqual(store.sequence_baseline(root, 'iq-experts'), base)
            with self.assertRaises(ValueError):
                store.sequence_baseline(root, 'gdn')

    def test_environment(self):
        original = {'Path': 'old', 'gufo_TEST': 'x', 'HIP_PATH': 'wrong', 'SystemRoot': 'Windows'}
        env = store.child_environment(original)
        self.assertEqual(original['Path'], 'old')
        self.assertNotIn('gufo_TEST', env)
        self.assertNotIn('Path', env)
        self.assertTrue(env['PATH'].startswith(str(store.SDK/'bin')))
        for key in ('hsa_TEST', 'HIP_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES', 'GPU_DEVICE_ORDINAL'):
            with self.assertRaises(ValueError):
                store.child_environment({key: '0'})

    def test_recheck_detects_change(self):
        with runtime_fixture() as (sdk, build, probes):
            for target in (build/probes['gdn'].filename,
                           sdk/'bin'/store.DLLS[0], build/store.DLLS[0]):
                with self.subTest(target=target):
                    original = target.read_bytes()
                    manifest = store.verify(probes['gdn'])
                    target.write_bytes(original + b'changed')
                    with self.assertRaisesRegex(ValueError, 'artifact_changed'):
                        store.recheck(manifest)
                    target.write_bytes(original)

    def test_binary_hash_and_required_local_runtime(self):
        with runtime_fixture() as (sdk, build, probes):
            for probe in probes.values():
                with self.subTest(probe=probe.key):
                    manifest = store.verify(probe)
                    self.assertEqual(len(manifest['artifacts']), 7)
                    self.assertEqual(manifest['runtime_policy'], store.RUNTIME_POLICY)
                    self.assertEqual(
                        [e['stamp'][0] for e in manifest['artifacts'][4:]],
                        [str((build/name).resolve()) for name in store.DLLS])
                    store.recheck(manifest)
            (build/probes['gdn'].filename).write_bytes(b'wrong executable')
            with self.assertRaisesRegex(ValueError, 'binary_hash_mismatch'):
                store.verify(probes['gdn'])

    @unittest.skipUnless(os.name == 'nt', 'Windows file lock')
    def test_lock_and_release(self):
        with tempfile.TemporaryDirectory() as folder:
            with store.exclusive(folder):
                with self.assertRaises(RuntimeError):
                    with store.exclusive(folder):
                        self.fail('second owner acquired lock')
            with store.exclusive(folder):
                pass


class AppLocalRuntimeTests(unittest.TestCase):
    def test_each_source_and_adjacent_dll_is_required_and_pinned(self):
        with runtime_fixture() as (sdk, build, probes):
            for directory in (sdk/'bin', build):
                for name in store.DLLS:
                    target = directory/name
                    original = target.read_bytes()
                    for mode in ('missing', 'wrong'):
                        with self.subTest(directory=directory, name=name, mode=mode):
                            if mode == 'missing':
                                target.unlink()
                            else:
                                target.write_bytes(b'wrong runtime')
                            for probe in probes.values():
                                with self.assertRaises((ValueError, OSError)):
                                    store.verify(probe)
                            target.write_bytes(original)

    def test_recheck_rejects_missing_runtime_and_manifest_tampering(self):
        with runtime_fixture() as (sdk, build, probes):
            manifest = store.verify(probes['gdn'])
            for position in range(1, 7):
                changed = deepcopy(manifest)
                changed['artifacts'][position]['sha256'] = '0'*64
                with self.assertRaisesRegex(ValueError, 'manifest_runtime_mismatch'):
                    store.recheck(changed)
            for field, value in (('runtime_policy', 'old'), ('source', 'wrong'),
                                 ('policy', 'wrong'), ('executable', 'wrong'),
                                 ('sdk', 'wrong'), ('probe', 'unknown')):
                changed = deepcopy(manifest)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, 'manifest_runtime_mismatch'):
                    store.recheck(changed)
            changed = deepcopy(manifest)
            changed['artifacts'].pop()
            with self.assertRaisesRegex(ValueError, 'manifest_runtime_mismatch'):
                store.recheck(changed)
            changed = deepcopy(manifest)
            changed['artifacts'][-1]['stamp'][0] = str(build/'other.dll')
            with self.assertRaisesRegex(ValueError, 'manifest_runtime_mismatch'):
                store.recheck(changed)
            (build/store.DLLS[0]).unlink()
            with self.assertRaises((ValueError, OSError)):
                store.recheck(manifest)

    def test_exact_retry_preserves_baseline_and_latch(self):
        with retry_fixture() as (root, run, base, result, state):
            before = (root/'sequence.json').read_bytes()
            self.assertEqual(store.sequence_baseline(root, 'gdn'), base)
            self.assertEqual((root/'sequence.json').read_bytes(), before)
            with self.assertRaisesRegex(ValueError, 'review'):
                store.sequence_baseline(root, 'iq-experts')
            retry = root/'retry'
            retry.mkdir()
            store.begin(root, retry, PROBES['gdn'], base)
            with self.assertRaisesRegex(ValueError, 'cleanup'):
                store.sequence_baseline(root, 'gdn')

    def test_tampered_result_and_each_state_mismatch_deny_retry(self):
        with retry_fixture() as (root, run, base, result, state):
            original = (run/'result.json').read_bytes()
            (run/'result.json').write_bytes(original + b' ')
            with self.assertRaisesRegex(ValueError, 'review'):
                store.sequence_baseline(root, 'gdn')
            (run/'result.json').write_bytes(original)
            for field, value in (('run', str(root/'other-run')), ('stage', 'iq-experts'),
                                 ('policy', 'other'), ('source', 'other'),
                                 ('binary', '0'*64), ('success', True),
                                 ('baseline', {})):
                changed = deepcopy(state)
                changed[field] = value
                store.atomic_json(root/'sequence.json', changed)
                with self.subTest(field=field):
                    with self.assertRaisesRegex(ValueError, 'review'):
                        store.sequence_baseline(root, 'gdn')
            store.atomic_json(root/'sequence.json', state)
            with patch.object(store, 'EVIDENCE', root/'other-root'):
                with self.assertRaisesRegex(ValueError, 'review'):
                    store.sequence_baseline(root, 'gdn')

    def test_unconfirmed_cleanup_and_wrong_failure_deny_even_with_mocked_hash(self):
        with retry_fixture() as (root, run, base, result, state):
            mutations = (
                ('cleanup_confirmed', False), ('owned_exit_confirmed', False),
                ('collector_terminal', False), ('recovery_samples', 4),
                ('exit_code', 1), ('failure', 'deadline'), ('success', True),
                ('numerical_pass', True),
            )
            for field, value in mutations:
                changed = deepcopy(result)
                changed[field] = value
                store.atomic_json(run/'result.json', changed)
                digest = hashlib.sha256((run/'result.json').read_bytes()).hexdigest().upper()
                with self.subTest(field=field), patch.object(store, 'REVIEWED_RESULT_SHA256', digest):
                    with self.assertRaisesRegex(ValueError, 'review'):
                        store.sequence_baseline(root, 'gdn')

    def test_second_failure_and_success_consume_retry(self):
        for success in (False, True):
            with self.subTest(success=success), retry_fixture() as (root, run, base, result, state):
                original = (run/'result.json').read_bytes()
                self.assertEqual(store.sequence_baseline(root, 'gdn'), base)
                retry = root/'retry'
                retry.mkdir()
                store.begin(root, retry, PROBES['gdn'], base)
                store.finish(root, retry, PROBES['gdn'], base,
                             {'success': success, 'cleanup_confirmed': True})
                self.assertEqual((run/'result.json').read_bytes(), original)
                self.assertEqual(store.read_json(root/'sequence.json')['run'], str(retry))
                with self.assertRaisesRegex(ValueError, 'review'):
                    store.sequence_baseline(root, 'gdn')
                if success:
                    self.assertEqual(store.sequence_baseline(root, 'iq-experts'), base)
                else:
                    with self.assertRaisesRegex(ValueError, 'review'):
                        store.sequence_baseline(root, 'iq-experts')


if __name__ == '__main__':
    unittest.main()
