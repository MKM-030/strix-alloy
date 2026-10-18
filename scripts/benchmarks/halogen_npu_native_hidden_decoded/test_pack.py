"""Only synthetic decoded-layout tests; no generator/runtime/model imports."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np


class DecodedPackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("pack.py")
        if not source.exists():
            raise AssertionError("initialization decoded BF16 packer is missing")
        spec = importlib.util.spec_from_file_location("decoded_hidden_pack", source)
        cls.pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.pack)
        indices = np.arange(2560 * 2560, dtype=np.uint32).reshape(2560, 2560)
        cls.words = ((indices & 0x3FFF) | ((indices // 2560 & 1) << 15)).astype("<u2")

    def test_inverse_reconstructs_every_decoded_bf16_word(self):
        packed = self.pack.pack_decoded(self.words)
        self.assertEqual(len(packed), 13107200)
        self.assertEqual(self.pack.unpack_decoded(packed).tobytes(), self.words.tobytes())

    def test_worker_chunk_is_original_row16_by_k256(self):
        packed = self.pack.pack_decoded(self.words)
        for column, group, kchunk, worker in ((0, 0, 0, 0), (7, 4, 9, 3), (3, 2, 5, 1)):
            start = self.pack.chunk_index(column, group, kchunk, worker) * 8192
            first_row = (column * 20 + group * 4 + worker) * 16
            expected = self.words[first_row:first_row + 16, kchunk * 256:kchunk * 256 + 256]
            self.assertEqual(packed[start:start + 8192], expected.tobytes())

    def test_rejects_wrong_shape_type_and_nonfinite_decoded_words(self):
        for bad in (self.words[:1], self.words.astype(np.float32)):
            with self.assertRaises(ValueError):
                self.pack.pack_decoded(bad)
        bad = self.words.copy()
        bad[123, 456] = 0x7F80
        with self.assertRaises(ValueError):
            self.pack.pack_decoded(bad)
        with self.assertRaises(ValueError):
            self.pack.unpack_decoded(bytes(13107200 - 1))


if __name__ == "__main__":
    unittest.main()
