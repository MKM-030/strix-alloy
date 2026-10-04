# SPDX-License-Identifier: Apache-2.0
# Modified decoder-only adaptation of halogen-v2-tooling; see the companion
# hgn_ht_slice.NOTICE.md and hgn_ht_slice.LICENSE for attribution and license.
"""Bounded CPU decoding of HGN HT 16/0x1208 complete 128-row groups.

The trellis codebook/packing originate from the recovered 0.15.0 gfx1151
decoder. Synthetic parity with that NumPy reference does not establish
current-engine numerical equivalence. No native encoder or accelerator loads.
The caller owns checkpoint lineage, file identity and host reserve checks.
"""
import functools
import hashlib

import numpy as np


MAX_DECODED_BYTES = 64 * 1024**2
HT_VARIANT = 0x1208


@functools.lru_cache(maxsize=1)
def _codebook():
    state = np.arange(65536, dtype=np.uint32)
    hashed = state * np.uint32(0x83DCD12D)
    sums = sum((hashed >> shift) & 255 for shift in (0, 8, 16, 24))
    values = (sums + 0x6400).astype("<u2").view("<f2").astype(np.float32)
    multiplier, bias = np.array([0x1EEE, 0xC931], dtype="<u2").view("<f2").astype(np.float32)
    # One FP16 rounding after the affine operation, as in the pinned decoder.
    result = (values * multiplier + bias).astype(np.float16).astype(np.float32)
    result.flags.writeable = False
    return result


@functools.lru_cache(maxsize=1)
def _h128():
    matrix = np.array([[1.0]], np.float32)
    while matrix.shape[0] < 128:
        matrix = np.block([[matrix, matrix], [matrix, -matrix]])
    matrix = (matrix / np.sqrt(128)).astype(np.float32)
    matrix.flags.writeable = False
    return matrix


def _metadata(entry, store, variant, rank, dims=None, name=None):
    if not isinstance(entry, dict):
        raise ValueError("tensor entry must be an object")
    for key, expected in (("store", store), ("variant", variant), ("rank", rank)):
        if type(entry.get(key)) is not int or entry[key] != expected:
            raise ValueError(f"unsupported tensor {key}")
    shape = entry.get("dims")
    if (not isinstance(shape, (list, tuple)) or len(shape) != rank or
            any(type(value) is not int or value <= 0 for value in shape) or
            (dims is not None and list(shape) != list(dims))):
        raise ValueError("unsupported tensor dimensions")
    if not isinstance(entry.get("name"), str) or not entry["name"]:
        raise ValueError("tensor name must be nonempty")
    if name is not None and entry["name"] != name:
        raise ValueError("HT side-plane name differs from its weight")
    if any(type(entry.get(key)) is not int or entry[key] < 0 for key in ("offset", "size")):
        raise ValueError("invalid tensor byte bounds")
    return tuple(shape)


def _read_range(stream, entry, offset, length, receipts):
    if offset < entry["offset"] or offset + length > entry["offset"] + entry["size"]:
        raise ValueError("selected source range exceeds declared tensor")
    stream.seek(offset)
    payload = stream.read(length)
    if not isinstance(payload, (bytes, bytearray, memoryview)) or len(payload) != length:
        raise ValueError("truncated selected HT source range")
    receipts.append(dict(name=entry["name"], offset=offset, bytes=length,
                         sha256=hashlib.sha256(payload).hexdigest()))
    return payload


def _decode_group(payload, width, signs, scales):
    # Disk order [O/128, K/16, eight output tiles, 32 little-endian u32s].
    words = np.frombuffer(payload, "<u4").reshape(1, width // 16, 8, 32)
    codes = (words[..., None] >> np.arange(28, -1, -4, dtype=np.uint32)) & 15
    codes = codes.transpose(0, 2, 1, 3, 4).reshape(-1, 256).astype(np.uint8)
    codes = codes.astype(np.uint32)
    # Each 256-value trellis is cyclic: its final three nibbles seed the
    # first state's history. Reversing nibble order changes every state.
    states = sum(np.roll(codes, shift, axis=1) << (4 * shift) for shift in range(4))
    tiles = _codebook()[states]
    rotated = tiles.reshape(8, width // 16, 2, 16, 8).transpose(0, 3, 1, 2, 4).reshape(128, width)
    hadamard = _h128()
    value = np.matmul(hadamard, rotated.reshape(1, 128, width)).reshape(128, width // 128, 128)
    # Signed output scales follow the inverse output rotation. Zero scales
    # are valid and force corresponding decoded rows to zero.
    return (value @ hadamard).reshape(128, width) * scales[:, None] * signs[None, :]


def decode_rows(stream, entry, row_start, rows, suh_entry, svh_entry):
    """Return ``(FP32[rows,K], receipt)`` for aligned, complete HT row groups.

    All metadata is validated before any read. Only the selected packed groups,
    the entire input sign vector and selected output scales are read. The output
    is capped at 64 MiB; scratch is processed one 128-row group at a time.
    ``stream`` must support bounded binary ``seek``/``read`` operations.
    """
    output_rows, width = _metadata(entry, 16, HT_VARIANT, 2)
    if output_rows % 128 or width % 128 or entry["size"] != output_rows * width // 2:
        raise ValueError("HT requires multiples of 128 and exact O*K/2 payload bytes")
    if not entry["name"].endswith(".weight"):
        raise ValueError("HT tensor name must end in .weight")
    if (type(row_start) is not int or type(rows) is not int or row_start < 0 or rows <= 0 or
            row_start % 128 or rows % 128 or row_start + rows > output_rows):
        raise ValueError("HT slice must contain complete aligned 128-row groups")
    decoded_bytes = rows * width * 4
    if decoded_bytes > MAX_DECODED_BYTES:
        raise ValueError("decoded HT slice exceeds 64 MiB")
    root = entry["name"][:-len(".weight")]
    _metadata(suh_entry, 2, 0, 1, [width], root + ".suh")
    _metadata(svh_entry, 2, 0, 1, [output_rows], root + ".svh")
    if suh_entry["size"] != width * 2 or svh_entry["size"] != output_rows * 2:
        raise ValueError("HT side planes require exact FP16 vector byte lengths")
    spans = sorted((item["offset"], item["offset"] + item["size"])
                   for item in (entry, suh_entry, svh_entry))
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError("HT weight and side-plane byte ranges overlap")

    receipts = []
    signs_raw = _read_range(stream, suh_entry, suh_entry["offset"], width * 2, receipts)
    signs = np.frombuffer(signs_raw, "<f2").astype(np.float32)
    scales_raw = _read_range(stream, svh_entry, svh_entry["offset"] + row_start * 2, rows * 2, receipts)
    scales = np.frombuffer(scales_raw, "<f2").astype(np.float32)
    if not np.isfinite(signs).all() or not np.all(np.abs(signs) == 1) or not np.isfinite(scales).all():
        raise ValueError("HT requires finite +/-1 input signs and finite signed output scales")
    output = np.empty((rows, width), dtype="<f4")
    group_bytes = 128 * width // 2
    for first in range(0, rows, 128):
        offset = entry["offset"] + (row_start + first) * width // 2
        packed = _read_range(stream, entry, offset, group_bytes, receipts)
        output[first:first + 128] = _decode_group(packed, width, signs, scales[first:first + 128])
    if not np.isfinite(output).all():
        raise ValueError("nonfinite decoded HT weights")
    return output, dict(schema=1, tensor=entry["name"], shape=list(entry["dims"]),
                        row_start=row_start, rows=rows, decoded_shape=list(output.shape),
                        decoded_bytes=decoded_bytes, source_ranges=receipts,
                        source_bytes_read=sum(item["bytes"] for item in receipts),
                        decoded_sha256=hashlib.sha256(memoryview(output).cast("B")).hexdigest())
