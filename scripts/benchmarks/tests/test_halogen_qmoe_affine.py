"""One small source fixture; no model files, native libraries or providers."""
import io
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hgn_q4c_slice import decode_rows
from halogen_qmoe_affine import (
    quantize_q4c_rows,
    quantize_expert,
    quantize_rows,
    reconstruct_rows,
    reorder_gate_up_rows,
)


class AffineFixture(unittest.TestCase):
    def test_known_reconstruction_and_nonuniform_q4c_error(self):
        # An exact INT4 grid establishes low-even/high-odd bytes and an odd
        # number of block zero points (unused final high nibble must be zero).
        grid = np.tile(np.arange(-8, 8, dtype=np.float32), 6)[None, :]
        exact = quantize_rows(grid, row_layout="linear")
        np.testing.assert_array_equal(exact.weights[0, :8], np.arange(0x10, 0x100, 0x22, dtype=np.uint8))
        np.testing.assert_array_equal(exact.scales, np.ones((1, 3), dtype=np.float32))
        np.testing.assert_array_equal(exact.zero_points, np.array([[0x88, 0x08]], dtype=np.uint8))
        np.testing.assert_array_equal(reconstruct_rows(exact), grid)
        self.assertEqual(exact.diagnostics["max_abs_error"], 0.0)

        # q4c uses a codebook, not nibble-8. This synthetic in-memory payload
        # is decoded by the unchanged real decoder contract for comparison.
        book = np.array([-2, -1.5, -1, -.75, -.5, -.25, -.125, 0,
                         .125, .25, .5, .75, 1, 1.25, 1.5, 2], dtype="<f4")
        codes = np.tile(np.arange(16, dtype=np.uint8), 6)[None, :]
        packed = (codes[:, 0::2] | (codes[:, 1::2] << 4)).astype(np.uint8)
        source_scales = np.array([[1, .5, 2]], dtype="<f2")
        payload = book.tobytes() + packed.tobytes() + bytes(16) + source_scales.tobytes() + bytes(10)
        decoded = decode_rows(io.BytesIO(payload),
                              {"store": 5, "variant": 2, "dims": [1, 96], "offset": 0, "size": len(payload)},
                              0, 1)
        approx = quantize_q4c_rows(book, packed, source_scales, row_layout="linear")
        restored = reconstruct_rows(approx)
        error = np.abs(restored.astype(np.float64) - decoded)
        self.assertGreater(float(error.max()), 0)
        self.assertFalse(np.array_equal(approx.weights, packed))
        self.assertTrue(np.all(error.reshape(1, 3, 32) <= approx.scales[:, :, None] / 2 + 1e-6))
        self.assertAlmostEqual(approx.diagnostics["max_abs_error"], float(error.max()), places=6)
        self.assertEqual(approx.weights.dtype, np.uint8)
        self.assertEqual(approx.scales.dtype, np.float32)
        self.assertEqual(approx.zero_points.dtype, np.uint8)
        np.testing.assert_array_equal(approx.bias, np.zeros(1, dtype=np.float32))

        gate_up = np.repeat(np.array([1, 2, 11, 12], dtype=np.float32)[:, None], 32, axis=1)
        ordered = reorder_gate_up_rows(gate_up, source_layout="concatenated", target_layout="interleaved")
        np.testing.assert_array_equal(ordered[:, 0], [1, 11, 2, 12])
        np.testing.assert_array_equal(reorder_gate_up_rows(ordered, source_layout="interleaved", target_layout="concatenated"), gate_up)
        toy_gate_up = np.repeat(np.arange(64, dtype=np.float32)[:, None], 32, axis=1)
        toy_expert = quantize_expert(toy_gate_up, np.zeros((32, 32), dtype=np.float32),
                                     source_gate_up_layout="concatenated", packed_gate_up_layout="interleaved",
                                     width=32, intermediate=32)
        self.assertEqual(toy_expert.gate_up.row_layout, "gate_up_interleaved")
        self.assertEqual(toy_expert.gate_up.block_size, 32)
        self.assertTrue(toy_expert.gate_up.diagnostics["activation_policy"].startswith("unset"))
        self.assertEqual(toy_expert.down.diagnostics["max_abs_error"], 0.0)
        for invalid in [np.zeros((512, 2, 32), dtype=np.float32),
                        np.full((1, 32), np.nan, dtype=np.float32),
                        np.zeros((1, 31), dtype=np.float32),
                        np.zeros((1, 32), dtype=np.float64)]:
            with self.assertRaises(ValueError):
                quantize_rows(invalid, row_layout="linear")


if __name__ == "__main__":
    unittest.main()
