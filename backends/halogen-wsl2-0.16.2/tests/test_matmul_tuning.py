"""Small offline checks for isolated experimental plan forwarding and admission."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_alloy_matmul_tuning', ROOT / 'scripts/matmul_tuning.py')
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)


class MatmulTuningTests(unittest.TestCase):
    def test_omitted_control_does_not_override_stock(self):
        self.assertEqual(mt.environment(None), {})
        self.assertIsNone(mt.receipt(None))

    def test_training_is_fixed_container_local_and_not_a_speed_result(self):
        self.assertEqual(mt.environment({'mode': 'train'}), {
            'HALOGEN_MATMUL_ALGOS': '8', 'HALOGEN_MATMUL_TUNING_FILE': '/tmp/strix-alloy-matmul.plan'})
        self.assertFalse(mt.receipt({'mode': 'train'})['timing_qualified'])
        for value in ({'mode': 'train', 'path': '/models/model.hgn'},
                      {'mode': 'train', 'algorithms': 64}, {'mode': 'unknown'}, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mt.validate(value)

    def test_duplicate_keys_and_incomplete_frozen_controls_refused(self):
        for text in ('{"mode":"train","mode":"frozen"}', '[]', 'null',
                     '{"mode":"frozen","path":"C:/tmp/plan"}', 'x' * 2049):
            with self.subTest(text=text[:80]), self.assertRaises(ValueError):
                mt.parse(text)

    def test_launch_recheck_refuses_replaced_seal_and_native_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'frozen.plan'
            data = struct.pack('<8sIii32s', b'HGNTUNE3', 1, 100401, 20, b'gfx1151') + bytes(64)
            path.write_bytes(data)
            path.chmod(0o444)
            try:
                with patch.object(mt, 'PLAN_ROOT', root):
                    seal = mt.receipt({'mode': 'frozen', 'path': str(path),
                        'sha256': hashlib.sha256(data).hexdigest(), 'hipblaslt_version': 100401,
                        'wgp_count': 20})
                    mt.revalidate_receipt(seal, 'hipBLASLt tuning file: loaded\n')
                    with self.assertRaisesRegex(ValueError, 'refused by native'):
                        mt.revalidate_receipt(seal, 'hipBLASLt tuning file: tuned elsewhere, ignored')
                    info = path.stat()
                    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000))
                    with self.assertRaisesRegex(ValueError, 'identity'):
                        mt.revalidate_receipt(seal)
            finally:
                path.chmod(0o644)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell launcher forwarding')
    def test_launcher_passes_one_json_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'Start.ps1', root / 'Start.ps1')
            (root / 'scripts/service.py').write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            config = '{"mode":"train"}'
            result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-File', str(root / 'Start.ps1'),
                '-Checkpoint', 'v2', '-MatmulTuningJson', config, '-PrintOnly'],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = json.loads(result.stdout)
            self.assertEqual(args[args.index('--matmul-tuning-json') + 1], config)
            self.assertIn('--print-only', args)


if __name__ == '__main__':
    unittest.main()
