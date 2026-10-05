// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Complete H arithmetic with offline lane-pair-packed decoded BF16 weights.
// Canonical input is permuted by the host; every hot load is contiguous.
#include "contract.h"
#include "bf16_round.h"
#include <aie_api/aie.hpp>

using namespace hidden_contract;

extern "C" void hidden_reset(float *partials) {
  for (unsigned i = 0; i < partial_elements; i += 16)
    aie::store_v(partials + i, aie::zeros<float, 16>());
}

extern "C" void hidden_chunk(const uint16_t *packed, const uint16_t *input,
                              float *partials, int32_t kchunk) {
  const auto *weight = reinterpret_cast<const bfloat16 *>(packed);
  const auto *x = reinterpret_cast<const bfloat16 *>(input);
  for (unsigned row = 0; row < tile_rows; ++row) {
    aie::accum<accfloat, 16> block0 = aie::zeros<accfloat, 16>();
    aie::accum<accfloat, 16> block1 = aie::zeros<accfloat, 16>();
    aie::accum<accfloat, 16> block2 = aie::zeros<accfloat, 16>();
    aie::accum<accfloat, 16> block3 = aie::zeros<accfloat, 16>();
    for (unsigned pair = 0; pair < pairs; ++pair) {
      const auto wp = aie::load_v<32>(weight + weight_pair_offset(row, pair));
      const auto w0 = wp.extract<16>(0), w1 = wp.extract<16>(1);
      // Each independent stream retains exactly the old ordered two-MAC chain.
      // No claim of exact GPU fused-dot2 parity; only operand access changes.
      {
        const auto xp = aie::load_v<32>(x + input_pair_offset(0, unsigned(kchunk), pair));
        block0 = aie::mac(block0, w0, xp.extract<16>(0));
        block0 = aie::mac(block0, w1, xp.extract<16>(1));
      }
      {
        const auto xp = aie::load_v<32>(x + input_pair_offset(1, unsigned(kchunk), pair));
        block1 = aie::mac(block1, w0, xp.extract<16>(0));
        block1 = aie::mac(block1, w1, xp.extract<16>(1));
      }
      {
        const auto xp = aie::load_v<32>(x + input_pair_offset(2, unsigned(kchunk), pair));
        block2 = aie::mac(block2, w0, xp.extract<16>(0));
        block2 = aie::mac(block2, w1, xp.extract<16>(1));
      }
      {
        const auto xp = aie::load_v<32>(x + input_pair_offset(3, unsigned(kchunk), pair));
        block3 = aie::mac(block3, w0, xp.extract<16>(0));
        block3 = aie::mac(block3, w1, xp.extract<16>(1));
      }
    }
    const unsigned base0 = row * lanes, base1 = (tile_rows + row) * lanes;
    const unsigned base2 = (2 * tile_rows + row) * lanes, base3 = (3 * tile_rows + row) * lanes;
    aie::store_v(partials + base0, aie::add(aie::load_v<16>(partials + base0), block0.to_vector<float>()));
    aie::store_v(partials + base1, aie::add(aie::load_v<16>(partials + base1), block1.to_vector<float>()));
    aie::store_v(partials + base2, aie::add(aie::load_v<16>(partials + base2), block2.to_vector<float>()));
    aie::store_v(partials + base3, aie::add(aie::load_v<16>(partials + base3), block3.to_vector<float>()));
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
