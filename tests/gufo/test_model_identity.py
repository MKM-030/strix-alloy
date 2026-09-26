import hashlib
import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gufo_control.model_identity import (
    ModelIdentityError, ProfilePins, ShardPin, validate_ar4k_model,
)


def s(value):
    data = value.encode()
    return struct.pack('<Q', len(data)) + data


def m(key, kind, value):
    return s(key) + struct.pack('<I', kind) + value


def u(key, value):
    return m(key, 4, struct.pack('<I', value))


def arr(key, values):
    return m(key, 9, struct.pack('<IQ', 4, len(values))
             + b''.join(struct.pack('<I', x) for x in values))


def gguf(metadata, tensor_count):
    tensors = b''.join(s('w' + str(i)) + struct.pack('<I', 2)
                       + struct.pack('<QQIQ', 4, 4, 0, i * 64)
                       for i in range(tensor_count))
    descriptor = (b'GGUF' + struct.pack('<IQQ', 3, tensor_count, len(metadata))
                  + b''.join(metadata) + tensors)
    padded = (len(descriptor) + 31) // 32 * 32
    return descriptor + bytes(padded - len(descriptor)) + bytes(64 * tensor_count), len(descriptor)


class ModelIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'models'
        self.root.mkdir()
        files = (
            gguf([m('general.architecture', 8, s('qwen4exp')),
                  u('split.no', 0), u('split.count', 3),
                  u('split.tensors.count', 2), arr('geometry', [4, 4])], 0),
            gguf([u('split.no', 1), u('split.count', 3),
                  u('split.tensors.count', 2)], 1),
            gguf([u('split.no', 2), u('split.count', 3),
                  u('split.tensors.count', 2)], 1),
        )
        pins = []
        for index, (data, end) in enumerate(files):
            name = f'shard-{index + 1}.gguf'
            (self.root / name).write_bytes(data)
            pins.append(ShardPin(name, len(data), end,
                                 hashlib.sha256(data[:end]).hexdigest(),
                                 0 if index == 0 else 1, index))
        self.pins = ProfilePins('test-revision', tuple(pins),
                                {'general.architecture': 'qwen4exp'},
                                {'geometry': (4, 4)})
        self.first = self.root / 'shard-1.gguf'

    def validate(self, pins=None):
        return validate_ar4k_model(self.first, pins=pins or self.pins)

    def rewrite_shard(self, index, metadata, tensor_count):
        data, end = gguf(metadata, tensor_count)
        pin = self.pins.shards[index]
        (self.root / pin.filename).write_bytes(data)
        changed = list(self.pins.shards)
        changed[index] = replace(
            pin, size_bytes=len(data), descriptor_end=end,
            descriptor_sha256=hashlib.sha256(data[:end]).hexdigest(),
            tensor_count=tensor_count)
        return replace(self.pins, shards=tuple(changed))

    def test_accepts_zero_tensor_first_shard_and_returns_only_target(self):
        result = self.validate()
        self.assertEqual(result.first_shard, self.first.resolve())
        self.assertEqual(result.revision, 'test-revision')
        self.assertEqual(result.context_capacity, 4096)
        self.assertEqual(result.sessions, 1)
        self.assertFalse(result.mtp_enabled)

    def test_rejects_size_and_descriptor_changes_on_each_shard(self):
        for index, pin in enumerate(self.pins.shards):
            with self.subTest(index=index, mismatch='size'):
                changed = list(self.pins.shards)
                changed[index] = replace(pin, size_bytes=pin.size_bytes + 1)
                with self.assertRaises(ModelIdentityError):
                    self.validate(replace(self.pins, shards=tuple(changed)))
            with self.subTest(index=index, mismatch='descriptor'):
                changed = list(self.pins.shards)
                changed[index] = replace(pin, descriptor_sha256='0' * 64)
                with self.assertRaises(ModelIdentityError):
                    self.validate(replace(self.pins, shards=tuple(changed)))

    def test_rejects_missing_or_wrong_split_and_tensor_count(self):
        wrong = list(self.pins.shards)
        wrong[0] = replace(wrong[0], tensor_count=1)
        with self.assertRaises(ModelIdentityError):
            self.validate(replace(self.pins, shards=tuple(wrong)))
        (self.root / 'shard-3.gguf').unlink()
        with self.assertRaises(ModelIdentityError):
            self.validate()

    def test_rejects_wrong_split_metadata_with_matching_descriptor_pin(self):
        for key, value in (('split.no', 0), ('split.count', 4),
                           ('split.tensors.count', 3)):
            with self.subTest(key=key):
                metadata = {'split.no': 1, 'split.count': 3,
                            'split.tensors.count': 2}
                metadata[key] = value
                pins = self.rewrite_shard(1, [u(k, v) for k, v in metadata.items()], 1)
                with self.assertRaises(ModelIdentityError):
                    self.validate(pins)

    def test_rejects_nextn_flag_with_matching_descriptor_pin(self):
        metadata = [m('general.architecture', 8, s('qwen4exp')),
                    u('split.no', 0), u('split.count', 3),
                    u('split.tensors.count', 2), arr('geometry', [4, 4]),
                    m('qwen4exp.nextn_shared_target_tensors', 7, b'\x01')]
        pins = self.rewrite_shard(0, metadata, 0)
        with self.assertRaises(ModelIdentityError):
            self.validate(pins)

    def test_rejects_wrong_geometry_even_when_pins_are_updated(self):
        with self.assertRaises(ModelIdentityError):
            self.validate(replace(self.pins, arrays={'geometry': (4, 0)}))

    def test_rejects_projector_in_model_directory_and_parent(self):
        for directory in (self.root, self.root.parent):
            with self.subTest(directory=directory):
                projector = directory / 'mmproj-BF16.gguf'
                projector.write_bytes(b'')
                try:
                    with self.assertRaises(ModelIdentityError):
                        self.validate()
                finally:
                    projector.unlink()

    def test_rejects_wrong_first_path_and_sidecar_substitution(self):
        with self.assertRaises(ModelIdentityError):
            validate_ar4k_model(self.root / 'shard-2.gguf', pins=self.pins)
        bad = list(self.pins.shards)
        # A sidecar cannot be substituted for any of the three declared shards.
        bad[2] = replace(bad[2], filename='mtp.gguf')
        with self.assertRaises(ModelIdentityError):
            self.validate(replace(self.pins, shards=tuple(bad)))


if __name__ == '__main__':
    unittest.main()
