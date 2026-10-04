"""Tiny CPU fixtures for the pinned HGNTUNE3 envelope, no kernels/models."""
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = (Path(__file__).resolve().parents[3] /
          'backends/halogen-wsl2-0.16.2/scripts/matmul_plan.py')


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = importlib.util.spec_from_file_location('halogen_matmul_plan', SCRIPT)
        cls.module = importlib.util.module_from_spec(cls.spec)
        if SCRIPT.exists():
            cls.spec.loader.exec_module(cls.module)

    def validate(self, path, **extra):
        self.assertTrue(hasattr(self.module, 'validate_plan'), 'Plan validator is missing')
        return self.module.validate_plan(path, expected_architecture='gfx1151', expected_wgp_count=20,
                                        expected_hipblaslt_version=70100, **extra)

    @staticmethod
    def fixture(*, magic=b'HGNTUNE3', count=1, version=70100, wgp=20,
                arch=b'gfx1151', records=1):
        return struct.pack('<8sIii32s', magic, count, version, wgp, arch) + b'\xff' * (64 * records)

    def test_valid_opaque_records_hash_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan'
            data = self.fixture()
            path.write_bytes(data)
            result = self.validate(path, expected_sha256=hashlib.sha256(data).hexdigest())
            self.assertEqual(result['header']['bucket_count'], 1)
            self.assertEqual(result['identity']['size'], 116)
            self.assertEqual(result['records_validation'], 'opaque_envelope_only')
            self.validate(path, expected_identity=result['identity'])

    def test_corrupt_headers_counts_and_mismatches_are_rejected(self):
        cases = [self.fixture(magic=b'HGNTUNE2'), self.fixture(count=0),
                 self.fixture(count=2), self.fixture(version=70101),
                 self.fixture(wgp=19), self.fixture(arch=b'gfx1150'),
                 self.fixture(arch=b'gfx1151\0X'), self.fixture(arch=b'A' * 32),
                 self.fixture()[:-1], self.fixture() + b'X', b'HGNTUNE3',
                 self.fixture(count=10000, records=0)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan'
            for data in cases:
                with self.subTest(size=len(data), head=data[:30]):
                    path.write_bytes(data)
                    with self.assertRaises(ValueError):
                        self.validate(path)

    def test_hash_identity_and_budget_refuse_unsealed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan'
            path.write_bytes(self.fixture())
            result = self.validate(path)
            with self.assertRaises(ValueError):
                self.validate(path, expected_sha256='0' * 64)
            with self.assertRaises(ValueError):
                self.validate(path, expected_identity=dict(result['identity'], size=115))
            with self.assertRaises(ValueError):
                self.validate(path, max_bytes=100)
            with self.assertRaises(ValueError):
                self.validate(path, frozen=True)

    def test_frozen_readonly_seal_and_native_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan'
            data = self.fixture()
            path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            with self.assertRaises(ValueError):
                self.validate(path, frozen=True, expected_sha256=digest)
            path.chmod(0o444)
            try:
                self.assertTrue(self.validate(path, frozen=True, expected_sha256=digest)['readonly_metadata'])
                log = Path(directory) / 'engine.log'
                for warning in ('absent, will be written at exit', 'cannot write',
                                'unreadable or an older format, ignored', 'TUNED ELSEWHERE',
                                'tuned on a 19-WGP part (38 CUs), this one has 20 WGPs'):
                    log.write_text('hipBLASLt tuning file /tmp/plan: ' + warning)
                    with self.assertRaises(ValueError):
                        self.validate(path, frozen=True, expected_sha256=digest, log_paths=[log])
                log.write_text('normal ready\n')
                self.validate(path, frozen=True, expected_sha256=digest, log_paths=[log])
            finally:
                path.chmod(0o644)

    def test_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'plan'
            source.write_bytes(self.fixture())
            linked = Path(directory) / 'link'
            try:
                os.symlink(source, linked)
            except OSError:
                self.skipTest('Host cannot create a symlink')
            with self.assertRaises(ValueError):
                self.validate(linked)

    def test_real_file_growth_during_read_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan'
            path.write_bytes(self.fixture())
            real_fstat = os.fstat
            calls = 0

            def grow_before_second_stat(fd):
                nonlocal calls
                calls += 1
                if calls == 2:
                    with path.open('ab') as output:
                        output.write(b'X')
                return real_fstat(fd)

            with patch.object(self.module.os, 'fstat', side_effect=grow_before_second_stat):
                with self.assertRaisesRegex(ValueError, 'growing or changed'):
                    self.validate(path)


if __name__ == '__main__':
    unittest.main()
