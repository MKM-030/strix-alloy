# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Decode original H once exactly, then losslessly rearrange all BF16 words.

Uses the copied reviewed integer-dyadic numerical reference. No device/compiler
imports. Only the owner's explicit7MB original H path may be read at CLI use.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from numeric_reference import decode_q8_numpy

ROWS = COLS = 2560
RAW_BYTES = ROWS * 2720
WEIGHT_BYTES = ROWS * COLS * 2
COLUMNS, GROUPS, K_CHUNKS, WORKERS = 8, 5, 10, 4
CHUNK_BYTES, COLUMN_BYTES = 8192, 1638400
FORMAT = "halogen-native-hidden-decoded-pack-v1"
DECODE = "exact-dyadic-affine-rn32-rnbf16-once"


def chunk_index(column: int, group: int, kchunk: int, worker: int) -> int:
    if not (0 <= column < COLUMNS and 0 <= group < GROUPS and
            0 <= kchunk < K_CHUNKS and 0 <= worker < WORKERS):
        raise ValueError("chunk coordinates out of range")
    return (((column * GROUPS + group) * K_CHUNKS + kchunk) * WORKERS + worker)


def check_decoded(words: np.ndarray) -> None:
    if not isinstance(words, np.ndarray) or words.shape != (ROWS, COLS) or words.dtype.kind != "u" or words.dtype.itemsize != 2:
        raise ValueError("decoded weights must be full2560×2560 unsigned BF16 words")
    if np.any((words & 0x7F80) == 0x7F80):
        raise ValueError("nonfinite decoded BF16 weight")


def pack_decoded(words: np.ndarray) -> bytes:
    check_decoded(words)
    # [column,group,worker,row16,Kchunk,K256] → runtime streamed order.
    arranged = words.reshape(COLUMNS, GROUPS, WORKERS, 16, K_CHUNKS, 256)
    arranged = arranged.transpose(0, 1, 4, 2, 3, 5)
    return np.ascontiguousarray(arranged, dtype="<u2").tobytes()


def unpack_decoded(packed: bytes) -> np.ndarray:
    if len(packed) != WEIGHT_BYTES:
        raise ValueError(f"packed decoded H must be exactly {WEIGHT_BYTES} bytes")
    words = np.frombuffer(packed, dtype="<u2").reshape(COLUMNS, GROUPS, K_CHUNKS, WORKERS, 16, 256)
    words = words.transpose(0, 1, 3, 4, 2, 5).reshape(ROWS, COLS)
    result = np.ascontiguousarray(words, dtype="<u2")
    check_decoded(result)
    return result


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
        parser.error("--raw-sha256 needs a pinned64-digit hexadecimal digest")
    if args.out_dir.exists():
        parser.error("--out-dir must be fresh")
    started = time.perf_counter_ns()
    if args.raw.stat().st_size != RAW_BYTES:
        parser.error(f"--raw must be exactly {RAW_BYTES} bytes before opening")
    with args.raw.open("rb") as source:
        raw = source.read(RAW_BYTES + 1)
    if len(raw) != RAW_BYTES:
        parser.error("original H extent changed during bounded read")
    if sha(raw) != expected:
        parser.error("original H differs from pinned SHA256")
    read_done = time.perf_counter_ns()
    # Only affine conversion; no fitting, calibration, new quantization or math
    # based on input fixtures. All6,553,600 original weight values are preserved
    # under the specified FP32 FMA then BF16 RNE contract.
    decoded = decode_q8_numpy(raw)
    check_decoded(decoded)
    decode_done = time.perf_counter_ns()
    decoded_bytes = decoded.astype("<u2", copy=False).tobytes()
    packed = pack_decoded(decoded)
    reconstructed = unpack_decoded(packed).tobytes()
    decoded_sha = sha(decoded_bytes)
    if reconstructed != decoded_bytes or sha(reconstructed) != decoded_sha:
        raise RuntimeError("decoded-word inverse proof failed before publication")
    pack_done = time.perf_counter_ns()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / "weights.bin").write_bytes(packed)
    receipt = {
        "format": FORMAT, "shape": [ROWS, COLS], "original_store": 7, "original_variant": 0,
        "raw_weight_bytes": RAW_BYTES, "weight_bytes": WEIGHT_BYTES, "raw_sha256": expected,
        "decode": DECODE, "decoded_elements": ROWS * COLS, "decode_occurs_per_projection": False,
        "decoded_row_major_sha256": decoded_sha, "packed_sha256": sha(packed),
        "reconstructed_decoded_sha256": sha(reconstructed), "inverse_decoded_bitwise_equal": True,
        "original_Q8_reconstruction_from_BF16_claimed": False, "finite_bf16_weights": True,
        "packed_order": ["column8", "output_group5", "K_chunk10", "worker4", "row16", "K256"],
        "chunk_bytes": CHUNK_BYTES, "aggregate_bytes": 32768, "column_bytes": COLUMN_BYTES,
        "output_row_tile": "column*20+output_group*4+worker", "source_sha256": sha(Path(__file__).read_bytes()),
        "numeric_reference_sha256": sha(Path(__file__).with_name("numeric_reference.py").read_bytes()),
        "original_read_and_hash_ns": read_done - started, "one_time_exact_decode_ns": decode_done - read_done,
        "decoded_pack_and_inverse_validation_ns": pack_done - decode_done,
        "total_preparation_ns": pack_done - started,
    }
    (args.out_dir / "pack-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    fields = {
        "format": FORMAT, "raw_weight_bytes": str(RAW_BYTES), "weight_bytes": str(WEIGHT_BYTES),
        "raw_sha256": expected, "packed_sha256": sha(packed), "decoded_sha256": decoded_sha,
        "reconstructed_sha256": decoded_sha, "inverse_decoded_bitwise_equal": "true",
        "finite_bf16_weights": "true", "decode": DECODE,
    }
    (args.out_dir / "weights.abi").write_text("".join(f"{k}={v}\n" for k, v in fields.items()), encoding="utf-8", newline="\n")
    print(json.dumps({"packed": str((args.out_dir / "weights.bin").resolve()), **receipt}))


if __name__ == "__main__":
    main()
