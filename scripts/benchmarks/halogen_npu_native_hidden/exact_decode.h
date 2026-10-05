// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Exact integer implementation of RN32(code*finite_half_scale+finite_half_bias),
// then BF16 RNE. Keeps the specified FP32 rounding boundary. No FP32 mul/FMA.
#pragma once
#include <stdint.h>

namespace hidden_numeric {
struct half_term { int64_t mantissa; int exponent; };

inline half_term finite_half(uint16_t word) {
  const unsigned e = (word >> 10) & 31U;
  const unsigned f = word & 1023U;
  int64_t m = e == 0 ? f : 1024U + f;
  if (word & 0x8000U) m = -m;
  return {m, e == 0 ? -24 : static_cast<int>(e) - 25};
}

inline uint64_t rshift_rne(uint64_t value, unsigned shift) {
  if (!shift) return value;
  // Decode maximum alignment is29 and significand at most49 bits.
  const uint64_t head = value >> shift;
  const uint64_t tail = value & ((uint64_t{1} << shift) - 1);
  const uint64_t halfway = uint64_t{1} << (shift - 1);
  return head + (tail > halfway || (tail == halfway && (head & 1U)));
}

inline uint32_t affine_fp32_bits(uint8_t code, uint16_t scale, uint16_t bias) {
  const auto s = finite_half(scale), b = finite_half(bias);
  const int exponent = s.exponent < b.exponent ? s.exponent : b.exponent;
  const int64_t sm = s.mantissa * code * (int64_t{1} << (s.exponent - exponent));
  const int64_t bm = b.mantissa * (int64_t{1} << (b.exponent - exponent));
  const int64_t sum = sm + bm;
  if (!sum) {
    // RN exact cancellation is+0; -0 only when both operands are negative0.
    const bool scale_zero = code == 0 || (scale & 0x7FFFU) == 0;
    const bool bias_zero = (bias & 0x7FFFU) == 0;
    return scale_zero && bias_zero && (scale & bias & 0x8000U) ? 0x80000000U : 0U;
  }
  const bool negative = sum < 0;
  uint64_t mag = negative ? static_cast<uint64_t>(-sum) : static_cast<uint64_t>(sum);
  unsigned msb = 0;
  for (uint64_t t = mag; t >>= 1;) ++msb;
  int unbiased = exponent + static_cast<int>(msb);
  uint64_t significand = msb > 23 ? rshift_rne(mag, msb - 23) : mag << (23 - msb);
  if (significand == (uint64_t{1} << 24)) { significand >>= 1; ++unbiased; }
  // All nonzero affine half values are normal FP32 (smallest2^-24).
  return (negative ? 0x80000000U : 0U) | (static_cast<uint32_t>(unbiased + 127) << 23) |
      (static_cast<uint32_t>(significand) & 0x7FFFFFU);
}

inline uint16_t fp32_bits_to_bf16(uint32_t bits) {
  return static_cast<uint16_t>((bits + 0x7FFFU + ((bits >> 16) & 1U)) >> 16);
}

inline uint16_t decode_q8(uint8_t code, uint16_t scale, uint16_t bias) {
  return fp32_bits_to_bf16(affine_fp32_bits(code, scale, bias));
}
}
