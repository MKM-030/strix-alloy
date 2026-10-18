# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Losslessly rearrange original H store7/variant0 Q8 bytes; never decode weights.

This is a standalone standard-library program. It does not import NPU code or
read model files except the explicitly named original H matrix passed by owner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

ROWS = COLS = 2560
ROW_BYTES = 2720
WEIGHT_BYTES = ROWS * ROW_BYTES
COLUMNS = 8
GROUPS = 5
WORKERS = 4
K_CHUNKS = 10
TILE_ROWS = 16
K = 256
CHUNK_BYTES = 4352
COLUMN_BYTES = GROUPS * K_CHUNKS * WORKERS * CHUNK_BYTES
FORMAT = "halogen-native-hidden-pack-v1"


def chunk_index(column: int, group: int, kchunk: int, worker: int) -> int:
    if not (0 <= column < COLUMNS and 0 <= group < GROUPS and
            0 <= kchunk < K_CHUNKS and 0 <= worker < WORKERS):
        raise ValueError("chunk coordinates out of range")
    return (((column * GROUPS + group) * K_CHUNKS + kchunk) * WORKERS + worker)


def _check_size(blob: bytes) -> None:
    if len(blob) != WEIGHT_BYTES:
        raise ValueError(f"H matrix must be exactly {WEIGHT_BYTES} bytes")


def check_finite_metadata(raw: bytes) -> None:
    _check_size(raw)
    for row in range(ROWS):
        base = row * ROW_BYTES + COLS
        for word, in struct.iter_unpack("<H", raw[base:base + 160]):
            if word & 0x7C00 == 0x7C00:
                raise ValueError(f"nonfinite FP16 scale/bias at original row {row}")


def pack_weights(raw: bytes) -> bytes:
    check_finite_metadata(raw)
    output = bytearray(WEIGHT_BYTES)
    for column in range(COLUMNS):
        for group in range(GROUPS):
            for kchunk in range(K_CHUNKS):
                for worker in range(WORKERS):
                    chunk = chunk_index(column, group, kchunk, worker) * CHUNK_BYTES
                    first_row = (column * 20 + group * 4 + worker) * TILE_ROWS
                    for row in range(TILE_ROWS):
                        base = (first_row + row) * ROW_BYTES
                        codes = base + kchunk * K
                        meta = base + COLS + kchunk * 16
                        output[chunk + row * K:chunk + (row + 1) * K] = raw[codes:codes + K]
                        output[chunk + 4096 + row * 16:chunk + 4096 + (row + 1) * 16] = raw[meta:meta + 16]
    return bytes(output)


def unpack_weights(packed: bytes) -> bytes:
    _check_size(packed)
    output = bytearray(WEIGHT_BYTES)
    for column in range(COLUMNS):
        for group in range(GROUPS):
            for kchunk in range(K_CHUNKS):
                for worker in range(WORKERS):
                    chunk = chunk_index(column, group, kchunk, worker) * CHUNK_BYTES
                    first_row = (column * 20 + group * 4 + worker) * TILE_ROWS
                    for row in range(TILE_ROWS):
                        base = (first_row + row) * ROW_BYTES
                        codes = base + kchunk * K
                        meta = base + COLS + kchunk * 16
                        output[codes:codes + K] = packed[chunk + row * K:chunk + (row + 1) * K]
                        output[meta:meta + 16] = packed[chunk + 4096 + row * 16:chunk + 4096 + (row + 1) * 16]
    return bytes(output)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--raw-sha256", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    expected = args.raw_sha256.lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        parser.error("--raw-sha256 must be a pinned 64-digit hexadecimal digest")
    if args.out_dir.exists():
        parser.error("--out-dir must be fresh")
    started = time.perf_counter_ns()
    # Reject an accidentally named full checkpoint before allocating/reading it.
    # The bounded read plus extent recheck also catches changes after stat().
    if args.raw.stat().st_size != WEIGHT_BYTES:
        parser.error(f"--raw must be exactly {WEIGHT_BYTES} bytes")
    with args.raw.open("rb") as source:
        raw = source.read(WEIGHT_BYTES + 1)
    if len(raw) != WEIGHT_BYTES:
        parser.error("original H extent changed during bounded read")
    if sha(raw) != expected:
        parser.error("original H SHA256 differs from pinned digest")
    packed = pack_weights(raw)
    reconstructed = unpack_weights(packed)
    if reconstructed != raw or sha(reconstructed) != expected:
        raise RuntimeError("inverse reconstruction failed; no packed artifact published")
    elapsed_ns = time.perf_counter_ns() - started
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / "weights.bin").write_bytes(packed)
    receipt = {
        "format": FORMAT, "shape": [ROWS, COLS], "store": 7, "variant": 0,
        "original_row_bytes": ROW_BYTES, "weight_bytes": WEIGHT_BYTES,
        "raw_sha256": expected, "packed_sha256": sha(packed),
        "reconstructed_sha256": sha(reconstructed), "inverse_bitwise_equal": True,
        "packed_order": ["column8", "output_group5", "K_chunk10", "worker4", "bytes4352"],
        "codes_order": "row16,K256", "metadata_order": "row16,group4,fp16(scale,bias)",
        "chunk_bytes": CHUNK_BYTES, "column_bytes": COLUMN_BYTES,
        "output_row_tile": "column*20+output_group*4+worker", "finite_fp16_metadata": True,
        "source_sha256": sha(Path(__file__).read_bytes()),
        "packing_inverse_and_validation_ns": elapsed_ns,
    }
    (args.out_dir / "pack-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    # Simple strict sidecar consumed by native host without a permissive JSON parser.
    (args.out_dir / "weights.abi").write_text(
        f"format={FORMAT}\nweight_bytes={WEIGHT_BYTES}\n"
        f"raw_sha256={expected}\npacked_sha256={sha(packed)}\n"
        f"reconstructed_sha256={expected}\ninverse_bitwise_equal=true\nfinite_fp16_metadata=true\n",
        encoding="utf-8", newline="\n")
    print(json.dumps({"packed": str((args.out_dir / "weights.bin").resolve()), **receipt}))


if __name__ == "__main__":
    main()
