import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gufo_control.gguf import GgufError, inspect_gguf


def string(value):
    data = value.encode('utf-8') if isinstance(value, str) else value
    return struct.pack('<Q', len(data)) + data


def meta(key, kind, value):
    return string(key) + struct.pack('<I', kind) + value


def tensor(name='weight', dimensions=(4, 4), kind=0, offset=0):
    return (string(name) + struct.pack('<I', len(dimensions))
            + b''.join(struct.pack('<Q', d) for d in dimensions)
            + struct.pack('<IQ', kind, offset))


def fixture(metadata=None, tensors=None, payload=64, padding=True):
    if metadata is None:
        metadata = [meta('general.architecture', 8, string('qwen4exp'))]
    if tensors is None:
        tensors = [tensor()]
    descriptor = (b'GGUF' + struct.pack('<IQQ', 3, len(tensors), len(metadata))
                  + b''.join(metadata) + b''.join(tensors))
    aligned = (len(descriptor) + 31) // 32 * 32
    return descriptor + (bytes(aligned - len(descriptor)) if padding else b'') + bytes(payload), len(descriptor)


class GgufTests(unittest.TestCase):
    def inspect(self, data):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'tiny.gguf'
            path.write_bytes(data)
            return inspect_gguf(path)

    def rejects(self, data):
        with self.assertRaises(GgufError):
            self.inspect(data)

    def test_valid_descriptor_and_extent(self):
        data, end = fixture()
        report = self.inspect(data)
        self.assertEqual(report['metadata']['general.architecture'], 'qwen4exp')
        self.assertEqual(report['tensors'][0]['size_bytes'], 64)
        self.assertEqual(report['descriptor_end'], end)
        self.assertEqual(report['size_bytes'], report['data_offset'] + 64)
        self.assertEqual(report['version'], 3)
        self.assertTrue(Path(report['path']).is_absolute())
        self.assertIsInstance(report['mtime_ns'], int)

    def test_string_array_is_summarized(self):
        entry = meta('tokenizer.ggml.tokens', 9, struct.pack('<IQ', 8, 2) + string('hello') + string('world'))
        report = self.inspect(fixture(metadata=[entry])[0])
        self.assertEqual(report['metadata']['tokenizer.ggml.tokens'], {'array_type': 8, 'count': 2})

    def test_truncated_tensor_payload_extent_rejected(self):
        self.rejects(fixture(payload=0)[0])

    def test_duplicate_metadata_rejected(self):
        self.rejects(fixture(metadata=[meta('a', 8, string('x'))] * 2)[0])

    def test_bad_magic_and_version(self):
        valid = fixture()[0]
        for data in (b'NOPE' + valid[4:], valid[:4] + struct.pack('<I', 4) + valid[8:]):
            with self.subTest(data=data[:8]):
                self.rejects(data)

    def test_truncated_header(self):
        valid = fixture()[0]
        for length in (0, 3, 7, 23, 40):
            with self.subTest(length=length):
                self.rejects(valid[:length])

    def test_oversized_metadata_count(self):
        self.rejects(b'GGUF' + struct.pack('<IQQ', 3, 0, 100001))

    def test_invalid_alignment(self):
        for kind, value in ((4, struct.pack('<I', 3)), (8, string('32')), (4, struct.pack('<I', 1 << 21))):
            with self.subTest(kind=kind, value=value):
                self.rejects(fixture(metadata=[meta('general.alignment', kind, value)])[0])

    def test_unsupported_metadata_types(self):
        for value in (meta('x', 13, b''), meta('x', 9, struct.pack('<IQ', 9, 0)),
                      meta('x', 9, struct.pack('<IQ', 13, 0))):
            with self.subTest(value=value):
                self.rejects(fixture(metadata=[value])[0])

    def test_unsupported_tensor_type(self):
        self.rejects(fixture(tensors=[tensor(kind=999)])[0])

    def test_excessive_lengths(self):
        for entry in (struct.pack('<Q', 65537),
                      meta('x', 8, struct.pack('<Q', (4 << 20) + 1)),
                      meta('x', 9, struct.pack('<IQ', 8, 1000001))):
            with self.subTest(entry=entry[:16]):
                self.rejects(fixture(metadata=[entry])[0])

    def test_invalid_utf8_and_boolean(self):
        for entry in (meta('x', 8, string(b'\xff')), meta('x', 7, b'\x02')):
            with self.subTest(entry=entry):
                self.rejects(fixture(metadata=[entry])[0])

    def test_bad_tensor_shapes_and_names(self):
        for tensors in ([tensor(dimensions=(0, 4))], [tensor(dimensions=(31, 4), kind=2)],
                        [tensor(), tensor()], [tensor(dimensions=(1 << 63, 2))]):
            with self.subTest(tensors=tensors):
                self.rejects(fixture(tensors=tensors)[0])

    def test_overlap(self):
        self.rejects(fixture(tensors=[tensor('a'), tensor('b', offset=32)], payload=128)[0])

    def test_metadata_only_shard(self):
        report = self.inspect(fixture(metadata=[meta('split.no', 4, struct.pack('<I', 0))], tensors=[], payload=0)[0])
        self.assertEqual(report['tensors'], [])
        self.assertEqual(report['metadata']['split.no'], 0)

    def test_never_reads_payload(self):
        data, descriptor_end = fixture()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'tiny.gguf'
            path.write_bytes(data)
            original_open = Path.open
            reads = []

            class Wrapped:
                def __init__(self, stream):
                    self.stream = stream
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    self.stream.close()
                def read(self, count):
                    start = self.stream.tell()
                    reads.append((start, count))
                    if start + count > descriptor_end:
                        raise AssertionError('payload read')
                    return self.stream.read(count)
                def __getattr__(self, name):
                    return getattr(self.stream, name)

            def wrapped_open(candidate, *args, **kwargs):
                return Wrapped(original_open(candidate, *args, **kwargs))

            with patch.object(Path, 'open', wrapped_open):
                inspect_gguf(path)
            self.assertTrue(reads)
            self.assertLessEqual(max(start + count for start, count in reads), descriptor_end)

    def test_file_change_detected(self):
        data, _ = fixture()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'tiny.gguf'
            path.write_bytes(data)
            original_fstat = __import__('os').fstat
            calls = 0
            def changed(fd):
                nonlocal calls
                calls += 1
                stat = original_fstat(fd)
                if calls == 2:
                    class Changed:
                        st_size = stat.st_size
                        st_mtime_ns = stat.st_mtime_ns + 1
                    return Changed()
                return stat
            with patch('gufo_control.gguf.os.fstat', side_effect=changed):
                with self.assertRaises(GgufError):
                    inspect_gguf(path)


if __name__ == '__main__':
    unittest.main()
