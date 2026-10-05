"""Three synthetic layout proofs; no compiler/runtime/model imports."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np


class VectorPackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("pack.py")
        spec = importlib.util.spec_from_file_location("vector_hidden_pack", source)
        cls.pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.pack)
        indices = np.arange(2560 * 2560, dtype=np.uint32).reshape(2560, 2560)
        # Coprime row/column multipliers distinguish every row/column at zero
        # of the other axis, including column/group/worker outer-layout edges.
        row, col = indices // 2560, indices % 2560
        cls.words = (((row * 13 ^ col * 73) & 0x3FFF) | ((row & 1) << 15)).astype("<u2")
        cls.words[0, 0] = 0x8000

    def test_full_inverse_preserves_words_and_prepared_source_layout(self):
        packed = self.pack.pack_decoded(self.words)
        self.assertEqual(len(packed), 13107200)
        self.assertEqual(self.pack.unpack_decoded(packed).tobytes(), self.words.tobytes())
        # Construct the old payload independently, without the vector packer.
        original = self.words.reshape(8, 5, 4, 16, 10, 256).transpose(0, 1, 4, 2, 3, 5)
        self.assertEqual(self.pack.unpack_source_decoded(original.tobytes()).tobytes(), self.words.tobytes())
        with self.assertRaises(ValueError):
            self.pack.unpack_decoded(packed[:-1])

    def test_vector_weight_pairs_have_aligned_original_lane_coordinates(self):
        packed = self.pack.pack_decoded(self.words)
        values = np.frombuffer(packed, dtype="<u2")
        for column, group, kchunk, worker in ((0, 0, 0, 0), (7, 4, 9, 3), (3, 2, 5, 1)):
            start = self.pack.chunk_index(column, group, kchunk, worker) * 4096
            first_row = (column * 20 + group * 4 + worker) * 16
            for row in range(16):
                for pair in range(8):
                    offset = start + self.pack.weight_pair_offset(row, pair)
                    self.assertEqual(offset * 2 % 64, 0)
                    for component in (0, 1):
                        expected = [self.words[first_row + row, kchunk * 256 + lane * 16 + pair * 2 + component]
                                    for lane in range(16)]
                        np.testing.assert_array_equal(values[offset + component * 16:offset + (component + 1) * 16], expected)
        bad = self.words.copy(); bad[123, 456] = 0x7F80
        with self.assertRaises(ValueError):
            self.pack.pack_decoded(bad)

    def test_canonical_input_mapping_is_bijective_aligned_and_bit_preserving(self):
        words = np.arange(4 * 2560, dtype=np.uint16).reshape(4, 2560)
        words[0, 0], words[3, 2559] = 0x8000, 0x8000
        packed = self.pack.pack_inputs(words)
        actual = np.frombuffer(packed, dtype="<u2")
        seen = set()
        for stream in range(4):
            for kchunk in range(10):
                for pair in range(8):
                    offset = self.pack.input_pair_offset(stream, kchunk, pair)
                    self.assertEqual(offset * 2 % 64, 0)
                    for component in (0, 1):
                        for lane in range(16):
                            source = stream * 2560 + kchunk * 256 + lane * 16 + pair * 2 + component
                            seen.add(source)
                            self.assertEqual(actual[offset + component * 16 + lane], words.flat[source])
        self.assertEqual(len(seen), 10240)
        self.assertEqual(self.pack.unpack_inputs(packed).tobytes(), words.tobytes())
        with self.assertRaises(ValueError):
            self.pack.pack_inputs(words[:, :2559])


if __name__ == "__main__":
    unittest.main()
