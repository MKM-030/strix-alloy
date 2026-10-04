"""Decode bounded rows of an HGN q8g64 variant-0 tensor."""
import argparse
import json
import math
from pathlib import Path

import numpy as np


MAX_DECODED_BYTES = 64 * 1024**2


def row_geometry(entry):
    """Validate the complete encoded extent without reading its payload."""
    if (entry.get("store"), entry.get("variant")) != (7, 0):
        raise ValueError("requires q8g64 variant 0")
    dims = entry.get("dims")
    if (not isinstance(dims, list) or not 1 <= len(dims) <= 4 or
            any(type(value) is not int or value <= 0 for value in dims)):
        raise ValueError("invalid q8g64 tensor dimensions")
    width, count = dims[-1], math.prod(dims[:-1])
    offset, size = entry.get("offset"), entry.get("size")
    if (width % 64 or type(offset) is not int or offset < 0 or
            type(size) is not int or size <= 0):
        raise ValueError("invalid q8g64 width or tensor bounds")
    row_bytes = width + width // 16
    if count * row_bytes != size:
        raise ValueError("q8g64 payload size mismatch")
    return width, count, row_bytes


def decode_rows(stream, entry, row_start, rows):
    """Read only selected affine-u8 rows; cap the FP32 slice at 64 MiB."""
    width, count, row_bytes = row_geometry(entry)
    if (type(row_start) is not int or type(rows) is not int or
            not 0 <= row_start < count or not 0 < rows <= count - row_start):
        raise ValueError("row slice outside q8g64 tensor")
    if rows * width * 4 > MAX_DECODED_BYTES:
        raise ValueError("decoded q8g64 slice exceeds the 64 MiB budget")
    start, length = entry["offset"] + row_start * row_bytes, rows * row_bytes
    if start < entry["offset"] or length > entry["offset"] + entry["size"] - start:
        raise ValueError("q8g64 slice exceeds declared tensor bounds")
    stream.seek(start)
    payload = stream.read(length)
    if len(payload) != length:
        raise ValueError("truncated q8g64 row slice")
    raw = np.frombuffer(payload, dtype=np.uint8).reshape(rows, row_bytes)
    codes = raw[:, :width].reshape(rows, width // 64, 64).astype(np.float32)
    affine = raw[:, width:].copy().view("<f2").reshape(rows, width // 64, 2).astype(np.float32)
    value = (codes * affine[..., 0, None] + affine[..., 1, None]).reshape(rows, width)
    if not np.isfinite(value).all():
        raise ValueError("nonfinite decoded q8g64 weights")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hgn", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tensor", required=True)
    parser.add_argument("--row-start", type=int, default=0)
    parser.add_argument("--rows", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.suffix != ".npy":
        raise ValueError("output must have an explicit .npy suffix")
    if args.out.exists():
        raise FileExistsError("existing decoded slice refused")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    matches = [entry for entry in manifest["entries"] if entry["name"] == args.tensor]
    if len(matches) != 1:
        raise ValueError("one unique selected tensor required")
    with args.hgn.open("rb") as stream:
        result = decode_rows(stream, matches[0], args.row_start, args.rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("xb") as stream:
        np.save(stream, result)
    print(json.dumps(dict(tensor=args.tensor, shape=matches[0]["dims"],
                          row_start=args.row_start, rows=args.rows,
                          K=result.shape[1], output_shape=list(result.shape),
                          min=float(result.min()), max=float(result.max()), finite=True), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
