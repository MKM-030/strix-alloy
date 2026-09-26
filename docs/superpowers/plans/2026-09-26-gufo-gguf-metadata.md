# GUFO Bounded GGUF Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute and independently review this task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read and validate GGUF header/tensor descriptors without reading tensor payloads, for the upcoming model/profile validator.

**Architecture:** A small standard-library parser bounds every descriptor read/skip and returns metadata, file identity and tensor extents. No mapping, hashing of weights, inference or runtime loading occurs. Model-specific shard/sidecar qualification is a later caller; this parser cannot qualify a runtime memory envelope.

**Tech Stack:** Python3.12 standard library, unittest, tiny synthetic GGUF fixtures.

## Global Constraints

- Source snapshots remain clean. Existing GGUF files are read-only.
- No tensor payload reads, whole-model hashes, mmap, GPU, WSL, model runtime or host setting changes.
- No edits in the dirty native repository or published Halogen repository.
- Work in `C:\Projects\strix-alloy-research\integration`; only the task-owned paths may be committed.
- Fail closed on malformed, unsupported, truncated, over-limit or changing input.
- This is partial backend work, not evidence of GUFO execution, numerical correctness or memory qualification.

### Task 1: Bounded GGUF v3 descriptor reader

**Files:**
- Create `scripts/gufo_control/gguf.py`.
- Create `tests/gufo/test_gguf.py`.
- Consume existing `scripts/gufo_control/__init__.py`; do not change admission.py.

**Interfaces:**
- `inspect_gguf(path: str | Path) -> dict` returns resolved `path`, `size_bytes`, `mtime_ns`, `version`, `metadata`, `tensors`, `descriptor_end`, `data_offset`.
- `GgufError(ValueError)` is the controlled parse error for malformed/unsupported content. Filesystem errors may propagate with their original path.
- Scalar/string metadata is retained; arrays are summarized as `{array_type: int, count: int}`, never instantiated element-by-element. String arrays are walked only through length fields, skipping their bytes.
- Tensor records contain name, dimensions, ggml_type, offset and size_bytes. Offsets are relative to the aligned tensor-data start; validate extents with file size without reading contents. Reject overlapping tensor extents, duplicate keys/names and non-row-aligned quantized shapes.
- Descriptor budget32MiB, key/name limit64KiB, retained string limit4MiB, metadata/tensor counts100000, array count1000000, alignment power-of-two up to1MiB. These caps cover the observed~11MiB IQ4XS header. Reject larger inputs rather than silently relaxing caps.

- [ ] **Step 1: Add failing fixture-based tests.** Use this initial complete test file, then add the specifically listed edge cases before extending implementation.

```python
import struct
import tempfile
import unittest
from pathlib import Path
from gufo_control.gguf import GgufError, inspect_gguf


def string(value):
    data = value.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def fixture(extra_metadata=b"", extra_count=0, tensor_name="weight", payload=True):
    meta = string("general.architecture") + struct.pack("<I", 8) + string("qwen4exp")
    header = b"GGUF" + struct.pack("<IQQ", 3, 1, 1 + extra_count) + meta + extra_metadata
    tensor = string(tensor_name) + struct.pack("<IQQIQ", 2, 4, 4, 0, 0)
    descriptors = header + tensor
    data_offset = (len(descriptors) + 31) // 32 * 32
    return descriptors + bytes(data_offset - len(descriptors)) + (bytes(64) if payload else b"")


class GgufTests(unittest.TestCase):
    def inspect(self, data):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tiny.gguf"
            path.write_bytes(data)
            return inspect_gguf(path)

    def test_valid_descriptor_and_extent(self):
        report = self.inspect(fixture())
        self.assertEqual(report["metadata"]["general.architecture"], "qwen4exp")
        self.assertEqual(report["tensors"][0]["size_bytes"], 64)
        self.assertLessEqual(report["descriptor_end"], report["data_offset"])
        self.assertEqual(report["size_bytes"], report["data_offset"] + 64)

    def test_string_array_is_summarized(self):
        arr = string("tokenizer.ggml.tokens") + struct.pack("<IIQ", 9, 8, 2)
        arr += string("hello") + string("world")
        report = self.inspect(fixture(arr, 1))
        self.assertEqual(report["metadata"]["tokenizer.ggml.tokens"], {"array_type": 8, "count": 2})

    def test_truncated_tensor_payload_extent_rejected(self):
        with self.assertRaises(GgufError):
            self.inspect(fixture(payload=False))

    def test_duplicate_metadata_rejected(self):
        duplicate = string("general.architecture") + struct.pack("<I", 8) + string("qwen4exp")
        with self.assertRaises(GgufError):
            self.inspect(fixture(duplicate, 1))

    def test_bad_magic_and_version(self):
        for data in (b"NOPE" + fixture()[4:], fixture()[:4] + struct.pack("<I", 4) + fixture()[8:]):
            with self.subTest(data=data[:8]), self.assertRaises(GgufError):
                self.inspect(data)

    def test_truncated_header(self):
        for length in (0, 3, 7, 23, 40):
            with self.subTest(length=length), self.assertRaises(GgufError):
                self.inspect(fixture()[:length])

    def test_oversized_metadata_count(self):
        data = b"GGUF" + struct.pack("<IQQ", 3, 0, 100001)
        with self.assertRaises(GgufError):
            self.inspect(data)

    def test_invalid_alignment(self):
        meta = string("general.alignment") + struct.pack("<II", 4, 3)
        with self.assertRaises(GgufError):
            self.inspect(fixture(meta, 1))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run RED.**

```powershell
$env:PYTHONPATH = Join-Path $PWD 'scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_gguf.py -v
```

Expected initial missing module. Then use a temporary empty-dict parser stub and capture an expected failing rejection assertion. Replace it only after observing that failure.

- [ ] **Step 3: Implement.** Complete starting implementation below. Verify GGML block encodings against the pinned GUFO source; fix concrete discrepancies before asserting real-file support. Do not use a guessed dtype size.

```python
"""Bounded GGUF v3 descriptors only; tensor payloads are never read."""
import math
import os
import struct
from pathlib import Path

MAX_HEADER = 32 << 20
MAX_NAME = 64 << 10
MAX_STRING = 4 << 20
MAX_COUNT = 100000
MAX_ARRAY = 1000000
SCALARS = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i",
           6: "f", 7: "B", 10: "Q", 11: "q", 12: "d"}
BLOCKS = {0: (1, 4), 1: (1, 2), 2: (32, 18), 3: (32, 20),
          6: (32, 22), 7: (32, 24), 8: (32, 34), 9: (32, 40),
          10: (256, 84), 11: (256, 110), 12: (256, 144),
          13: (256, 176), 14: (256, 210), 15: (256, 292),
          16: (256, 66), 20: (32, 18), 21: (256, 110),
          23: (256, 136), 26: (1, 4), 30: (1, 2)}


class GgufError(ValueError):
    pass


class _Reader:
    def __init__(self, stream, size):
        self.stream = stream
        self.size = size

    def advance(self, size, read=True):
        end = self.stream.tell() + size
        if size < 0 or end > min(self.size, MAX_HEADER):
            raise GgufError("truncated or over-limit descriptor")
        if not read:
            self.stream.seek(size, 1)
            return None
        data = self.stream.read(size)
        if len(data) != size:
            raise GgufError("truncated descriptor")
        return data

    def number(self, fmt):
        return struct.unpack("<" + fmt, self.advance(struct.calcsize("<" + fmt)))[0]

    def string(self, *, retain=True, limit=MAX_STRING):
        length = self.number("Q")
        if length > limit:
            raise GgufError("string exceeds descriptor limit")
        data = self.advance(length, read=retain)
        if not retain:
            return None
        try:
            return data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise GgufError("invalid UTF-8 descriptor") from error

    def value(self, kind):
        if kind in SCALARS:
            value = self.number(SCALARS[kind])
            if kind == 7:
                if value not in (0, 1):
                    raise GgufError("invalid boolean")
                return bool(value)
            if isinstance(value, float) and not math.isfinite(value):
                raise GgufError("non-finite metadata")
            return value
        if kind == 8:
            return self.string()
        if kind != 9:
            raise GgufError("unsupported metadata type")
        subtype, count = self.number("I"), self.number("Q")
        if count > MAX_ARRAY or subtype not in (*SCALARS, 8):
            raise GgufError("invalid or excessive metadata array")
        if subtype == 8:
            for _ in range(count):
                self.string(retain=False)
        else:
            self.advance(count * struct.calcsize("<" + SCALARS[subtype]), read=False)
        return {"array_type": subtype, "count": count}


def inspect_gguf(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb", buffering=0) as stream:
        before = os.fstat(stream.fileno())
        reader = _Reader(stream, before.st_size)
        if reader.advance(4) != b"GGUF" or reader.number("I") != 3:
            raise GgufError("expected GGUF v3")
        tensor_count, metadata_count = reader.number("Q"), reader.number("Q")
        if tensor_count > MAX_COUNT or metadata_count > MAX_COUNT:
            raise GgufError("descriptor count exceeds limit")
        metadata = {}
        for _ in range(metadata_count):
            key = reader.string(limit=MAX_NAME)
            if not key or key in metadata:
                raise GgufError("empty or duplicate metadata key")
            metadata[key] = reader.value(reader.number("I"))
        alignment = metadata.get("general.alignment", 32)
        if type(alignment) is not int or not 1 <= alignment <= 1 << 20 or alignment & (alignment - 1):
            raise GgufError("invalid alignment")
        tensors, names = [], set()
        for _ in range(tensor_count):
            name = reader.string(limit=MAX_NAME)
            count = reader.number("I")
            if not name or name in names or not 1 <= count <= 4:
                raise GgufError("invalid tensor name or dimension count")
            names.add(name)
            dimensions = [reader.number("Q") for _ in range(count)]
            kind, offset = reader.number("I"), reader.number("Q")
            if kind not in BLOCKS or any(d == 0 for d in dimensions):
                raise GgufError("unsupported tensor storage or zero dimension")
            block, size = BLOCKS[kind]
            elements = math.prod(dimensions)
            if dimensions[0] % block or elements > (1 << 63) - 1 or offset % alignment:
                raise GgufError("invalid tensor shape or offset")
            tensors.append({"name": name, "dimensions": dimensions,
                            "ggml_type": kind, "offset": offset,
                            "size_bytes": elements // block * size})
        descriptor_end = stream.tell()
        data_offset = (descriptor_end + alignment - 1) // alignment * alignment
        if data_offset > before.st_size:
            raise GgufError("truncated aligned header")
        previous_end = 0
        for tensor in sorted(tensors, key=lambda value: value["offset"]):
            end = tensor["offset"] + tensor["size_bytes"]
            if tensor["offset"] < previous_end or data_offset + end > before.st_size:
                raise GgufError("overlapping or truncated tensor extent")
            previous_end = end
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise GgufError("file changed during descriptor inspection")
    return {"path": str(path), "size_bytes": before.st_size,
            "mtime_ns": before.st_mtime_ns, "version": 3, "metadata": metadata,
            "tensors": tensors, "descriptor_end": descriptor_end,
            "data_offset": data_offset}
```

- [ ] **Step 4: Extend focused RED/GREEN cases and verify no payload reads.** Add cases for unsupported scalar/array/tensor types, nested arrays, excessive string/array length, malformed UTF-8, invalid boolean/alignment type, zero dimension, quantized first-dimension misalignment, duplicate tensor names, overlap, size overflow and metadata-only first shard. Use a real wrapped file handle in a single focused test whose read method records requested extents and rejects any read past `descriptor_end`; do not replace parsing with mocked results. Model input can be changed between reads in a controlled fixture to exercise the fstat recheck. Source validation here concerns metadata and extents; skipped tokenizer-array contents are intentionally not semantically validated.

- [ ] **Step 5: Verify on real metadata only.** After fixture tests pass, call `inspect_gguf` on the three existing IQ4XS shards and shared sidecar under `C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS`, printing only scalar architecture/split/geometry, counts, sizes and descriptor boundaries. Do not print tokenizer arrays, paths outside this scope or full tensor payloads. Confirm actual types are in the validated table and record any rejection without loosening caps silently. No correctness or runtime-fit claim follows.

- [ ] **Step 6: Run all GUFO offline tests and commit only the two owned files.**

```powershell
$env:PYTHONPATH = Join-Path $PWD 'scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_*.py' -v
git diff --check
git add -- scripts/gufo_control/gguf.py tests/gufo/test_gguf.py
git commit -m 'feat: inspect GGUF descriptors without loading weights'
```

Report RED/GREEN, actual test counts, real-file header observations, source verification of dtype table, commit and limitations to the task-brief sibling `gguf-task-1-report.md`. Main obtains an independent task review before using this parser in a profile validator.
