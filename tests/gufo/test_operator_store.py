import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import operator_store as store
from gufo_control.operator_policy import Baseline, PROBES


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
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'x'
            path.write_bytes(b'a')
            manifest = {'artifacts': [{'stamp': store.stamp(path)}]}
            path.write_bytes(b'ab')
            with patch.object(store, 'source_identity'), patch.object(store, 'BUILD', Path(folder)):
                with self.assertRaisesRegex(ValueError, 'artifact_changed'):
                    store.recheck(manifest)

    def test_binary_hash_and_shadow(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'bin').mkdir()
            (root/'lib/llvm/bin').mkdir(parents=True)
            (root/'lib/llvm/amdgcn/bitcode').mkdir(parents=True)
            for name in store.DLLS:
                (root/'bin'/name).write_bytes(b'dll')
            (root/PROBES['gdn'].filename).write_bytes(b'wrong')
            with patch.object(store, 'SOURCE', root), patch.object(store, 'BUILD', root), \
                 patch.object(store, 'SDK', root), patch.object(store, 'source_identity'):
                with self.assertRaisesRegex(ValueError, 'binary_hash'):
                    store.verify(PROBES['gdn'])
                (root/store.DLLS[0]).write_bytes(b'shadow')
                with self.assertRaisesRegex(ValueError, 'shadow'):
                    store.verify(PROBES['gdn'])

    @unittest.skipUnless(os.name == 'nt', 'Windows file lock')
    def test_lock_and_release(self):
        with tempfile.TemporaryDirectory() as folder:
            with store.exclusive(folder):
                with self.assertRaises(RuntimeError):
                    with store.exclusive(folder):
                        self.fail('second owner acquired lock')
            with store.exclusive(folder):
                pass


if __name__ == '__main__':
    unittest.main()
