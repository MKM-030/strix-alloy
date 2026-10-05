// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#pragma once
#include <stdint.h>

namespace hidden_contract {
constexpr unsigned rows = 2560, cols = 2560, streams = 4;
constexpr unsigned columns = 8, workers = 4, groups = 5, k_chunks = 10;
constexpr unsigned tile_rows = 16, chunk_k = 256, lanes = 16, core_calls = 64;
constexpr unsigned input_elements = streams * cols, output_elements = streams * rows;
constexpr unsigned input_bytes = input_elements * 2, output_bytes = output_elements * 2;
constexpr unsigned weight_bytes = rows * 2720, chunk_bytes = 4352;
constexpr unsigned aggregate_bytes = workers * chunk_bytes, column_weight_bytes = 870400;
constexpr unsigned partial_elements = streams * tile_rows * lanes;
constexpr unsigned decoded_elements = tile_rows * chunk_k;
constexpr unsigned stack_bytes = 4096;
// One input object, two streamed weight chunks, two output objects, partials,
// decoded scratch and stack. The emitted map must prove actual placement.
constexpr unsigned nominal_worker_bytes = input_bytes + 2 * chunk_bytes +
    2 * streams * tile_rows * 2 + partial_elements * 4 + decoded_elements * 2 + stack_bytes;
static_assert(weight_bytes == 6963200 && nominal_worker_bytes == 45824, "hidden dataflow budget");
}
