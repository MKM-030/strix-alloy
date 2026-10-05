# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Losslessly permute an explicitly pinned prepared decoded H payload.

No original Q8 reads, affine decoder, compiler, or runtime imports. Canonical
input helpers define the same word-only permutation used by the native host.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np

ROWS = COLS = 2560
RAW_BYTES = ROWS * 2720
WEIGHT_BYTES = ROWS * COLS * 2
COLUMNS, GROUPS, K_CHUNKS, WORKERS = 8, 5, 10, 4
CHUNK_BYTES, COLUMN_BYTES = 8192, 1638400
FORMAT = "halogen-native-hidden-vector-pack-v1"
SOURCE_FORMAT = "halogen-native-hidden-decoded-pack-v1"
DECODE = "exact-dyadic-affine-rn32-rnbf16-once"
WEIGHT_LAYOUT = "row16,pair8,component2,lane16"
INPUT_LAYOUT = "stream4,Kchunk10,pair8,component2,lane16"
VECTOR_ALIGNMENT_BYTES = 64


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
    # Canonical K256 = [lane16,pair8,component2]; only word order changes.
    arranged = words.reshape(COLUMNS, GROUPS, WORKERS, 16, K_CHUNKS, 16, 8, 2)
    arranged = arranged.transpose(0, 1, 4, 2, 3, 6, 7, 5)
    return np.ascontiguousarray(arranged, dtype="<u2").tobytes()


def unpack_decoded(packed: bytes) -> np.ndarray:
    if len(packed) != WEIGHT_BYTES:
        raise ValueError(f"packed decoded H must be exactly {WEIGHT_BYTES} bytes")
    words = np.frombuffer(packed, dtype="<u2").reshape(COLUMNS, GROUPS, K_CHUNKS, WORKERS, 16, 8, 2, 16)
    words = words.transpose(0, 1, 3, 4, 2, 7, 5, 6).reshape(ROWS, COLS)
    result = np.ascontiguousarray(words, dtype="<u2")
    check_decoded(result)
    return result


def unpack_source_decoded(packed: bytes) -> np.ndarray:
    if len(packed) != WEIGHT_BYTES:
        raise ValueError("prepared decoded source extent mismatch")
    words = np.frombuffer(packed, dtype="<u2").reshape(COLUMNS, GROUPS, K_CHUNKS, WORKERS, 16, 256)
    result = np.ascontiguousarray(words.transpose(0, 1, 3, 4, 2, 5).reshape(ROWS, COLS), dtype="<u2")
    check_decoded(result)
    return result


def weight_pair_offset(row: int, pair: int) -> int:
    if not (0 <= row < 16 and 0 <= pair < 8):
        raise ValueError("weight vector coordinates out of range")
    return (row * 8 + pair) * 32


def input_pair_offset(stream: int, kchunk: int, pair: int) -> int:
    if not (0 <= stream < 4 and 0 <= kchunk < K_CHUNKS and 0 <= pair < 8):
        raise ValueError("input vector coordinates out of range")
    return ((stream * K_CHUNKS + kchunk) * 8 + pair) * 32


def pack_inputs(words: np.ndarray) -> bytes:
    if not isinstance(words, np.ndarray) or words.shape != (4, COLS) or words.dtype.kind != "u" or words.dtype.itemsize != 2:
        raise ValueError("canonical input must be unsigned BF16 [4,2560] words")
    if np.any((words & 0x7F80) == 0x7F80):
        raise ValueError("nonfinite input word")
    return np.ascontiguousarray(words.reshape(4, K_CHUNKS, 16, 8, 2).transpose(0, 1, 3, 4, 2), dtype="<u2").tobytes()


def unpack_inputs(packed: bytes) -> np.ndarray:
    if len(packed) != 20480:
        raise ValueError("vector input extent mismatch")
    words = np.frombuffer(packed, dtype="<u2").reshape(4, K_CHUNKS, 8, 2, 16)
    return np.ascontiguousarray(words.transpose(0, 1, 4, 2, 3).reshape(4, COLS), dtype="<u2")


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoded-packed", type=Path, required=True)
    parser.add_argument("--decoded-weights-abi", type=Path, required=True)
    parser.add_argument("--decoded-packed-sha256", required=True)
    parser.add_argument("--raw-sha256", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    expected = args.raw_sha256.lower()
    source_sha = args.decoded_packed_sha256.lower()
    for value in (expected, source_sha):
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            parser.error("raw and prepared decoded SHA pins need64 hexadecimal digits")
    if args.out_dir.exists():
        parser.error("--out-dir must be fresh")
    started = time.perf_counter_ns()
    if args.decoded_packed.stat().st_size != WEIGHT_BYTES:
        parser.error(f"prepared decoded H must be exactly {WEIGHT_BYTES} bytes before opening")
    if args.decoded_weights_abi.stat().st_size > 65536:
        parser.error("prepared source ABI too large")
    with args.decoded_packed.open("rb") as source:
        prepared = source.read(WEIGHT_BYTES + 1)
    with args.decoded_weights_abi.open("rb") as source:
        source_abi_bytes = source.read(65537)
    if len(prepared) != WEIGHT_BYTES or len(source_abi_bytes) > 65536:
        parser.error("prepared source extent changed during bounded read")
    if sha(prepared) != source_sha:
        parser.error("prepared decoded H differs from pinned SHA256")
    source_abi = {}
    for line in source_abi_bytes.decode("ascii").splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or key in source_abi:
            parser.error("malformed or duplicate prepared source ABI field")
        source_abi[key] = value
    required = {"format": SOURCE_FORMAT, "raw_weight_bytes": str(RAW_BYTES), "weight_bytes": str(WEIGHT_BYTES),
                "raw_sha256": expected, "packed_sha256": source_sha, "inverse_decoded_bitwise_equal": "true",
                "finite_bf16_weights": "true", "decode": DECODE}
    if any(source_abi.get(key) != value for key, value in required.items()):
        parser.error("prepared decoded source ABI does not match its pins/format")
    decoded_sha = source_abi.get("decoded_sha256", "")
    if (len(decoded_sha) != 64 or any(c not in "0123456789abcdef" for c in decoded_sha)
            or decoded_sha != source_abi.get("reconstructed_sha256")):
        parser.error("prepared source decoded inverse SHA is invalid")
    read_done = time.perf_counter_ns()
    decoded = unpack_source_decoded(prepared)
    decode_done = time.perf_counter_ns()
    decoded_bytes = decoded.astype("<u2", copy=False).tobytes()
    if sha(decoded_bytes) != decoded_sha:
        parser.error("prepared source decoded row-major inverse SHA mismatch")
    packed = pack_decoded(decoded)
    reconstructed = unpack_decoded(packed).tobytes()
    if reconstructed != decoded_bytes or sha(reconstructed) != decoded_sha:
        raise RuntimeError("decoded-word inverse proof failed before publication")
    pack_done = time.perf_counter_ns()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / "weights.bin").write_bytes(packed)
    receipt = {
        "format": FORMAT, "shape": [ROWS, COLS], "original_store": 7, "original_variant": 0,
        "raw_weight_bytes": RAW_BYTES, "weight_bytes": WEIGHT_BYTES, "raw_sha256": expected,
        "decode": DECODE, "decoded_elements": ROWS * COLS, "decode_occurs_per_projection": False,
        "affine_decode_performed": False, "source_decoded_packed_sha256": source_sha,
        "source_decoded_abi_sha256": sha(source_abi_bytes), "source_decoded_format": SOURCE_FORMAT,
        "decoded_row_major_sha256": decoded_sha, "packed_sha256": sha(packed),
        "reconstructed_decoded_sha256": sha(reconstructed), "inverse_decoded_bitwise_equal": True,
        "original_Q8_reconstruction_from_BF16_claimed": False, "finite_bf16_weights": True,
        "packed_order": ["column8", "output_group5", "K_chunk10", "worker4", "row16", "pair8", "component2", "lane16"],
        "weight_layout": WEIGHT_LAYOUT, "input_layout": INPUT_LAYOUT, "vector_alignment_bytes": VECTOR_ALIGNMENT_BYTES,
        "chunk_bytes": CHUNK_BYTES, "aggregate_bytes": 32768, "column_bytes": COLUMN_BYTES,
        "output_row_tile": "column*20+output_group*4+worker", "source_sha256": sha(Path(__file__).read_bytes()),
        "numeric_reference_sha256": sha(Path(__file__).with_name("numeric_reference.py").read_bytes()),
        "prepared_read_and_hash_ns": read_done - started, "source_decoded_unpack_ns": decode_done - read_done,
        "vector_pack_and_inverse_validation_ns": pack_done - decode_done,
        "total_preparation_ns": pack_done - started,
    }
    (args.out_dir / "pack-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    fields = {
        "format": FORMAT, "raw_weight_bytes": str(RAW_BYTES), "weight_bytes": str(WEIGHT_BYTES),
        "raw_sha256": expected, "packed_sha256": sha(packed), "decoded_sha256": decoded_sha,
        "reconstructed_sha256": decoded_sha, "inverse_decoded_bitwise_equal": "true",
        "finite_bf16_weights": "true", "decode": DECODE,
        "weight_layout": WEIGHT_LAYOUT, "input_layout": INPUT_LAYOUT,
        "vector_alignment_bytes": str(VECTOR_ALIGNMENT_BYTES),
    }
    (args.out_dir / "weights.abi").write_text("".join(f"{k}={v}\n" for k, v in fields.items()), encoding="utf-8", newline="\n")
    print(json.dumps({"packed": str((args.out_dir / "weights.bin").resolve()), **receipt}))


if __name__ == "__main__":
    main()
