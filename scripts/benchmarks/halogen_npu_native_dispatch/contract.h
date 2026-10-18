// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#ifndef HALOGEN_NPU_NATIVE_DISPATCH_CONTRACT_H
#define HALOGEN_NPU_NATIVE_DISPATCH_CONTRACT_H

#include <stdint.h>

namespace dispatch_contract {
constexpr unsigned cols = 256;
constexpr unsigned rows = 64;
constexpr unsigned core_calls = 64;
constexpr unsigned input_bytes = cols * sizeof(int16_t);
constexpr unsigned output_bytes = rows * sizeof(int32_t);
constexpr unsigned weight_bytes = rows * cols * sizeof(int16_t);
constexpr unsigned stack_bytes = 4096;

// Row-major, synthetic weights. No model payload is read by this probe.
constexpr int16_t weight_value(unsigned row, unsigned col) {
  return static_cast<int16_t>(static_cast<int>((row * 7 + col * 3) % 17) - 8);
}

// The first element uniquely marks all 64 legal calls. Other elements vary
// with every consecutive call and stay in [-11, 11].
constexpr int16_t input_value(unsigned call, unsigned col) {
  return col == 0
             ? static_cast<int16_t>(static_cast<int>(call) - 32)
             : static_cast<int16_t>(static_cast<int>((col * 5 + call * 7) % 23) - 11);
}

constexpr int32_t poison = (-2147483647 - 1);
static_assert(input_bytes == 512 && output_bytes == 256 && weight_bytes == 32768,
              "DMA and tile-local weight contract changed");
} // namespace dispatch_contract

#endif
