"""Offline receipt binding and real launcher forwarding; no model payload reads."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class LookupSourceTests(unittest.TestCase):
    def module(self):
        specification = importlib.util.find_spec('lookup_source')
        self.assertIsNotNone(specification, 'Standalone lookup qualification support is missing')
        import lookup_source
        return lookup_source

    def test_skewed_host_clock_is_ignored_but_frozen_progress_and_deadline_refused(self):
        lookup = self.module()
        tracker = getattr(lookup, 'ProgressGuard', None)
        self.assertIsNotNone(tracker, 'Qualification requires a guest monotonic progress guard')
        record = dict(schema=1, run_id='qualification', sequence=10, time=1000.0,
                      frame=dict(available_bytes=18 * 1024**3, commit_headroom_bytes=18 * 1024**3))
        with patch.object(lookup.time, 'time', return_value=1035.0):
            guard = tracker('qualification', now=4000.0)
            self.assertFalse(guard.observe(record, now=4000.0))
            self.assertTrue(guard.observe({**record, 'sequence': 11}, now=4000.2))
            self.assertTrue(guard.observe({**record, 'sequence': 11}, now=4001.0))
            with self.assertRaisesRegex(ValueError, 'progress'):
                guard.observe({**record, 'sequence': 11}, now=4002.3)
            guard = tracker('qualification', now=0.0)
            guard.observe(record, now=0.0)
            with self.assertRaisesRegex(ValueError, 'deadline'):
                guard.observe({**record, 'sequence': 12}, now=600.0)

    def test_untrusted_or_malformed_receipt_cannot_authorize_lookup(self):
        lookup = self.module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = root / 'lookup.json'
            receipt.write_bytes(b'{"schema":1,"source":{},"tensor":{},"output":{}}')
            with patch.object(lookup, 'RECEIPT_ROOTS', (root,)):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    lookup.read_receipt({'receipt': str(receipt), 'receipt_sha256': '0' * 64})
                digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):
                    lookup.read_receipt({'receipt': str(receipt), 'receipt_sha256': digest})
                with self.assertRaises(ValueError):
                    lookup.validate_configuration({'receipt': str(receipt), 'receipt_sha256': digest,
                                                   'source': '/models/other.hgn'})

    def test_service_rejects_partial_binding_and_non_v2_use(self):
        self.module()
        import service
        for arguments in (['--lookup-receipt', 'C:/lookup.json'],
                          ['--lookup-receipt-sha256', '0' * 64],
                          ['--lookup-receipt', 'C:/lookup.json', '--lookup-receipt-sha256', '0' * 64]):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                service.options(arguments)

    def test_pinned_extraction_for_other_original_source_is_refused_before_wsl(self):
        lookup = self.module()
        import portable
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt_path = root / 'lookup.json'
            source_identity = dict(size=124068083904, device=71, inode=1234, mtime_ns=5, ctime_ns=6)
            output_identity = dict(size=51200246144, device=1792, inode=18, mtime_ns=7, ctime_ns=8)
            receipt = dict(schema=1, chunk_bytes=8388608,
                source=dict(path='/mnt/c/reviewed-w4b.hgn',
                    sha256='9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6',
                    identity=source_identity, header_sha256='1' * 64),
                tensor=dict(name='layers.1.ple.ngram_embedding.weight', storage=10,
                    dimensions=[128,2500012,160], variant=0, source_offset=1882122624,
                    bytes=51200245764, sha256='2' * 64, xor32='f682e517', xor32_verified=True),
                output=dict(path='/home/revn/lookup.hgn', bytes=51200246144, sha256='3' * 64,
                    identity=output_identity, data_offset=320))
            receipt_path.write_text(json.dumps(receipt))
            configuration = dict(receipt=str(receipt_path),
                receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())
            with patch.object(lookup, 'RECEIPT_ROOTS', (root,)), patch.object(portable, 'wsl',
                    side_effect=AssertionError('Refused source must never reach WSL')):
                with self.assertRaisesRegex(ValueError, 'differs from the installed'):
                    lookup.qualify(dict(ngram_source='/mnt/c/another-w4b.hgn'), root, configuration)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell launcher forwarding')
    def test_real_launcher_preserves_receipt_path_as_one_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'Start.ps1', root / 'Start.ps1')
            (root / 'scripts/service.py').write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            receipt = str(root / 'lookup receipt.json')
            result = subprocess.run([shutil.which('pwsh'), '-NoProfile', '-File', str(root / 'Start.ps1'),
                '-Checkpoint', 'v2', '-LookupReceipt', receipt, '-LookupReceiptSha256', 'a' * 64,
                '-PrintOnly'], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = json.loads(result.stdout)
            self.assertEqual(arguments[arguments.index('--lookup-receipt') + 1], receipt)
            self.assertEqual(arguments[arguments.index('--lookup-receipt-sha256') + 1], 'a' * 64)


if __name__ == '__main__':
    unittest.main()
