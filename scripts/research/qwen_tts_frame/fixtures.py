"""Native qwentts.cpp Base 0.6B first-frame dumps and host sampler inputs."""

from __future__ import annotations

import operator
from pathlib import Path
import struct

import numpy as np

_HIDDEN_SIZE = 1024
_MAX_PROMPT_ROWS = 4096
_ACOUSTIC_CODES = 15
_CODEBOOK_SIZE = 2048
_UINT32_MASK = (1 << 32) - 1
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1
_FLOAT_BYTES = 4


def _read_dump_last_row(path: Path, width: int, max_rows: int | None = None) -> np.ndarray:
    # debug.h stores rank and shape as int32, followed by row-major binary32.
    header = struct.Struct("<ii" if max_rows is None else "<iii")
    row_bytes = width * _FLOAT_BYTES
    with path.open("rb") as stream:
        encoded_shape = stream.read(header.size)
        if len(encoded_shape) != header.size:
            raise ValueError(f"{path.name}: truncated tensor header")

        dimensions = header.unpack(encoded_shape)
        if max_rows is None:
            rows = 1
            valid_shape = dimensions == (1, width)
        else:
            rank, rows, actual_width = dimensions
            valid_shape = rank == 2 and 1 <= rows <= max_rows and actual_width == width
        if not valid_shape:
            raise ValueError(f"{path.name}: unexpected tensor header {dimensions}")

        end = stream.seek(0, 2)
        if end != header.size + rows * row_bytes:
            raise ValueError(f"{path.name}: file length does not match tensor shape")

        stream.seek(end - row_bytes)
        payload = stream.read(row_bytes)
        if len(payload) != row_bytes:
            raise ValueError(f"{path.name}: truncated tensor row")
    return np.frombuffer(payload, dtype="<f4").astype(np.float32, copy=True)


def load_first_frame(directory: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Read the FP32 bridge row and 16 int32 IDs, starting with semantic c0."""
    directory = Path(directory)
    hidden = _read_dump_last_row(
        directory / "talker-hidden-prefill-final.bin", _HIDDEN_SIZE, _MAX_PROMPT_ROWS
    )
    if not np.isfinite(hidden).all():
        raise ValueError("talker-hidden-prefill-final.bin: nonfinite bridge value")

    codes = _read_dump_last_row(directory / "codes-step0.bin", 1 + _ACOUSTIC_CODES)
    # The 3072-entry semantic vocabulary reserves its last 1024 codes.
    # EOS is the sole sampling exception there and ends the frame before this dump.
    if (
        not np.isfinite(codes).all()
        or np.any(codes < 0)
        or np.any(codes >= _CODEBOOK_SIZE)
        or np.any(codes != np.trunc(codes))
    ):
        raise ValueError("codes-step0.bin: expected integer codec IDs in [0, 2048)")
    return hidden, codes.astype(np.int32)


def _int64(value: int) -> int:
    value = operator.index(value)
    if not _INT64_MIN <= value <= _INT64_MAX:
        raise OverflowError("seed and subsequence must fit a signed int64")
    return value


def philox_uniform(seed: int, subsequence: int) -> np.float32:
    """Compute the exact qwentts.cpp Philox draw with block counter zero."""
    seed = _int64(seed)
    subsequence = _int64(subsequence)
    key_low = seed & _UINT32_MASK
    key_high = (seed >> 32) & _UINT32_MASK
    x, y = 0, 0
    z = subsequence & _UINT32_MASK
    w = (subsequence >> 32) & _UINT32_MASK
    for _ in range(10):
        product_x = 0xD2511F53 * x
        product_z = 0xCD9E8D57 * z
        x = (product_z >> 32) ^ y ^ key_low
        y = product_z & _UINT32_MASK
        z = (product_x >> 32) ^ w ^ key_high
        w = product_x & _UINT32_MASK
        key_low = (key_low + 0x9E3779B9) & _UINT32_MASK
        key_high = (key_high + 0xBB67AE85) & _UINT32_MASK

    # Round the uint32 to FP32 before adding 0.5, as in philox.h.
    return (np.float32(x) + np.float32(0.5)) * np.float32(2.0**-32)


def acoustic_sampler_inputs(
    seed: int, subseq_base: int, temperature: float
) -> tuple[np.float32, np.ndarray]:
    """Return the uploaded acoustic temperature and 15 uniforms for one frame."""
    seed = _int64(seed)
    subseq_base = _int64(subseq_base)
    with np.errstate(over="ignore"):
        effective_temperature = np.float32(temperature)
    if not np.isfinite(effective_temperature):
        raise ValueError("temperature must be finite in FP32")
    if effective_temperature <= 0:
        return np.float32(1.0), np.zeros(_ACOUSTIC_CODES, dtype=np.float32)

    draws = np.array(
        [
            philox_uniform(seed, subseq_base + step)
            for step in range(1, _ACOUSTIC_CODES + 1)
        ],
        dtype=np.float32,
    )
    return effective_temperature, draws
