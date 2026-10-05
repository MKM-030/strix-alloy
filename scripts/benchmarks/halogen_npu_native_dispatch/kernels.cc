// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// AIE API use follows the AMD/Xilinx MLIR-AIE examples listed in README.md.
#include "contract.h"
#if defined(DISPATCH_ENABLE_VECTOR)
#include <aie_api/aie.hpp>
#endif

using namespace dispatch_contract;

extern "C" void dispatch_control(const int16_t *input, int32_t *output) {
  for (unsigned row = 0; row < rows; ++row)
    output[row] = static_cast<int32_t>(input[row]);
}

// Explicit fallback. This is never substituted for the vector entry point.
extern "C" void dispatch_gemv_scalar(const int16_t *weights,
                                      const int16_t *input, int32_t *output) {
  for (unsigned row = 0; row < rows; ++row) {
    int32_t sum = 0;
    for (unsigned col = 0; col < cols; ++col)
      sum += static_cast<int32_t>(weights[row * cols + col]) *
             static_cast<int32_t>(input[col]);
    output[row] = sum;
  }
}

// Eight 32-lane MACs per row; lane sums and final reduction fit exactly in
// signed i32 for the bounded synthetic contract. No shift or quantization.
#if defined(DISPATCH_ENABLE_VECTOR)
extern "C" void dispatch_gemv_vector(const int16_t *weights,
                                      const int16_t *input, int32_t *output) {
  for (unsigned row = 0; row < rows; ++row) {
    aie::accum<acc32, 32> sum = aie::zeros<acc32, 32>();
    for (unsigned col = 0; col < cols; col += 32) {
      const auto w = aie::load_v<32>(weights + row * cols + col);
      const auto x = aie::load_v<32>(input + col);
      sum = aie::mac(sum, w, x);
    }
    output[row] = aie::reduce_add(sum.to_vector<int32_t>(0));
  }
}
#endif
