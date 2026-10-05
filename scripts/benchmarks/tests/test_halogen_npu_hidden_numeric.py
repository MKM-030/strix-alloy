"""Offline arithmetic tests; no provider, checkpoint, GPU, or NPU imports."""
import importlib.util
from pathlib import Path
import struct
import random
import unittest

try:
    import numpy as np
except ImportError:
    np = None


SOURCE = Path(__file__).parents[1] / "halogen_npu_hidden_numeric.py"
spec = importlib.util.spec_from_file_location("hidden_numeric", SOURCE)
numeric = importlib.util.module_from_spec(spec)
spec.loader.exec_module(numeric)


def f32(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def bf16(value):
    return numeric.f32_to_bf16_rne(f32(value))


class ExactArithmeticTests(unittest.TestCase):
    def test_fp32_rounding_ties_and_subnormals(self):
        self.assertEqual(numeric.round_dyadic_to_f32((1 << 24) + 1, -24), 0x3F800000)
        self.assertEqual(numeric.round_dyadic_to_f32((1 << 24) + 3, -24), 0x3F800002)
        self.assertEqual(numeric.round_dyadic_to_f32(1, -150), 0)
        self.assertEqual(numeric.round_dyadic_to_f32(3, -150), 2)
        self.assertEqual(numeric.round_dyadic_to_f32(-3, -150), 0x80000002)

    def test_bf16_rounding_ties_to_even(self):
        self.assertEqual(numeric.f32_to_bf16_rne(0x3F808000), 0x3F80)
        self.assertEqual(numeric.f32_to_bf16_rne(0x3F818000), 0x3F82)
        self.assertEqual(numeric.f32_to_bf16_rne(0xBF818000), 0xBF82)
        self.assertEqual(numeric.f32_to_bf16_rne(0x80000000), 0x8000)

    def test_signed_zero_and_gradual_underflow(self):
        self.assertEqual(numeric.add_f32_bits(0x80000000, 0x80000000), 0x80000000)
        for model in numeric.MODELS:
            self.assertEqual(numeric.dot2_f32_bits(0x8000, 0x3F80, 0x8000, 0x3F80,
                                                   0x80000000, model=model), 0x80000000)
        self.assertEqual(numeric.dot2_f32_bits(0x8001, 1, 0, 0, 0, model="fused"), 0x80000000)

    def test_generic_fma_has_one_rounding(self):
        # (1+2^-23)*(1-2^-23)-1 is exactly -2^-46.
        result = numeric.fma_f32_bits(0x3F800001, 0x3F7FFFFE, f32(-1))
        self.assertEqual(result, f32(-(2.0 ** -46)))
        product = numeric.fma_f32_bits(0x3F800001, 0x3F7FFFFE, 0)
        self.assertEqual(numeric.add_f32_bits(product, f32(-1)), 0)

    def test_unsigned_codes_and_little_endian_fp16_groups(self):
        payload = bytes([0, 128, 255] + [1] * 61 + [255] * 64)
        payload += struct.pack("<4H", 0x3C00, 0xC000, 0x3800, 0x3C00)
        actual = numeric.decode_q8_row(payload, width=128)
        self.assertEqual(actual[:3], [bf16(-2), bf16(126), bf16(253)])
        self.assertEqual(actual[64], bf16(128.5))

    def test_q8_affine_product_is_exact_before_add(self):
        # uint8 has <=8 significant bits, FP16 <=11: their product fits FP32.
        for code in [0, 1, 127, 128, 254, 255]:
            for scale in [0, 1, 0x03FF, 0x0400, 0x3555, 0x7BFF, 0xBC01]:
                for bias in [0, 0x8000, 0x0001, 0xB555, 0x7BFF]:
                    scale32 = numeric.fp16_to_f32_bits(scale)
                    bias32 = numeric.fp16_to_f32_bits(bias)
                    separate = numeric.add_f32_bits(
                        f32(code * numeric.bits_to_float(scale32)), bias32)
                    self.assertEqual(numeric.affine_f32_bits(code, scale, bias), separate)

    def test_dot2_models_are_explicit_and_distinguishable(self):
        args = (bf16(1), bf16(1), bf16(2.0 ** -24), bf16(1), f32(-1))
        self.assertEqual(numeric.dot2_f32_bits(*args, model="fused"), f32(2.0 ** -24))
        self.assertEqual(numeric.dot2_f32_bits(*args, model="sequential"), f32(2.0 ** -24))
        self.assertEqual(numeric.dot2_f32_bits(*args, model="pair_then_acc"), 0)
        args = (bf16(2.0 ** -24), bf16(1), bf16(-1), bf16(1), f32(1))
        self.assertEqual(numeric.dot2_f32_bits(*args, model="fused"), f32(2.0 ** -24))
        self.assertEqual(numeric.dot2_f32_bits(*args, model="sequential"), 0)

    def test_original_block_reset_and_xor_order(self):
        weights = [bf16(1)] * 512
        values = [0] * 512
        # Lane0 block0=2^25, lane0 block1=(-2^25+1) rounds to -2^25;
        # lane1 block0=1. Original block reset then XOR tree gives 1.
        values[0], values[256], values[258], values[16] = (
            bf16(2.0 ** 25), bf16(-(2.0 ** 25)), bf16(1), bf16(1))
        self.assertEqual(numeric.project_row_fp32(weights, values, model="fused"), f32(1))
        lanes = [f32(2.0 ** 24), f32(1)] + [0] * 6 + [f32(-(2.0 ** 24))] + [0] * 7
        self.assertEqual(numeric.xor_reduce_f32(lanes), f32(1))

    def test_extent_and_nonfinite_rejection(self):
        for word in [0x7C00, 0xFC00, 0x7E00]:
            with self.assertRaises(ValueError):
                numeric.affine_f32_bits(1, word, 0)
        for payload in [b"", bytes(2719), bytes(2721)]:
            with self.assertRaises(ValueError):
                numeric.decode_q8_row(payload, width=2560)
        with self.assertRaises(ValueError):
            numeric.affine_f32_bits(256, 0, 0)
        with self.assertRaises(ValueError):
            numeric.project_row_fp32([0] * 255, [0] * 255)
        with self.assertRaises(ValueError):
            numeric.project_row_fp32([0] * 256, [0x7F80] + [0] * 255)
        with self.assertRaises(ValueError):
            numeric.dot2_f32_bits(0, 0, 0, 0, 0, model="unknown")


@unittest.skipIf(np is None, "NumPy acceleration is optional for scalar tests")
class VectorArithmeticTests(unittest.TestCase):
    def test_vector_affine_matches_integer_scalar(self):
        rng = random.Random(6116)
        width, rows = 256, 3
        payload = bytearray()
        for _ in range(rows):
            payload.extend(rng.randrange(256) for _ in range(width))
            pairs = [rng.randrange(0x7C00) | (rng.randrange(2) << 15)
                     for _ in range(width // 32)]
            payload.extend(struct.pack("<" + "H" * len(pairs), *pairs))
        actual = numeric.decode_q8_numpy(bytes(payload), width=width, rows=rows)
        stride = width + width // 16
        for row in range(rows):
            self.assertEqual(actual[row].tolist(), numeric.decode_q8_row(
                payload[row * stride:(row + 1) * stride], width=width))

    def test_inexact_fp64_addition_uses_integer_fallback(self):
        arrays = [np.array([word], dtype=np.uint16) for word in
                  [bf16(2.0 ** -100), bf16(1), bf16(-1), bf16(1)]]
        accumulator = np.array([1], dtype=np.float32)
        for model in numeric.MODELS:
            actual, fallback = numeric._dot2_numpy(*arrays, accumulator, model)
            self.assertEqual(fallback, 1)
            self.assertEqual(int(actual.view(np.uint32)[0]), numeric.dot2_f32_bits(
                *(int(word[0]) for word in arrays), f32(1), model=model))

    def test_vector_schedule_matches_integer_scalar_for_all_models(self):
        rng = random.Random(162560)
        def words(count):
            return [rng.randrange(70, 161) << 7 | rng.randrange(128)
                    | (rng.randrange(2) << 15) for _ in range(count)]
        weights = np.array(words(3 * 512), dtype=np.uint16).reshape(3, 512)
        inputs = np.array(words(2 * 512), dtype=np.uint16).reshape(2, 512)
        for model in numeric.MODELS:
            actual, _, _ = numeric.project_numpy(weights, inputs, model=model)
            for stream in range(2):
                for row in range(3):
                    expected = numeric.project_row_fp32(weights[row].tolist(), inputs[stream].tolist(), model=model)
                    self.assertEqual(int(actual[stream, row]), expected)


if __name__ == "__main__":
    unittest.main()
