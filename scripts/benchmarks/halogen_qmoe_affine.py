"""Bounded CPU q4c-v2 -> AMD QMoE affine INT4 preparation.

No file reads, native library imports, providers or device calls occur here.
Callers supply one expert's decoded FP32 rows, or its already-read q4c
codebook/codes/scales. q4c-v2 means codebook[nibble] * FP16 scale per32 K
values, as in the unchanged hgn_q4c_slice.py decoder. These codes cannot be
passed straight to AMD's nibble-8 formatter when the codebook is nonuniform.

AMD inputs: UINT8[N,K/2] weights (low=even K), FLOAT32[N,K/32] scales,
UINT8[N,ceil((K/32)/2)] zero points (low=even block), FLOAT32[N] zero bias.
Affine reconstruction is (unsigned_code - unsigned_zero_point) * scale.
Quantization is approximate, includes zero in each block's range, and uses
nearest-even rounding. Diagnostics exclude DD BF16 scale rounding and NPU
arithmetic; draft quality must be measured through native target verification.

Gate/up layouts are explicit data choices. This module chooses no runtime
activation, alpha, beta or clipping policy; it does not assume GPT-OSS SwiGLU.
"""
from dataclasses import dataclass
import hashlib
import math

import numpy as np


BLOCK_SIZE = 32
MAX_ROWS = 4096
MAX_WIDTH = 4096
MAX_DECODED_BYTES = 64 * 1024**2
ROW_LAYOUTS = {"linear", "gate_up_concatenated", "gate_up_interleaved"}
GATE_UP_LAYOUTS = {"concatenated", "interleaved"}


@dataclass(frozen=True)
class AffineInt4Rows:
    weights: np.ndarray
    scales: np.ndarray
    zero_points: np.ndarray
    bias: np.ndarray
    row_layout: str
    diagnostics: dict

    @property
    def N(self):
        return self.weights.shape[0]

    @property
    def K(self):
        return self.weights.shape[1] * 2

    @property
    def block_size(self):
        return BLOCK_SIZE


@dataclass(frozen=True)
class AffineInt4Expert:
    gate_up: AffineInt4Rows
    down: AffineInt4Rows
    source_gate_up_layout: str
    packed_gate_up_layout: str


def _shape_guard(n, k):
    if type(n) is not int or type(k) is not int or not 0 < n <= MAX_ROWS:
        raise ValueError("requires one bounded 2D row matrix")
    if not 0 < k <= MAX_WIDTH or k % BLOCK_SIZE:
        raise ValueError("K must be a positive multiple of32, at most4096")
    if n * k * 4 > MAX_DECODED_BYTES:
        raise ValueError("decoded expert rows exceed the64MiB limit")


def _decoded_guard(rows):
    if not isinstance(rows, np.ndarray) or rows.dtype != np.float32 or rows.ndim != 2:
        raise ValueError("requires decoded FP32[N,K]; expert banks and implicit dtype casts are forbidden")
    _shape_guard(*rows.shape)
    if not np.isfinite(rows).all():
        raise ValueError("decoded rows must be finite")


def _layout_guard(layout, n):
    if not isinstance(layout, str) or layout not in ROW_LAYOUTS:
        raise ValueError("row_layout must explicitly identify linear or gate/up rows")
    if layout != "linear" and n % 2:
        raise ValueError("gate/up row count must be even")


def quantize_rows(decoded, *, row_layout):
    """Quantize one FP32 matrix; retain only row-sized FP64 working buffers.

    Use row_layout='linear' for down weights. Gate/up callers must declare
    'gate_up_concatenated' or 'gate_up_interleaved'; this function preserves
    that order. Use reorder_gate_up_rows explicitly to change it.
    """
    _decoded_guard(decoded)
    n, k = decoded.shape
    _layout_guard(row_layout, n)
    blocks = k // BLOCK_SIZE
    weights = np.empty((n, k // 2), dtype=np.uint8)
    scales = np.empty((n, blocks), dtype=np.float32)
    zero_points = np.zeros((n, (blocks + 1) // 2), dtype=np.uint8)
    bias = np.zeros(n, dtype=np.float32)
    smallest_scale = np.nextafter(np.float32(0), np.float32(1))
    max_error = abs_error_sum = error_squared = source_squared = max_weight = 0.0
    clipped = zero_blocks = 0
    for row in range(n):
        source = decoded[row].astype(np.float64).reshape(blocks, BLOCK_SIZE)
        lo = np.minimum(source.min(axis=1), 0.0)
        hi = np.maximum(source.max(axis=1), 0.0)
        raw_scale = (hi - lo) / 15.0
        all_zero = raw_scale == 0
        row_scales = raw_scale.astype(np.float32)
        row_scales[~all_zero] = np.maximum(row_scales[~all_zero], smallest_scale)
        row_scales[all_zero] = 1.0
        if not np.isfinite(row_scales).all() or not (row_scales > 0).all():
            raise ValueError("unrepresentable affine FP32 scales")
        stored_scale = row_scales.astype(np.float64)
        zp = np.clip(np.rint(-lo / stored_scale), 0, 15).astype(np.uint8)
        rounded = np.rint(source / stored_scale[:, None] + zp[:, None])
        clipped += int(np.count_nonzero((rounded < 0) | (rounded > 15)))
        q = np.clip(rounded, 0, 15).astype(np.uint8)
        codes = q.reshape(k)
        weights[row] = codes[0::2] | (codes[1::2] << 4)
        scales[row] = row_scales
        zero_points[row, : (blocks + 1) // 2] = zp[0::2]
        zero_points[row, : blocks // 2] |= zp[1::2] << 4
        # Compare the same FP32 reconstruction that reconstruct_rows returns.
        with np.errstate(over="ignore", invalid="ignore"):
            restored = ((q.astype(np.int16) - zp[:, None].astype(np.int16)) * stored_scale[:, None]).astype(np.float32)
        if not np.isfinite(restored).all():
            raise ValueError("affine FP32 reconstruction would be non-finite")
        error = restored.astype(np.float64) - source
        absolute = np.abs(error)
        max_error = max(max_error, float(absolute.max()))
        max_weight = max(max_weight, float(np.abs(source).max()))
        abs_error_sum += float(absolute.sum())
        error_squared += float(np.square(error).sum())
        source_squared += float(np.square(source).sum())
        zero_blocks += int(np.count_nonzero(all_zero))
    count = n * k
    diagnostics = {
        "N": n, "K": k, "block_size": BLOCK_SIZE, "row_layout": row_layout,
        "rounding": "nearest_even", "max_abs_error": max_error,
        "mean_abs_error": abs_error_sum / count,
        "rmse": math.sqrt(error_squared / count),
        "relative_l2_error": math.sqrt(error_squared / source_squared) if source_squared else 0.0,
        "max_abs_weight": max_weight, "clipped_elements": clipped, "all_zero_blocks": zero_blocks,
        "input_fp32_bytes": decoded.nbytes,
        "output_bytes": weights.nbytes + scales.nbytes + zero_points.nbytes + bias.nbytes,
        "error_scope": "affine FP32 reconstruction; excludes DD BF16 scale rounding and NPU arithmetic",
        "activation_policy": "unset; caller must verify native gate/up activation and clipping semantics",
    }
    return AffineInt4Rows(weights, scales, zero_points, bias, row_layout, diagnostics)


def reconstruct_rows(affine):
    """Reconstruct a bounded affine matrix for CPU diagnostics, without DD."""
    if not isinstance(affine, AffineInt4Rows):
        raise ValueError("requires AffineInt4Rows")
    if not isinstance(affine.weights, np.ndarray) or affine.weights.dtype != np.uint8 or affine.weights.ndim != 2:
        raise ValueError("invalid packed UINT8 weight rows")
    n, packed_k = affine.weights.shape
    k = packed_k * 2
    _shape_guard(n, k)
    _layout_guard(affine.row_layout, n)
    blocks = k // BLOCK_SIZE
    if not isinstance(affine.scales, np.ndarray) or affine.scales.dtype != np.float32 or affine.scales.shape != (n, blocks):
        raise ValueError("invalid affine scales")
    if not np.isfinite(affine.scales).all() or not (affine.scales > 0).all():
        raise ValueError("affine scales must be positive and finite")
    if not isinstance(affine.zero_points, np.ndarray) or affine.zero_points.dtype != np.uint8 or affine.zero_points.shape != (n, (blocks + 1) // 2):
        raise ValueError("invalid packed affine zero points")
    if blocks % 2 and np.any(affine.zero_points[:, -1] & 0xF0):
        raise ValueError("unused zero-point high nibble must be zero")
    if not isinstance(affine.bias, np.ndarray) or affine.bias.dtype != np.float32 or affine.bias.shape != (n,) or np.any(affine.bias != 0):
        raise ValueError("requires zero FLOAT32 bias")
    result = np.empty((n, k), dtype=np.float32)
    for row in range(n):
        codes = np.empty(k, dtype=np.int16)
        codes[0::2] = affine.weights[row] & 15
        codes[1::2] = affine.weights[row] >> 4
        zp = np.empty(blocks, dtype=np.int16)
        zp[0::2] = affine.zero_points[row] & 15
        zp[1::2] = affine.zero_points[row, : blocks // 2] >> 4
        with np.errstate(over="ignore", invalid="ignore"):
            result[row] = ((codes.reshape(blocks, BLOCK_SIZE) - zp[:, None]) * affine.scales[row, :, None].astype(np.float64)).reshape(k)
    if not np.isfinite(result).all():
        raise ValueError("affine FP32 reconstruction would be non-finite")
    return result


def quantize_q4c_rows(codebook, packed_codes, block_scales, *, row_layout):
    """Convert already-read q4c-v2 components; performs no checkpoint I/O.

    codebook is FLOAT32[16], packed_codes is UINT8[N,K/2], and source
    block_scales is FLOAT16[N,K/32]. File headers/alignment are the caller's
    responsibility; hgn_q4c_slice.decode_rows remains the file decoder.
    """
    if not isinstance(codebook, np.ndarray) or codebook.dtype != np.float32 or codebook.shape != (16,) or not np.isfinite(codebook).all():
        raise ValueError("q4c requires a finite16-entry FLOAT32 codebook")
    if not isinstance(packed_codes, np.ndarray) or packed_codes.dtype != np.uint8 or packed_codes.ndim != 2:
        raise ValueError("q4c requires packed UINT8[N,K/2] codes")
    n, packed_k = packed_codes.shape
    k = packed_k * 2
    _shape_guard(n, k)
    _layout_guard(row_layout, n)
    blocks = k // BLOCK_SIZE
    if not isinstance(block_scales, np.ndarray) or block_scales.dtype != np.float16 or block_scales.shape != (n, blocks) or not np.isfinite(block_scales).all():
        raise ValueError("q4c requires finite FLOAT16[N,K/32] scales")
    decoded = np.empty((n, k), dtype=np.float32)
    for row in range(n):
        codes = np.empty(k, dtype=np.uint8)
        codes[0::2], codes[1::2] = packed_codes[row] & 15, packed_codes[row] >> 4
        with np.errstate(over="ignore", invalid="ignore"):
            decoded[row] = codebook[codes] * np.repeat(block_scales[row].astype(np.float32), BLOCK_SIZE)
    result = quantize_rows(decoded, row_layout=row_layout)
    result.diagnostics["source_encoding"] = "q4c_variant_2"
    result.diagnostics["q4c_codebook_sha256"] = hashlib.sha256(codebook.astype("<f4", copy=False).tobytes()).hexdigest()
    return result


def reorder_gate_up_rows(decoded, *, source_layout, target_layout):
    """Explicit [gate;up] <-> [g0,u0,g1,u1,...] row reorder only."""
    _decoded_guard(decoded)
    if not isinstance(source_layout, str) or not isinstance(target_layout, str) or source_layout not in GATE_UP_LAYOUTS or target_layout not in GATE_UP_LAYOUTS:
        raise ValueError("source_layout and target_layout must be concatenated or interleaved")
    n = decoded.shape[0]
    if n % 2:
        raise ValueError("gate/up row count must be even")
    if source_layout == target_layout:
        return np.ascontiguousarray(decoded)
    result = np.empty_like(decoded, order="C")
    half = n // 2
    if source_layout == "concatenated":
        result[0::2], result[1::2] = decoded[:half], decoded[half:]
    else:
        result[:half], result[half:] = decoded[0::2], decoded[1::2]
    return result


def quantize_expert(gate_up, down, *, source_gate_up_layout, packed_gate_up_layout,
                    width=2560, intermediate=640):
    """Prepare exactly one expert, with explicit gate/up row layout.

    Returns .gate_up and .down AffineInt4Rows. Pass their weights, bias,
    scales, zero_points to the official packer in that argument order.
    No expert ID selection, router policy or activation configuration occurs.
    """
    _decoded_guard(gate_up)
    _decoded_guard(down)
    if type(width) is not int or type(intermediate) is not int:
        raise ValueError("width and intermediate must be integer dimensions")
    _shape_guard(2 * intermediate, width)
    _shape_guard(width, intermediate)
    if gate_up.shape != (2 * intermediate, width) or down.shape != (width, intermediate):
        raise ValueError("gate/up and down must match the declared single-expert geometry")
    if gate_up.nbytes + down.nbytes > MAX_DECODED_BYTES:
        raise ValueError("combined decoded expert arrays exceed the64MiB limit")
    ordered = reorder_gate_up_rows(gate_up, source_layout=source_gate_up_layout, target_layout=packed_gate_up_layout)
    gate = quantize_rows(ordered, row_layout="gate_up_" + packed_gate_up_layout)
    return AffineInt4Expert(gate, quantize_rows(down, row_layout="linear"),
                           source_gate_up_layout, packed_gate_up_layout)
