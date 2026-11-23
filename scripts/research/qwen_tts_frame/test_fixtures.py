"""Check the native dump pairing for the first two acoustic frames."""

from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from . import fixtures


def write_dump(path, values):
    values = np.asarray(values, dtype='<f4')
    shape = struct.pack(f'<{values.ndim + 1}i', values.ndim, *values.shape)
    path.write_bytes(shape + values.tobytes())


class NativeFrameFixtures(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.prefill = np.arange(2048, dtype=np.float32).reshape(2, 1024)
        self.step_one_hidden = -np.arange(1024, dtype=np.float32) - np.float32(0.125)
        self.codes = np.arange(48, dtype=np.float32).reshape(3, 16)
        self.hidden_path = self.directory / 'talker-hidden-step1.bin'
        self.full_codes_path = self.directory / 'codes-full.bin'
        write_dump(self.directory / 'talker-hidden-prefill-final.bin', self.prefill)
        write_dump(self.directory / 'codes-step0.bin', self.codes[0])
        write_dump(self.hidden_path, self.step_one_hidden)
        write_dump(self.full_codes_path, self.codes)

    def test_selects_explicit_hidden_and_corresponding_code_row(self):
        for index, expected_hidden in ((0, self.prefill[-1]), (1, self.step_one_hidden)):
            with self.subTest(index=index):
                hidden, codes = fixtures.load_native_frame(self.directory, index)
                self.assertEqual(hidden.dtype, np.dtype('float32'))
                self.assertEqual(codes.dtype, np.dtype('int32'))
                np.testing.assert_array_equal(hidden, expected_hidden)
                np.testing.assert_array_equal(codes, self.codes[index])

    def test_rejects_indices_without_a_matching_native_hidden_dump(self):
        for index in (-1, 2, 3):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'frame index'):
                fixtures.load_native_frame(self.directory, index)
        with self.assertRaises(TypeError):
            fixtures.load_native_frame(self.directory, 1.0)

    def test_rejects_full_codes_from_an_inconsistent_capture(self):
        self.codes[0, 1] = 2047
        write_dump(self.full_codes_path, self.codes)
        with self.assertRaisesRegex(ValueError, 'first row.*codes-step0.bin'):
            fixtures.load_native_frame(self.directory, 1)

    def test_rejects_missing_or_malformed_code_rows(self):
        for malformed in (self.codes[:1], self.codes[:, :-1], self.codes[0]):
            with self.subTest(shape=malformed.shape):
                write_dump(self.full_codes_path, malformed)
                with self.assertRaisesRegex(ValueError, 'codes-full.bin'):
                    fixtures.load_native_frame(self.directory, 1)

        write_dump(self.full_codes_path, self.codes)
        data = self.full_codes_path.read_bytes()
        self.full_codes_path.write_bytes(data[:-1])
        with self.assertRaisesRegex(ValueError, 'file length'):
            fixtures.load_native_frame(self.directory, 1)

    def test_rejects_nonfinite_hidden_and_invalid_ids(self):
        self.step_one_hidden[0] = np.inf
        write_dump(self.hidden_path, self.step_one_hidden)
        with self.assertRaisesRegex(ValueError, 'nonfinite bridge value'):
            fixtures.load_native_frame(self.directory, 1)

        self.step_one_hidden[0] = 0.0
        write_dump(self.hidden_path, self.step_one_hidden)
        for invalid in (float('nan'), -1, 2048, 12.5):
            with self.subTest(invalid=invalid):
                self.codes[1, 0] = invalid
                write_dump(self.full_codes_path, self.codes)
                with self.assertRaisesRegex(ValueError, 'expected integer codec IDs'):
                    fixtures.load_native_frame(self.directory, 1)

    def test_reads_native_logits_in_codebook_order_and_checks_the_code_row(self):
        index = 1
        _, codes = fixtures.load_native_frame(self.directory, index)
        code_path = self.directory / 'codes-step1.bin'
        write_dump(code_path, codes)
        expected = np.arange(15 * 2048, dtype='<f4').reshape(15, 2048)
        logits_path = self.directory / 'codepred-logits-step1.bin'
        raw = struct.pack('<iii', 2, 2048, 15) + expected.tobytes()
        logits_path.write_bytes(raw)
        np.testing.assert_array_equal(fixtures.load_native_logits(self.directory, index, codes), expected)

        logits_path.write_bytes(raw[:-1])
        with self.assertRaisesRegex(ValueError, 'shape or size'):
            fixtures.load_native_logits(self.directory, index, codes)

        write_dump(code_path, np.zeros_like(codes))
        with self.assertRaisesRegex(ValueError, 'do not match'):
            fixtures.load_native_logits(self.directory, index, codes)


if __name__ == '__main__':
    unittest.main()
