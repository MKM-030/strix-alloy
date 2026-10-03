"""Decode selected rows of an HGN q4c variant-2 tensor for NPU prototyping."""
import argparse
import json
import math
from pathlib import Path
import numpy as np


def decode_rows(stream, entry, row_start, rows):
    """Read only requested rows; never expand the complete tensor or model."""
    if entry['store'] != 5 or entry['variant'] != 2:
        raise ValueError('requires q4c variant 2')
    dims = entry['dims']
    if not dims or any(type(value) is not int or value <= 0 for value in dims):
        raise ValueError('invalid tensor dimensions')
    width, count = dims[-1], math.prod(dims[:-1])
    if width % 32 or type(row_start) is not int or type(rows) is not int or not 0 <= row_start < count or not 0 < rows <= count - row_start:
        raise ValueError('row slice outside tensor or unsupported q4c width')
    if rows * width * 4 > 256 * 1024**2:
        raise ValueError('decoded slice exceeds the 256 MiB prototype budget')
    offset, size = entry['offset'], entry['size']
    if type(offset) is not int or type(size) is not int or offset < 0 or size <= 0:
        raise ValueError('invalid tensor bounds')
    code_bytes = width // 2
    scale_base = offset + 64 + ((count * code_bytes + 63) // 64) * 64
    scale_stride = ((width // 16 + 15) // 16) * 16
    groups = width // 32

    def read(position, length):
        if position < offset or position + length > offset + size:
            raise ValueError('q4c payload outside declared tensor')
        stream.seek(position)
        value = stream.read(length)
        if len(value) != length:
            raise ValueError('truncated q4c payload')
        return value

    codebook = np.frombuffer(read(offset, 64), dtype='<f4')
    result = np.empty((rows, width), dtype=np.float32)
    for index, row in enumerate(range(row_start, row_start + rows)):
        packed = np.frombuffer(read(offset + 64 + row * code_bytes, code_bytes), dtype=np.uint8)
        codes = np.empty(width, dtype=np.uint8)
        codes[0::2], codes[1::2] = packed & 15, packed >> 4
        scales = np.frombuffer(read(scale_base + row * scale_stride, groups * 2), dtype='<f2').astype(np.float32)
        result[index] = codebook[codes] * np.repeat(scales, 32)
    if not np.isfinite(result).all():
        raise ValueError('non-finite decoded q4c weights')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hgn', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--tensor', required=True)
    parser.add_argument('--row-start', type=int, default=0)
    parser.add_argument('--rows', type=int, default=1)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    entry = next(value for value in manifest['entries'] if value['name'] == args.tensor)
    with args.hgn.open('rb') as stream:
        result = decode_rows(stream, entry, args.row_start, args.rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out, result)
    print(json.dumps({'tensor': args.tensor, 'shape': entry['dims'], 'row_start': args.row_start,
                     'rows': args.rows, 'K': entry['dims'][-1], 'output_shape': list(result.shape),
                     'min': float(result.min()), 'max': float(result.max()), 'finite': True}, indent=2))


if __name__ == '__main__':
    main()
