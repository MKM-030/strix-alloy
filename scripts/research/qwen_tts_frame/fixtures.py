"""Native qwentts.cpp Base 0.6B frame dumps and host sampler inputs."""

from __future__ import annotations

import operator
from pathlib import Path
import struct

import numpy as np

_HIDDEN_SIZE = 1024
_MAX_PROMPT_ROWS = 4096
_ACOUSTIC_CODES = 15
_FRAME_CODES = 1 + _ACOUSTIC_CODES
_CODEBOOK_SIZE = 2048
_UINT32_MASK = (1 << 32) - 1
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1
_FLOAT_BYTES = 4


def _read_dump_rows(
    path: Path, width: int, max_rows: int | None = None, *, first_rows: int | None = None
) -> np.ndarray:
    """Read the last row by default or a bounded prefix of a matrix dump."""
    # debug.h stores rank and shape as int32, followed by row-major binary32.
    matrix = max_rows is not None or first_rows is not None
    header = struct.Struct("<iii" if matrix else "<ii")
    row_bytes = width * _FLOAT_BYTES
    read_count = 1 if first_rows is None else first_rows
    with path.open("rb") as stream:
        encoded_shape = stream.read(header.size)
        if len(encoded_shape) != header.size:
            raise ValueError(f"{path.name}: truncated tensor header")

        dimensions = header.unpack(encoded_shape)
        if matrix:
            rank, rows, actual_width = dimensions
            valid_shape = rank == 2 and rows >= read_count and actual_width == width
            if max_rows is not None:
                valid_shape = valid_shape and rows <= max_rows
        else:
            rows = 1
            valid_shape = dimensions == (1, width)
        if not valid_shape:
            raise ValueError(f"{path.name}: unexpected tensor header {dimensions}")

        end = stream.seek(0, 2)
        if end != header.size + rows * row_bytes:
            raise ValueError(f"{path.name}: file length does not match tensor shape")

        stream.seek(end - row_bytes if first_rows is None else header.size)
        payload = stream.read(read_count * row_bytes)
        if len(payload) != read_count * row_bytes:
            raise ValueError(f"{path.name}: truncated tensor data")
    return np.frombuffer(payload, dtype="<f4").astype(np.float32, copy=True).reshape(read_count, width)


def _load_hidden(path: Path, max_rows: int | None = None) -> np.ndarray:
    hidden = _read_dump_rows(path, _HIDDEN_SIZE, max_rows)[0]
    if not np.isfinite(hidden).all():
        raise ValueError(f"{path.name}: nonfinite bridge value")
    return hidden

def _code_ids(codes: np.ndarray, name: str) -> np.ndarray:
    # The 3072-entry semantic vocabulary reserves its last 1024 codes.
    # EOS is the sole sampling exception there and ends the frame before this dump.
    if (
        not np.isfinite(codes).all()
        or np.any(codes < 0)
        or np.any(codes >= _CODEBOOK_SIZE)
        or np.any(codes != np.trunc(codes))
    ):
        raise ValueError(f"{name}: expected integer codec IDs in [0, 2048)")
    return codes.astype(np.int32)


def load_first_frame(directory: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Read the FP32 bridge row and 16 int32 IDs, starting with semantic c0."""
    directory = Path(directory)
    hidden = _load_hidden(directory / "talker-hidden-prefill-final.bin", _MAX_PROMPT_ROWS)
    code_path = directory / "codes-step0.bin"
    codes = _read_dump_rows(code_path, _FRAME_CODES)[0]
    return hidden, _code_ids(codes, code_path.name)


def load_native_frame(directory: str | Path, index: int) -> tuple[np.ndarray, np.ndarray]:
    """Read the predictor input and acoustic IDs for native frame zero or one."""
    index = operator.index(index)
    if index == 0:
        return load_first_frame(directory)
    if index != 1:
        raise ValueError("native frame index must be 0 or 1")

    directory = Path(directory)
    hidden = _load_hidden(directory / "talker-hidden-step1.bin")
    first_path = directory / "codes-step0.bin"
    first = _code_ids(_read_dump_rows(first_path, _FRAME_CODES)[0], first_path.name)
    full_path = directory / "codes-full.bin"
    full_codes = _code_ids(_read_dump_rows(full_path, _FRAME_CODES, first_rows=2), full_path.name)
    # pipeline-tts.cpp writes all_codes in frame order. The explicit step-0
    # dump links the matrix to the capture before its second row is selected.
    if not np.array_equal(full_codes[0], first):
        raise ValueError("codes-full.bin: first row does not match codes-step0.bin")
    return hidden, full_codes[1]


def load_native_logits(directory: str | Path, index: int, reference: np.ndarray) -> np.ndarray:
    """Read the private Vulkan tap and confirm it belongs to the expected code row."""
    directory = Path(directory)
    code_path = directory / f"codes-step{index}.bin"
    if index == 0:
        _, codes = load_first_frame(directory)
    elif index == 1:
        codes = _code_ids(_read_dump_rows(code_path, _FRAME_CODES)[0], code_path.name)
    else:
        raise ValueError("native logits frame index must be 0 or 1")
    if not np.array_equal(codes, reference):
        raise ValueError(f"{code_path.name}: acoustic codes do not match the reference frame")

    path = directory / f"codepred-logits-step{index}.bin"
    raw = path.read_bytes()
    header = struct.Struct("<iii")
    if (
        len(raw) != header.size + _ACOUSTIC_CODES * _CODEBOOK_SIZE * _FLOAT_BYTES
        or header.unpack_from(raw) != (2, _CODEBOOK_SIZE, _ACOUSTIC_CODES)
    ):
        raise ValueError(f"{path.name}: unexpected native logits shape or size")
    logits = np.frombuffer(raw, dtype="<f4", offset=header.size).reshape(_ACOUSTIC_CODES, _CODEBOOK_SIZE)
    if not np.isfinite(logits).all():
        raise ValueError(f"{path.name}: nonfinite native logits")
    return logits


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
