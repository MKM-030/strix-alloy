# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Emit complete32-worker H with lane-pair-packed decoded BF16 weights/input.

Only installed compiler dialect APIs are imported. No XRT/device or weights.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path

import numpy as np
from aie.dialects.aie import (
    AIEDevice, ObjectFifoPort, buffer, core, device, external_func,
    object_fifo, object_fifo_link, tile,
)
from aie.dialects import arith
from aie.dialects.aiex import dma_wait, npu_dma_memcpy_nd, runtime_sequence
from aie.extras import types as T
from aie.extras.context import mlir_mod_ctx
from aie.helpers.dialects.scf import _for as range_

COLUMNS, WORKERS, GROUPS, K_CHUNKS, CALLS = 8, 4, 5, 10, 64
INPUT_ELEMENTS, OUTPUT_ELEMENTS, WEIGHT_BYTES = 10240, 10240, 13107200
WEIGHT_ELEMENTS = WEIGHT_BYTES // 2
CHUNK_ELEMENTS, AGGREGATE_ELEMENTS, COLUMN_ELEMENTS = 4096, 16384, 819200
CHUNK_BYTES, AGGREGATE_BYTES, COLUMN_BYTES = 8192, 32768, 1638400


def generate() -> tuple[str, dict]:
    inp = np.ndarray[(INPUT_ELEMENTS,), np.dtype[np.uint16]]
    out = np.ndarray[(OUTPUT_ELEMENTS,), np.dtype[np.uint16]]
    weights = np.ndarray[(WEIGHT_ELEMENTS,), np.dtype[np.uint16]]
    chunk = np.ndarray[(CHUNK_ELEMENTS,), np.dtype[np.uint16]]
    aggregate = np.ndarray[(AGGREGATE_ELEMENTS,), np.dtype[np.uint16]]
    tile_output = np.ndarray[(64,), np.dtype[np.uint16]]
    column_output = np.ndarray[(256,), np.dtype[np.uint16]]
    partial = np.ndarray[(1024,), np.dtype[np.float32]]
    transfers = []
    with mlir_mod_ctx() as ctx:
        @device(AIEDevice.npu2)
        def design():
            reset = external_func("hidden_reset", inputs=[partial], link_with="kernels.o")
            process = external_func("hidden_chunk", inputs=[chunk, inp, partial, T.i32()], link_with="kernels.o")
            finish = external_func("hidden_finish", inputs=[partial, tile_output], link_with="kernels.o")
            input_host_fifos, weight_host_fifos, output_host_fifos = [], [], []
            # Stateful object-FIFO lowering inserts buffers/locks at tile sites.
            # Resolve every tile before any FIFO/core, as installed iron.Program
            # does, so resources on a later column dominate earlier core uses.
            column_tiles = []
            for column in range(COLUMNS):
                shim, memory = tile(column, 0), tile(column, 1)
                computes = [tile(column, row) for row in range(2, 6)]
                column_tiles.append((shim, memory, computes))
            core_records = []
            for column, (shim, memory, computes) in enumerate(column_tiles):
                host_input = object_fifo(f"input_host_c{column}", shim, memory, 1, inp)
                broadcast_input = object_fifo(f"input_workers_c{column}", memory, computes, [1, 1, 1, 1, 1], inp)
                object_fifo_link(host_input, broadcast_input)
                host_weight = object_fifo(f"weight_host_c{column}", shim, memory, 2, aggregate)
                worker_weights = [object_fifo(f"weight_c{column}_w{worker}", memory, compute, 2, chunk)
                                  for worker, compute in enumerate(computes)]
                # Split offsets count BF16 words, not bytes.
                object_fifo_link(host_weight, worker_weights, dstOffsets=[0, 4096, 8192, 12288])
                worker_outputs = [object_fifo(f"output_c{column}_w{worker}", compute, memory, 2, tile_output)
                                  for worker, compute in enumerate(computes)]
                host_output = object_fifo(f"output_host_c{column}", memory, shim, 2, column_output)
                object_fifo_link(worker_outputs, host_output, srcOffsets=[0, 64, 128, 192])
                for worker, compute in enumerate(computes):
                    scratch = buffer(compute, partial, name=f"partial_c{column}_w{worker}")
                    core_records.append((compute, broadcast_input, worker_weights, worker_outputs,
                                         worker, scratch))
                input_host_fifos.append(host_input)
                weight_host_fifos.append(host_weight)
                output_host_fifos.append(host_output)

            # Emit cores only after all FIFO links and scratch buffers exist.
            for (compute, broadcast_input, worker_weights, worker_outputs,
                 worker, scratch) in core_records:
                @core(compute, stack_size=4096)
                def finite_core():
                    for _ in range_(CALLS):
                        input_object = broadcast_input.acquire(ObjectFifoPort.Consume, 1)
                        for _ in range_(GROUPS):
                            reset(scratch)
                            for kchunk in range_(K_CHUNKS):
                                weight_object = worker_weights[worker].acquire(ObjectFifoPort.Consume, 1)
                                k32 = arith.index_cast(T.i32(), kchunk)
                                process(weight_object, input_object, scratch, k32)
                                worker_weights[worker].release(ObjectFifoPort.Consume, 1)
                            output_object = worker_outputs[worker].acquire(ObjectFifoPort.Produce, 1)
                            finish(scratch, output_object)
                            worker_outputs[worker].release(ObjectFifoPort.Produce, 1)
                        broadcast_input.release(ObjectFifoPort.Consume, 1)

            @runtime_sequence(weights, inp, out, sym_name="hidden")
            def sequence(weight_host, input_host, output_host):
                # Queue every output first, then input and weights; no chunk launch.
                for column in range(COLUMNS):
                    npu_dma_memcpy_nd(output_host_fifos[column], 2, output_host,
                        offsets=[0, 0, 0, column * 320],
                        sizes=[5, 4, 4, 16], strides=[64, 16, 2560, 1])
                    transfers.append({"kind": "output", "column": column, "bo": 2,
                        "element_bytes": 2, "base_element": column * 320,
                        "sizes": [5, 4, 4, 16], "strides": [64, 16, 2560, 1], "bytes": 2560})
                for column in range(COLUMNS):
                    npu_dma_memcpy_nd(input_host_fifos[column], 0, input_host,
                        sizes=[1, 1, 1, INPUT_ELEMENTS], issue_token=True)
                    transfers.append({"kind": "input", "column": column, "bo": 1,
                        "element_bytes": 2, "base_element": 0,
                        "sizes": [1, 1, 1, INPUT_ELEMENTS], "strides": [0, 0, 0, 1], "bytes": 20480})
                for column in range(COLUMNS):
                    npu_dma_memcpy_nd(weight_host_fifos[column], 1, weight_host,
                        offsets=[0, 0, 0, column * COLUMN_ELEMENTS],
                        sizes=[1, 1, 50, AGGREGATE_ELEMENTS], strides=[0, 0, AGGREGATE_ELEMENTS, 1], issue_token=True)
                    transfers.append({"kind": "weights", "column": column, "bo": 0,
                        "element_bytes": 2, "base_element": column * COLUMN_ELEMENTS,
                        "sizes": [1, 1, 50, AGGREGATE_ELEMENTS], "strides": [0, 0, AGGREGATE_ELEMENTS, 1], "bytes": COLUMN_BYTES})
                # Drain each MM2S/S2MM token before reuse of all three BD IDs.
                dma_wait(*input_host_fifos, *weight_host_fifos, *output_host_fifos)

        ctx.module.operation.verify()
        emitted = str(ctx.module) + "\n"
    receipt = {
        "format": "halogen-native-hidden-vector-source-schedule-v1", "device": "npu2",
        "workers": 32, "finite_calls": CALLS, "output_rows_per_worker": 80,
        "weight_chunks_per_worker_per_call": 50, "packed_order": "column,group,Kchunk,worker,row16,pair8,component2,lane16",
        "weight_layout": "row16,pair8,component2,lane16", "input_layout": "stream4,Kchunk10,pair8,component2,lane16",
        "wire_input_layout": "canonical-stream4-K2560", "vector_alignment_bytes": 64,
        "host_input_transpose_per_call": True, "weight_pair_reused_across_streams": 4,
        "lane_k": "Kchunk*256+lane*16+pair*2+[0,1]", "dot2": "two sequential native BF16 MACs",
        "persistent_lane_adds": 10, "xor_reduction": [8, 4, 2, 1],
        "decode": "exact-dyadic-affine-rn32-rnbf16-once", "per_projection_decoder_calls": 0,
        "chunk_bytes": CHUNK_BYTES, "aggregate_bytes": AGGREGATE_BYTES,
        "declared_worker_bytes": 45312, "declared_stack_bytes": 4096,
        "declared_memtile_payload_bytes": 87040, "actual_allocations_verified": False,
        "runtime_launches_per_call": 1, "transfers": transfers,
        "ddr_weight_bytes": WEIGHT_BYTES, "ddr_input_bytes": 163840,
        "ddr_output_bytes": 20480, "ddr_total_bytes": 13291520,
        "mlir_sha256": hashlib.sha256(emitted.encode()).hexdigest(),
    }
    return emitted, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mlir", type=Path, required=True)
    parser.add_argument("--abi", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    args = parser.parse_args()
    installed = version("mlir-aie")
    if installed.split("+", 1)[0] != "1.3.4":
        parser.error(f"MLIR-AIE1.3.4 required, found {installed}")
    if len({p.resolve() for p in (args.mlir, args.abi, args.schedule)}) != 3:
        parser.error("output files must differ")
    emitted, receipt = generate()
    abi = {
        "format": "halogen-native-hidden-vector-v1", "device": "npu2", "kernel": "MLIR_AIE",
        "mlir_aie_version": installed, "input_bytes": "20480", "output_bytes": "20480",
        "weight_bytes": "13107200", "raw_weight_bytes": "6963200", "core_calls": "64", "workers": "32",
        "stack_bytes": "4096", "runtime_buffers": "3", "weight_arg": "3",
        "input_arg": "4", "output_arg": "5", "instruction_count_unit": "uint32_words",
        "numeric_schedule": "16lane-sequential2mac-block16-xor8,4,2,1",
        "weight_layout": "row16,pair8,component2,lane16", "input_layout": "stream4,Kchunk10,pair8,component2,lane16",
        "wire_input_layout": "canonical-stream4-K2560", "vector_alignment_bytes": "64",
        "weight_decode": "exact-dyadic-affine-rn32-rnbf16-once", "mlir_sha256": receipt["mlir_sha256"],
    }
    for path in (args.mlir, args.abi, args.schedule):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.mlir.write_text(emitted, encoding="utf-8", newline="\n")
    args.abi.write_text("".join(f"{k}={v}\n" for k, v in abi.items()), encoding="utf-8", newline="\n")
    args.schedule.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote full H32-worker MLIR, ABI and schedule/traffic receipts to {args.mlir.parent.resolve()}")


if __name__ == "__main__":
    main()
