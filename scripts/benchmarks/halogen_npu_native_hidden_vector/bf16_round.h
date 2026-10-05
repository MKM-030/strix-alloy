// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#pragma once
#include <stdint.h>
namespace hidden_numeric {
inline uint16_t fp32_bits_to_bf16(uint32_t bits) {
  return static_cast<uint16_t>((bits + 0x7FFFU + ((bits >> 16) & 1U)) >> 16);
}
}
