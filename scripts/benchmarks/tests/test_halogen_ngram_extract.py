"""Small CPU HGN fixtures; never read or extract a real checkpoint."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'halogen_ngram_extract.py'


class NgramExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('halogen_ngram_extract', SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def fixture(self, root, *, checksum_delta=0, dimensions=(1, 3, 9), storage=10,
                duplicate=False, invalid_extent=False):
        m = self.module
        payload = bytes(range(31))  # 27 FP8 entries and the four-byte scale.
        checksum = 0
        padded = payload + b'\0' * (-len(payload) % 4)
        for word, in struct.iter_unpack('<I', padded):
            checksum ^= word
        count = 3 if duplicate else 2
        data_offset = (104 + 160 * count + 63) // 64 * 64
        file_size = data_offset + 128
        header = struct.pack('<IIQQQQ', 0x314e4748, 2, count, 104, data_offset, file_size)
        header += b'fixture-model' + b'\0' * (64 - len(b'fixture-model'))
        entry = bytearray(160)
        name = m.TENSOR_NAME.encode()
        entry[:len(name)] = name
        struct.pack_into('<II4qQQII', entry, 96, storage, 3, *dimensions, 0,
                         file_size if invalid_extent else data_offset, len(payload),
                         checksum ^ checksum_delta, 0)
        other = bytearray(160)
        other[:11] = b'model.other'
        struct.pack_into('<II4qQQII', other, 96, 0, 1, 8, 0, 0, 0,
                         data_offset + 64, 32, 0, 0)
        contents = bytearray(file_size)
        contents[:104] = header
        contents[104:264] = entry
        contents[264:424] = entry if duplicate else other
        if duplicate:
            contents[424:584] = other
        contents[data_offset:data_offset + len(payload)] = payload
        contents[data_offset + 64:data_offset + 96] = b'X' * 32
        source = root / 'source.hgn'
        source.write_bytes(contents)
        receipt = {'sha256': hashlib.sha256(contents).hexdigest(),
                   'identity': m.file_identity(m._path_stat(source))}
        expected = m.ExtractionSpec(receipt['sha256'], file_size, (1, 3, 9), 31, count)
        return source, receipt, expected, bytes(entry), payload

    def extract(self, source, destination, receipt, expected, **kwargs):
        return self.module.extract_ngram(source, destination, source_receipt=receipt,
                                         expected=expected, verify_xor=True, **kwargs)

    def test_preserves_single_record_and_payload_with_bounded_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, original, payload = self.fixture(root)
            destination = root / 'ngram.hgn'
            result = self.extract(source, destination, receipt, expected, chunk_bytes=8,
                                  flush_bytes=16)
            output = destination.read_bytes()
            self.assertEqual(struct.unpack_from('<IIQQQQ', output),
                             (0x314e4748, 2, 1, 104, 320, 384))
            self.assertEqual(output[40:104], source.read_bytes()[40:104])
            adapted = bytearray(original)
            struct.pack_into('<Q', adapted, 136, 320)
            self.assertEqual(output[104:264], adapted)
            self.assertEqual(output[320:351], payload)
            self.assertEqual(output[264:320], b'\0' * 56)
            self.assertEqual(output[351:], b'\0' * 33)
            self.assertEqual(result['output']['sha256'], hashlib.sha256(output).hexdigest())
            self.assertEqual(result['tensor']['sha256'], hashlib.sha256(payload).hexdigest())
            self.assertTrue(result['tensor']['xor32_verified'])
            self.assertEqual(json.loads(destination.with_suffix('.hgn.receipt.json').read_text()), result)

    def test_refuses_existing_output_or_same_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, _, _ = self.fixture(root)
            destination = root / 'ngram.hgn'
            destination.write_bytes(b'keep')
            for target in (destination, source):
                with self.assertRaises((ValueError, FileExistsError)):
                    self.extract(source, target, receipt, expected)
            self.assertEqual(destination.read_bytes(), b'keep')

    def test_sparse_stub_and_truncated_source_are_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, _, _ = self.fixture(root)
            source.write_bytes(b'\0' * expected.source_bytes)
            receipt['identity'] = self.module.file_identity(self.module._path_stat(source))
            with self.assertRaisesRegex(ValueError, 'header'):
                self.extract(source, root / 'ngram.hgn', receipt, expected)
            source.write_bytes(source.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'identity|size'):
                self.extract(source, root / 'ngram.hgn', receipt, expected)
            self.assertFalse((root / 'ngram.hgn').exists())

    def test_shape_storage_duplicate_and_extent_checks(self):
        for changes in ({'dimensions': (1, 3, 8)}, {'storage': 7}, {'duplicate': True},
                        {'invalid_extent': True}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, receipt, expected, _, _ = self.fixture(root, **changes)
                with self.assertRaises(ValueError):
                    self.extract(source, root / 'ngram.hgn', receipt, expected)
                self.assertFalse((root / 'ngram.hgn').exists())

    def test_bad_payload_checksum_removes_created_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, _, _ = self.fixture(root, checksum_delta=1)
            destination = root / 'ngram.hgn'
            with self.assertRaisesRegex(ValueError, 'XOR32'):
                self.extract(source, destination, receipt, expected)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix('.hgn.receipt.json').exists())

    def test_concurrent_payload_truncation_cleans_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, _, _ = self.fixture(root)
            inspect = self.module._inspect
            def truncate_after_metadata(stream, spec):
                result = inspect(stream, spec)
                os.truncate(source, result[1]['offset'] + result[1]['size'] - 1)
                return result
            with patch.object(self.module, '_inspect', side_effect=truncate_after_metadata):
                with self.assertRaisesRegex(ValueError, 'Truncated'):
                    self.extract(source, root / 'ngram.hgn', receipt, expected, chunk_bytes=8)
            self.assertFalse((root / 'ngram.hgn').exists())

    def test_existing_receipt_is_preserved_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, _, _ = self.fixture(root)
            destination = root / 'ngram.hgn'
            retained = destination.with_suffix('.hgn.receipt.json')
            retained.write_text('keep')
            with self.assertRaises(FileExistsError):
                self.extract(source, destination, receipt, expected)
            self.assertEqual(retained.read_text(), 'keep')
            self.assertFalse(destination.exists())

    def test_same_size_output_mutation_before_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, _, _ = self.fixture(root)
            destination = root / 'ngram.hgn'
            path_stat = self.module._path_stat
            def replace_output(path):
                if path == destination:
                    identity = path.stat()
                    with path.open('r+b') as stream:
                        stream.seek(320)
                        stream.write(b'Z')
                    os.utime(path, ns=(identity.st_atime_ns, identity.st_mtime_ns + 1000000000))
                return path_stat(path)
            with patch.object(self.module, '_path_stat', side_effect=replace_output):
                with self.assertRaisesRegex(ValueError, 'Output changed'):
                    self.extract(source, destination, receipt, expected)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix('.hgn.receipt.json').exists())

    def test_source_receipt_and_identity_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, _, _ = self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'receipt'):
                self.extract(source, root / 'ngram.hgn', {**receipt, 'sha256': '0' * 64}, expected)
            identity = self.module.file_identity
            calls = 0
            def drift(stat):
                nonlocal calls
                calls += 1
                return {**identity(stat), 'mtime_ns': identity(stat)['mtime_ns'] + (calls > 1)}
            with patch.object(self.module, 'file_identity', side_effect=drift):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    self.extract(source, root / 'ngram.hgn', receipt, expected)
            self.assertFalse((root / 'ngram.hgn').exists())

    def test_symlink_input_and_parent_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, receipt, expected, _, _ = self.fixture(root)
            link = root / 'source-link.hgn'
            try:
                link.symlink_to(source)
                parent = root / 'linked-parent'
                parent.symlink_to(root, target_is_directory=True)
            except OSError:
                self.skipTest('Host does not permit test symlink creation')
            for input_path, output_path in ((link, root / 'ngram.hgn'),
                                             (source, parent / 'ngram.hgn')):
                with self.assertRaisesRegex(ValueError, 'link|reparse'):
                    self.extract(input_path, output_path, receipt, expected)

    def test_real_expected_output_size_is_fixed_without_reading_payload(self):
        m = self.module
        self.assertEqual(m.align64(m.DATA_OFFSET + m.TABLE_BYTES), 51200246144)


if __name__ == '__main__':
    unittest.main()
