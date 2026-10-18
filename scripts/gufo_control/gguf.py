"""Read bounded GGUF v3 descriptors without reading tensor payloads."""

import math
import os
import struct
from pathlib import Path

MAX_HEADER = 32 << 20
MAX_NAME = 64 << 10
MAX_STRING = 4 << 20
MAX_COUNT = 100000
MAX_ARRAY = 1000000
SCALARS = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i',
           6: 'f', 7: 'B', 10: 'Q', 11: 'q', 12: 'd'}
# ggml_type_size / ggml_blck_size from pinned GUFO ds4_ggml_stubs.h.
BLOCKS = {0: (1, 4), 1: (1, 2), 2: (32, 18), 3: (32, 20),
          6: (32, 22), 7: (32, 24), 8: (32, 34), 9: (32, 36),
          10: (256, 84), 11: (256, 110), 12: (256, 144),
          13: (256, 176), 14: (256, 210), 15: (256, 292),
          16: (256, 66), 17: (256, 74), 18: (256, 98),
          19: (256, 50), 20: (32, 18), 21: (256, 110),
          22: (256, 82), 23: (256, 136), 24: (1, 1),
          25: (1, 2), 26: (1, 4), 27: (1, 8), 28: (1, 8),
          29: (256, 56), 30: (1, 2), 39: (32, 17),
          40: (64, 18), 41: (256, 36)}


class GgufError(ValueError):
    """Malformed, excessive, or unsupported GGUF descriptor."""


class _Reader:
    def __init__(self, stream, size):
        self.stream = stream
        self.size = size

    def advance(self, size, read=True):
        end = self.stream.tell() + size
        if size < 0 or end > min(self.size, MAX_HEADER):
            raise GgufError('truncated or over-limit descriptor')
        if not read:
            self.stream.seek(size, 1)
            return None
        data = self.stream.read(size)
        if len(data) != size:
            raise GgufError('truncated descriptor')
        return data

    def number(self, fmt):
        return struct.unpack('<' + fmt, self.advance(struct.calcsize('<' + fmt)))[0]

    def string(self, *, retain=True, limit=MAX_STRING):
        length = self.number('Q')
        if length > limit:
            raise GgufError('string exceeds descriptor limit')
        data = self.advance(length, read=retain)
        if not retain:
            return None
        try:
            return data.decode('utf-8', errors='strict')
        except UnicodeDecodeError as error:
            raise GgufError('invalid UTF-8 descriptor') from error

    def value(self, kind):
        if kind in SCALARS:
            value = self.number(SCALARS[kind])
            if kind == 7:
                if value not in (0, 1):
                    raise GgufError('invalid boolean')
                return bool(value)
            if isinstance(value, float) and not math.isfinite(value):
                raise GgufError('non-finite metadata')
            return value
        if kind == 8:
            return self.string()
        if kind != 9:
            raise GgufError('unsupported metadata type')
        subtype, count = self.number('I'), self.number('Q')
        if count > MAX_ARRAY or subtype not in (*SCALARS, 8):
            raise GgufError('invalid or excessive metadata array')
        if subtype == 8:
            for _ in range(count):
                self.string(retain=False)
        else:
            self.advance(count * struct.calcsize('<' + SCALARS[subtype]), read=False)
        return {'array_type': subtype, 'count': count}


def inspect_gguf(path: str | Path) -> dict:
    """Inspect metadata and tensor extents, bounded to the descriptor region."""
    path = Path(path).resolve(strict=True)
    with path.open('rb', buffering=0) as stream:
        before = os.fstat(stream.fileno())
        reader = _Reader(stream, before.st_size)
        if reader.advance(4) != b'GGUF' or reader.number('I') != 3:
            raise GgufError('expected GGUF v3')
        tensor_count, metadata_count = reader.number('Q'), reader.number('Q')
        if tensor_count > MAX_COUNT or metadata_count > MAX_COUNT:
            raise GgufError('descriptor count exceeds limit')
        metadata = {}
        for _ in range(metadata_count):
            key = reader.string(limit=MAX_NAME)
            if not key or key in metadata:
                raise GgufError('empty or duplicate metadata key')
            metadata[key] = reader.value(reader.number('I'))
        alignment = metadata.get('general.alignment', 32)
        if type(alignment) is not int or not 1 <= alignment <= 1 << 20 or alignment & (alignment - 1):
            raise GgufError('invalid alignment')
        tensors, names = [], set()
        for _ in range(tensor_count):
            name = reader.string(limit=MAX_NAME)
            count = reader.number('I')
            if not name or name in names or not 1 <= count <= 4:
                raise GgufError('invalid tensor name or dimension count')
            names.add(name)
            dimensions = [reader.number('Q') for _ in range(count)]
            kind, offset = reader.number('I'), reader.number('Q')
            if kind not in BLOCKS or any(d == 0 for d in dimensions):
                raise GgufError('unsupported tensor storage or zero dimension')
            block, size = BLOCKS[kind]
            elements = math.prod(dimensions)
            if dimensions[0] % block or elements > (1 << 63) - 1 or offset % alignment:
                raise GgufError('invalid tensor shape or offset')
            tensors.append({'name': name, 'dimensions': dimensions,
                            'ggml_type': kind, 'offset': offset,
                            'size_bytes': elements // block * size})
        descriptor_end = stream.tell()
        data_offset = (descriptor_end + alignment - 1) // alignment * alignment
        if data_offset > before.st_size:
            raise GgufError('truncated aligned header')
        previous_end = 0
        for tensor in sorted(tensors, key=lambda value: value['offset']):
            end = tensor['offset'] + tensor['size_bytes']
            if tensor['offset'] < previous_end or data_offset + end > before.st_size:
                raise GgufError('overlapping or truncated tensor extent')
            previous_end = end
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise GgufError('file changed during descriptor inspection')
    return {'path': str(path), 'size_bytes': before.st_size,
            'mtime_ns': before.st_mtime_ns, 'version': 3, 'metadata': metadata,
            'tensors': tensors, 'descriptor_end': descriptor_end,
            'data_offset': data_offset}
