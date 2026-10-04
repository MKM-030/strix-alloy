"""Tiny arithmetic fixtures; no assets, checkpoint, provider or engine."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halogen_npu_v2_d_prepare import bf16_rne, rms_bf16, reference, widen_bf16


class DPrepareMathTests(unittest.TestCase):
    def test_bf16_ties_signed_zero_and_overflow(self):
        values = np.array([0x3f808000, 0x3f818000, 0xbf808000,
                           0x00008000, 0x00018000, 0x80000000], dtype=np.uint32).view(np.float32)
        expected = np.array([0x3f80, 0x3f82, 0xbf80, 0, 2, 0x8000], dtype="<u2")
        np.testing.assert_array_equal(bf16_rne(values).view(np.uint32) >> 16, expected)
        np.testing.assert_array_equal(widen_bf16(expected).view(np.uint32), expected.astype(np.uint32) << 16)
        with self.assertRaisesRegex(ValueError, "overflow"):
            bf16_rne(np.array([0x7f7fffff], dtype=np.uint32).view(np.float32))

    def test_whole_row_norm_raw_gamma_and_input_contract(self):
        # Four features form one group. Per-half normalization would differ.
        x = np.array([[3, 4, 0, 0]], dtype=np.float32)
        norm = rms_bf16(x, np.zeros(4, dtype=np.float32))
        expected = np.array([[0x3f9a, 0x3fcd, 0, 0]], dtype="<u2")
        np.testing.assert_array_equal(norm.view(np.uint32) >> 16, expected)
        norm = rms_bf16(x[:, :2], np.array([-1, 1], dtype=np.float32))
        np.testing.assert_array_equal(norm.view(np.uint32) >> 16, [[0, 0x4011]])
        with self.assertRaisesRegex(ValueError, "exactly BF16"):
            rms_bf16(np.array([[1.001]], dtype=np.float32), np.zeros(1, dtype=np.float32))
        with self.assertRaisesRegex(ValueError, "explicit wire_mode"):
            reference(None, None, {}, "default")
        with self.assertRaisesRegex(ValueError, "count1"):
            reference(np.zeros((2, 2560), dtype=np.float32), np.zeros((1, 10240), dtype=np.float32), {}, "D")


if __name__ == "__main__":
    unittest.main()
