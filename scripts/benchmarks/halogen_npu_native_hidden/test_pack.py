"""Offline synthetic tests. No model payloads, compiler, or device imports."""
import importlib.util
from pathlib import Path
import struct
import unittest


class PackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name("pack.py")
        if not path.exists():
            raise AssertionError("lossless streamed Q8 packer has not been implemented")
        spec = importlib.util.spec_from_file_location("hidden_pack", path)
        cls.pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.pack)
        raw = bytearray(2560 * 2720)
        for row in range(2560):
            base = row * 2720
            raw[base:base + 2560] = bytes((row * 13 + k * 7) & 255 for k in range(2560))
            for group in range(40):
                # Finite FP16, including sign and distinct scale/bias words.
                struct.pack_into("<HH", raw, base + 2560 + group * 4,
                                 0x3000 + ((row + group) & 1023),
                                 0xA000 + ((row * 5 + group) & 1023))
        cls.raw = bytes(raw)

    def test_inverse_reconstructs_every_original_bit(self):
        packed = self.pack.pack_weights(self.raw)
        self.assertEqual(len(packed), len(self.raw))
        self.assertEqual(self.pack.unpack_weights(packed), self.raw)

    def test_chunk_rows_and_metadata_are_in_worker_order(self):
        packed = self.pack.pack_weights(self.raw)
        for column, group, kchunk, worker in ((0, 0, 0, 0), (7, 4, 9, 3), (3, 2, 5, 1)):
            chunk = self.pack.chunk_index(column, group, kchunk, worker) * 4352
            first_row = (column * 20 + group * 4 + worker) * 16
            for r in (0, 7, 15):
                base = (first_row + r) * 2720
                self.assertEqual(packed[chunk + r * 256:chunk + (r + 1) * 256],
                                 self.raw[base + kchunk * 256:base + (kchunk + 1) * 256])
                self.assertEqual(packed[chunk + 4096 + r * 16:chunk + 4096 + (r + 1) * 16],
                                 self.raw[base + 2560 + kchunk * 16:base + 2560 + (kchunk + 1) * 16])

    def test_rejects_short_long_and_nonfinite_half_metadata(self):
        for blob in (self.raw[:-1], self.raw + b"\0"):
            with self.assertRaises(ValueError):
                self.pack.pack_weights(blob)
        nonfinite = bytearray(self.raw)
        struct.pack_into("<H", nonfinite, 2560, 0x7C00)
        with self.assertRaises(ValueError):
            self.pack.pack_weights(nonfinite)

    def test_corruption_changes_inverse_receipt(self):
        packed = bytearray(self.pack.pack_weights(self.raw))
        packed[-1] ^= 1
        self.assertNotEqual(self.pack.unpack_weights(packed), self.raw)


if __name__ == "__main__":
    unittest.main()
