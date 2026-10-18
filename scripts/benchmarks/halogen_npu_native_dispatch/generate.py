# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Generate one finite, synthetic npu2_1col design with MLIR-AIE 1.3.4.

This program writes source and an ABI sidecar. It does not compile or launch.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
from pathlib import Path

import numpy as np
from aie.dialects.aie import (
    AIEDevice, ObjectFifoPort, buffer, core, device,
    external_func, object_fifo, tile,
)
from aie.dialects.aiex import dma_wait, npu_dma_memcpy_nd, runtime_sequence
from aie.extras.context import mlir_mod_ctx
from aie.helpers.dialects.scf import _for as range_

COLS = 256
ROWS = 64
CORE_CALLS = 64
STACK_BYTES = 4096
MODES = ("control", "gemv-vector", "gemv-scalar")


def make_weights() -> np.ndarray:
    # This formula must match dispatch_contract::weight_value in contract.h.
    row = np.arange(ROWS, dtype=np.int32)[:, None]
    col = np.arange(COLS, dtype=np.int32)[None, :]
    return np.ascontiguousarray((row * 7 + col * 3) % 17 - 8, dtype=np.int16)


def generate(mode: str) -> tuple[str, str]:
    input_type = np.ndarray[(COLS,), np.dtype[np.int16]]
    output_type = np.ndarray[(ROWS,), np.dtype[np.int32]]
    weight_type = np.ndarray[(ROWS, COLS), np.dtype[np.int16]]
    weights = make_weights()
    weight_hash = hashlib.sha256(weights.astype("<i2").tobytes()).hexdigest()

    with mlir_mod_ctx() as ctx:
        @device(AIEDevice.npu2_1col)
        def design():
            shim = tile(0, 0)
            compute = tile(0, 2)
            in_fifo = object_fifo("of_in", shim, [compute], 2, input_type)
            out_fifo = object_fifo("of_out", compute, [shim], 2, output_type)
            if mode == "control":
                kernel = external_func(
                    "dispatch_control", inputs=[input_type, output_type],
                    outputs=[], link_with="kernels.o",
                )
                tile_weights = None
            else:
                tile_weights = buffer(
                    compute, weight_type, name="static_weight",
                    initial_value=weights,
                )
                entry = "dispatch_gemv_vector" if mode == "gemv-vector" else "dispatch_gemv_scalar"
                kernel = external_func(
                    entry, inputs=[weight_type, input_type, output_type],
                    outputs=[], link_with="kernels.o",
                )

            @core(compute, stack_size=STACK_BYTES)
            def finite_core():
                for _ in range_(CORE_CALLS):
                    input_object = in_fifo.acquire(ObjectFifoPort.Consume, 1)
                    output_object = out_fifo.acquire(ObjectFifoPort.Produce, 1)
                    if mode == "control":
                        kernel(input_object, output_object)
                    else:
                        kernel(tile_weights, input_object, output_object)
                    in_fifo.release(ObjectFifoPort.Consume, 1)
                    out_fifo.release(ObjectFifoPort.Produce, 1)

            # Two runtime buffers only: bo0 = input, bo1 = output. Each launch
            # transfers exactly one input vector and one output vector.
            @runtime_sequence(input_type, output_type, sym_name="dispatch")
            def sequence(input_host, output_host):
                npu_dma_memcpy_nd(out_fifo, 1, output_host, sizes=[1, 1, 1, ROWS])
                npu_dma_memcpy_nd(
                    in_fifo, 0, input_host, sizes=[1, 1, 1, COLS], issue_token=True,
                )
                # Consume both completion tokens before these BD IDs are reused
                # by the next persistent-host launch.
                dma_wait(in_fifo, out_fifo)

        ctx.module.operation.verify()
        return str(ctx.module) + "\n", weight_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--mlir", type=Path, required=True)
    parser.add_argument("--abi", type=Path, required=True)
    args = parser.parse_args()
    installed_version = version("mlir-aie")
    if installed_version.split("+", 1)[0] != "1.3.4":
        parser.error(f"MLIR-AIE 1.3.4 is required; installed {installed_version}")
    mlir, weight_hash = generate(args.mode)
    if args.mlir.resolve() == args.abi.resolve():
        parser.error("--mlir and --abi must be different files")
    args.mlir.parent.mkdir(parents=True, exist_ok=True)
    args.abi.parent.mkdir(parents=True, exist_ok=True)
    args.mlir.write_text(mlir, encoding="utf-8", newline="\n")
    sidecar = {
        "format": "halogen-native-dispatch-v1",
        "mode": args.mode,
        "device": "npu2_1col",
        "kernel": "MLIR_AIE",
        "mlir_aie_version": installed_version,
        "input_elements": str(COLS), "input_bytes": str(COLS * 2),
        "output_elements": str(ROWS), "output_bytes": str(ROWS * 4),
        "weight_bytes": str(0 if args.mode == "control" else ROWS * COLS * 2),
        "core_calls": str(CORE_CALLS), "stack_bytes": str(STACK_BYTES),
        "instruction_count_unit": "uint32_words",
        "runtime_buffers": "2", "input_arg": "3", "output_arg": "4",
        "weight_formula": "(row*7+col*3)%17-8",
        "input_formula": "col==0?call-32:(col*5+call*7)%23-11",
        "weight_sha256": weight_hash if args.mode != "control" else "none",
        "mlir_sha256": hashlib.sha256(mlir.encode("utf-8")).hexdigest(),
    }
    args.abi.write_text(
        "".join(f"{key}={value}\n" for key, value in sidecar.items()),
        encoding="utf-8", newline="\n",
    )
    print(f"Wrote {args.mlir.resolve()} and {args.abi.resolve()}")


if __name__ == "__main__":
    main()
