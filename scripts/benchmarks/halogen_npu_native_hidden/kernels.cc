// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Full H arithmetic. Native BF16 elementwise MAC; no BFP weight conversion.
#include "contract.h"
#include "exact_decode.h"
#include <aie_api/aie.hpp>

using namespace hidden_contract;

extern "C" void hidden_reset(float *partials) {
  for (unsigned i = 0; i < partial_elements; i += 16)
    aie::store_v(partials + i, aie::zeros<float, 16>());
}

extern "C" void hidden_chunk(const uint8_t *packed, const uint16_t *input,
                              float *partials, uint16_t *decoded, int32_t kchunk) {
  // Original metadata remains little-endian packed FP16 bit patterns.
  for (unsigned row = 0; row < tile_rows; ++row) {
    for (unsigned group = 0; group < 4; ++group) {
      const unsigned meta = 4096 + row * 16 + group * 4;
      const uint16_t scale = packed[meta] | (uint16_t(packed[meta + 1]) << 8);
      const uint16_t bias = packed[meta + 2] | (uint16_t(packed[meta + 3]) << 8);
      for (unsigned col = 0; col < 64; ++col)
        decoded[row * chunk_k + group * 64 + col] = hidden_numeric::decode_q8(
            packed[row * chunk_k + group * 64 + col], scale, bias);
    }
  }
  const auto *weight = reinterpret_cast<const bfloat16 *>(decoded);
  const auto *x = reinterpret_cast<const bfloat16 *>(input);
  for (unsigned row = 0; row < tile_rows; ++row) {
    for (unsigned stream = 0; stream < streams; ++stream) {
      aie::accum<accfloat, 16> block = aie::zeros<accfloat, 16>();
      for (unsigned pair = 0; pair < 8; ++pair) {
        aie::vector<bfloat16, 16> w0, w1, x0, x1;
        for (unsigned lane = 0; lane < lanes; ++lane) {
          const unsigned k = lane * 16 + pair * 2;
          w0.set(weight[row * chunk_k + k], lane);
          w1.set(weight[row * chunk_k + k + 1], lane);
          x0.set(x[stream * cols + unsigned(kchunk) * chunk_k + k], lane);
          x1.set(x[stream * cols + unsigned(kchunk) * chunk_k + k + 1], lane);
        }
        // Explicit sequential two-MAC dot2. Original GPU fused-dot2 semantics
        // are independently investigated; never claim exact GPU dot parity.
        block = aie::mac(block, w0, x0);
        block = aie::mac(block, w1, x1);
      }
      const unsigned base = (stream * tile_rows + row) * lanes;
      const auto old = aie::load_v<16>(partials + base);
      const auto completed_block = block.to_vector<float>();
      aie::store_v(partials + base, aie::add(old, completed_block));
    }
  }
}

extern "C" void hidden_finish(const float *partials, uint16_t *output) {
  for (unsigned stream = 0; stream < streams; ++stream) {
    for (unsigned row = 0; row < tile_rows; ++row) {
      auto lanes_value = aie::load_v<16>(partials + (stream * tile_rows + row) * lanes);
      for (unsigned distance = 8; distance; distance >>= 1) {
        aie::vector<float, 16> xor_lanes;
        for (unsigned lane = 0; lane < lanes; ++lane)
          xor_lanes.set(lanes_value.get(lane ^ distance), lane);
        lanes_value = aie::add(lanes_value, xor_lanes);
      }
      union { float value; uint32_t bits; } reduced;
      reduced.value = lanes_value.get(0);
      output[stream * tile_rows + row] = hidden_numeric::fp32_bits_to_bf16(reduced.bits);
    }
  }
}
