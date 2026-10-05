// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#pragma once
#include <stdint.h>

namespace hidden_contract {
constexpr unsigned rows = 2560, cols = 2560, streams = 4;
constexpr unsigned columns = 8, workers = 4, groups = 5, k_chunks = 10;
constexpr unsigned tile_rows = 16, chunk_k = 256, lanes = 16, core_calls = 64;
constexpr unsigned input_elements = streams * cols, output_elements = streams * rows;
constexpr unsigned input_bytes = input_elements * 2, output_bytes = output_elements * 2;
constexpr unsigned raw_weight_bytes = rows * 2720, weight_elements = rows * cols;
constexpr unsigned weight_bytes = weight_elements * 2, chunk_bytes = 8192;
constexpr unsigned aggregate_bytes = workers * chunk_bytes, column_weight_bytes = 1638400;
constexpr unsigned partial_elements = streams * tile_rows * lanes;
constexpr unsigned stack_bytes = 4096;
// One input object, two streamed weight chunks, two output objects, partials,
// and stack. Exact CPU initialization decoding removes tile decode scratch.
// The emitted map must prove actual placement.
constexpr unsigned nominal_worker_bytes = input_bytes + 2 * chunk_bytes +
    2 * streams * tile_rows * 2 + partial_elements * 4 + stack_bytes;
static_assert(raw_weight_bytes == 6963200 && weight_bytes == 13107200 && nominal_worker_bytes == 45312,
              "initialization decoded hidden dataflow budget");
}
