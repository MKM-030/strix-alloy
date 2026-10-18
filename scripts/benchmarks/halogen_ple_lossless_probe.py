"""Bounded CPU feasibility screen of exact PLE rows; stdlib only.

Reads only sealed 256x160-byte sample files, never a checkpoint or device.
Canonical Huffman is trained only on train windows with pseudocount one for all
256 byte symbols. Rows are independently byte-aligned and support indexed
decoding. Net bytes include uint32 offsets with a sentinel, 256 code lengths,
per-row CRC32 and the four exact global-scale bytes. CRC detects accidental
corruption; the manifest and sample SHA256 provide input identity.

No live consumer, NPU placement, quality/tok-s claim or whole-table extrapolation.
"""
import argparse
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time
import zlib


ROW_BYTES = 160
WINDOW_ROWS = 256
MAX_SAMPLE_BYTES = 8 << 20
MAX_MANIFEST_BYTES = 1 << 20
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
UINT32_MAX = (1 << 32) - 1


def _check_deadline(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise ValueError("bounded CPU probe deadline exceeded")


def _digest(value):
    if not isinstance(value, str) or HASH_PATTERN.fullmatch(value) is None:
        raise ValueError("lowercase SHA256 required")
    return value


def _regular_path(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute sample/manifest path without traversal required")
    for node in (path, *path.parents):
        info = node.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("sample/manifest links and reparse points refused")
    return path


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_bounded(path, limit, expected_sha, *, exact_bytes=None, deadline=None):
    path = _regular_path(path)
    _check_deadline(deadline)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_size > limit
                or (exact_bytes is not None and before.st_size != exact_bytes)):
            raise ValueError("bounded regular sample/manifest file extent differs")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    _regular_path(path)
    # Use fstat both times; Windows stat/fstat ctime interpretations may differ.
    with os.fdopen(os.open(path, flags), "rb") as stream:
        current = os.fstat(stream.fileno())
    if _identity(before) != _identity(after) or _identity(before) != _identity(current):
        raise ValueError("sample/manifest identity changed during read")
    if len(data) != before.st_size or hashlib.sha256(data).hexdigest() != _digest(expected_sha):
        raise ValueError("sample/manifest extent or SHA256 differs")
    _check_deadline(deadline)
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


@dataclass(frozen=True)
class SampleWindow:
    file: str
    sha256: str
    region: object
    window_index: int
    split: str
    raw: bytes


@dataclass(frozen=True)
class Samples:
    manifest_sha256: str
    source: dict
    global_scale: bytes
    windows: tuple

    @property
    def train_bytes(self):
        return b"".join(window.raw for window in self.windows if window.split == "train")

    @property
    def raw(self):
        return b"".join(window.raw for window in self.windows)


def load_samples(manifest_path, manifest_sha256, *, deadline=None):
    """Load only exact small window files, with train/eval separation."""
    manifest_sha256 = _digest(manifest_sha256)
    content = _read_bounded(manifest_path, MAX_MANIFEST_BYTES, manifest_sha256,
                            deadline=deadline)
    manifest = json.loads(content, object_pairs_hook=_unique_object)
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "halogen.ple-samples.v1"
            or type(manifest.get("row_bytes")) is not int
            or manifest["row_bytes"] != ROW_BYTES):
        raise ValueError("halogen.ple-samples.v1 with row_bytes160 required")
    scale_hex = manifest.get("global_scale_bits")
    if not isinstance(scale_hex, str) or re.fullmatch(r"[0-9a-fA-F]{8}", scale_hex) is None:
        raise ValueError("global_scale_bits must be exactly four hex bytes")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError("source provenance object required")
    for field in ("extraction_receipt_sha256", "tensor_sha256"):
        _digest(source.get(field))
    entries = manifest.get("windows")
    if not isinstance(entries, list) or not 2 <= len(entries) <= MAX_SAMPLE_BYTES // (256 * ROW_BYTES):
        raise ValueError("bounded nonempty train/eval window list required")
    windows, seen_paths, seen_regions = [], set(), set()
    for entry in entries:
        _check_deadline(deadline)
        if not isinstance(entry, dict):
            raise ValueError("window must be an object")
        if type(entry.get("rows")) is not int or entry["rows"] != WINDOW_ROWS:
            raise ValueError("every sample window must contain exactly256 rows")
        region = entry.get("region")
        if not ((type(region) is int and region >= 0)
                or (isinstance(region, str) and 0 < len(region) <= 128)):
            raise ValueError("region must be a nonnegative integer or short name")
        index, split = entry.get("window_index"), entry.get("split")
        if type(index) is not int or index < 0 or split not in ("train", "eval"):
            raise ValueError("window index and explicit train/eval split required")
        filename = entry.get("file")
        if not isinstance(filename, str):
            raise ValueError("absolute window file required")
        path = _regular_path(filename)
        path_key = os.path.normcase(str(path.resolve()))
        region_key = (type(region).__name__, region, index)
        if path_key in seen_paths or region_key in seen_regions:
            raise ValueError("duplicate sample file or region/window")
        seen_paths.add(path_key)
        seen_regions.add(region_key)
        digest = _digest(entry.get("sha256"))
        raw = _read_bounded(path, WINDOW_ROWS * ROW_BYTES, digest,
                            exact_bytes=WINDOW_ROWS * ROW_BYTES, deadline=deadline)
        windows.append(SampleWindow(str(path), digest, region, index, split, raw))
    if {window.split for window in windows} != {"train", "eval"}:
        raise ValueError("at least one train and one held-out eval window required")
    if sum(len(window.raw) for window in windows) > MAX_SAMPLE_BYTES:
        raise ValueError("total sample payload exceeds8MiB")
    return Samples(manifest_sha256, source, bytes.fromhex(scale_hex), tuple(windows))


def train_lengths(train):
    """Canonical Huffman lengths from training bytes, with all-symbol support."""
    if not isinstance(train, bytes) or not 0 < len(train) <= MAX_SAMPLE_BYTES:
        raise ValueError("bounded nonempty training bytes required")
    counts = Counter(train)
    # Distinct minimum-symbol tie breakers make equal-frequency trees stable.
    heap = [(counts[symbol] + 1, symbol, symbol) for symbol in range(256)]
    heapq.heapify(heap)
    while len(heap) > 1:
        left_count, left_min, left = heapq.heappop(heap)
        right_count, right_min, right = heapq.heappop(heap)
        heapq.heappush(heap, (left_count + right_count, min(left_min, right_min), (left, right)))
    lengths, stack = [0] * 256, [(heap[0][2], 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, int):
            lengths[node] = depth
        else:
            stack.extend(((node[0], depth + 1), (node[1], depth + 1)))
    result = bytes(lengths)
    _canonical(result)
    return result


@lru_cache(maxsize=8)
def _canonical(lengths):
    if not isinstance(lengths, bytes) or len(lengths) != 256 or any(length == 0 for length in lengths):
        raise ValueError("invalid all-symbol Huffman code lengths")
    ordered = sorted(range(256), key=lambda symbol: (lengths[symbol], symbol))
    codes, decode, code, previous = [None] * 256, {}, 0, 0
    for symbol in ordered:
        length = lengths[symbol]
        code <<= length - previous
        if code >= 1 << length:
            raise ValueError("oversubscribed Huffman code lengths")
        codes[symbol] = (code, length)
        decode[(length, code)] = symbol
        code += 1
        previous = length
    if code != 1 << previous:
        raise ValueError("incomplete Huffman code lengths")
    return tuple(codes), decode, max(lengths)


@dataclass(frozen=True)
class HuffmanRows:
    lengths: bytes
    offsets: tuple
    payload: bytes
    row_crc32: tuple
    global_scale: bytes

    def __post_init__(self):
        _canonical(self.lengths)
        if not isinstance(self.global_scale, bytes) or len(self.global_scale) != 4:
            raise ValueError("exact four-byte global scale required")
        if not isinstance(self.payload, bytes):
            raise ValueError("encoded row payload must be bytes")
        rows = len(self.row_crc32)
        if not 1 <= rows <= MAX_SAMPLE_BYTES // ROW_BYTES or len(self.offsets) != rows + 1:
            raise ValueError("bounded row directory extent differs")
        if (self.offsets[0] != 0 or self.offsets[-1] != len(self.payload)
                or any(type(offset) is not int or not 0 <= offset <= UINT32_MAX for offset in self.offsets)
                or any(left >= right for left, right in zip(self.offsets, self.offsets[1:]))
                or any(type(crc) is not int or not 0 <= crc <= UINT32_MAX for crc in self.row_crc32)):
            raise ValueError("invalid row offset/extent/checksum metadata")

    def accounting(self):
        # Materialize the directory/checksum planes in the stated byte order;
        # these counts are serialized bytes, not Python tuple memory estimates.
        directory = struct.pack("<" + "I" * len(self.offsets), *self.offsets)
        checksums = struct.pack("<" + "I" * len(self.row_crc32), *self.row_crc32)
        counts = dict(encoded_data_bytes=len(self.payload),
                      row_directory_bytes=len(directory),
                      row_checksum_bytes=len(checksums),
                      canonical_lengths_bytes=256, global_scale_bytes=4)
        counts["net_bytes"] = sum(counts.values())
        return counts


def encode_rows(raw, lengths, global_scale, *, deadline=None):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_SAMPLE_BYTES or len(raw) % ROW_BYTES:
        raise ValueError("bounded complete160-byte rows required")
    codes, _, _ = _canonical(lengths)
    payload, offsets, checksums = bytearray(), [0], []
    for index in range(len(raw) // ROW_BYTES):
        if index % 256 == 0:
            _check_deadline(deadline)
        row = raw[index * ROW_BYTES:(index + 1) * ROW_BYTES]
        pending, bits = 0, 0
        for symbol in row:
            code, length = codes[symbol]
            pending = (pending << length) | code
            bits += length
            while bits >= 8:
                bits -= 8
                payload.append((pending >> bits) & 255)
                pending &= (1 << bits) - 1
        if bits:
            payload.append(pending << (8 - bits))
        offsets.append(len(payload))
        checksums.append(zlib.crc32(row))
    _check_deadline(deadline)
    return HuffmanRows(lengths, tuple(offsets), bytes(payload), tuple(checksums), global_scale)


def decode_row(bank, row_index):
    """Read only one encoded row; reject truncation, padding and CRC corruption."""
    if type(row_index) is not int or not 0 <= row_index < len(bank.row_crc32):
        raise ValueError("row index outside encoded bank")
    _, lookup, longest = _canonical(bank.lengths)
    start, end = bank.offsets[row_index:row_index + 2]
    encoded = memoryview(bank.payload)[start:end]
    result, cursor = bytearray(), 0
    for _ in range(ROW_BYTES):
        code, found = 0, False
        for length in range(1, longest + 1):
            if cursor >= len(encoded) * 8:
                raise ValueError("truncated Huffman row")
            code = (code << 1) | ((encoded[cursor // 8] >> (7 - cursor % 8)) & 1)
            cursor += 1
            symbol = lookup.get((length, code))
            if symbol is not None:
                result.append(symbol)
                found = True
                break
        if not found:
            raise ValueError("corrupt Huffman row code")
    remaining = len(encoded) * 8 - cursor
    if remaining >= 8:
        raise ValueError("noncanonical trailing Huffman row bytes")
    if remaining and encoded[-1] & ((1 << remaining) - 1):
        raise ValueError("nonzero Huffman row padding")
    row = bytes(result)
    if zlib.crc32(row) != bank.row_crc32[row_index]:
        raise ValueError("Huffman row checksum differs")
    return row


def byte_entropy(raw):
    if not raw:
        return 0.0
    count = len(raw)
    return -sum((frequency / count) * math.log2(frequency / count)
                for frequency in Counter(raw).values())


def _row_stats(raw):
    rows = [raw[start:start + ROW_BYTES] for start in range(0, len(raw), ROW_BYTES)]
    distinct = len(set(rows))  # Python bytes equality confirms collisions.
    counts = Counter(raw)
    return dict(rows=len(rows), distinct_exact_vectors=distinct,
                duplicate_vectors=len(rows) - distinct,
                all_zero_rows=sum(not any(row) for row in rows),
                distinct_byte_symbols=len(counts), byte_entropy_bits=byte_entropy(raw),
                sign_entropy_bits=byte_entropy(bytes(value >> 7 for value in raw)),
                exponent_entropy_bits=byte_entropy(bytes((value >> 3) & 15 for value in raw)),
                mantissa_entropy_bits=byte_entropy(bytes(value & 7 for value in raw)))


def zlib_blocks(raw, *, rows_per_block, global_scale, deadline=None):
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_SAMPLE_BYTES
            or len(raw) % ROW_BYTES or rows_per_block not in (1, 4, 16, 64, 256)
            or not isinstance(global_scale, bytes) or len(global_scale) != 4):
        raise ValueError("bounded complete rows and supported zlib block size required")
    block_bytes, encoded_bytes, blocks = rows_per_block * ROW_BYTES, 0, 0
    for start in range(0, len(raw), block_bytes):
        _check_deadline(deadline)
        original = raw[start:start + block_bytes]
        encoded = zlib.compress(original, level=6)
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(encoded, len(original) + 1)
        if (decoded != original or not inflater.eof or inflater.unused_data
                or inflater.unconsumed_tail):
            raise ValueError("bounded zlib exact roundtrip differs")
        encoded_bytes += len(encoded)
        blocks += 1
    directory = 4 * (blocks + 1)
    return dict(rows_per_block=rows_per_block, blocks=blocks, level=6,
                encoded_data_bytes=encoded_bytes, block_directory_bytes=directory,
                global_scale_bytes=4, net_bytes=encoded_bytes + directory + 4,
                exact_roundtrip=True, checksums="zlib stream Adler32 included in encoded bytes",
                worst_single_row_raw_decode_bytes=min(block_bytes, len(raw)),
                worst_single_row_amplification_rows=min(rows_per_block, len(raw) // ROW_BYTES),
                format_overhead_excludes_file_container=True)


def probe_samples(samples, *, deadline=None):
    """Report sampled bytes only. Neither serializes nor publishes a live bank."""
    _check_deadline(deadline)
    source_path = Path(__file__).resolve()
    with source_path.open("rb") as source_stream:
        probe_source = source_stream.read(MAX_MANIFEST_BYTES + 1)
    if not 0 < len(probe_source) <= MAX_MANIFEST_BYTES:
        raise ValueError("bounded probe source extent differs")
    probe_source_sha256 = hashlib.sha256(probe_source).hexdigest()
    raw, train = samples.raw, samples.train_bytes
    lengths = train_lengths(train)
    bank = encode_rows(raw, lengths, samples.global_scale, deadline=deadline)
    for index in range(len(raw) // ROW_BYTES):
        if index % 256 == 0:
            _check_deadline(deadline)
        if decode_row(bank, index) != raw[index * ROW_BYTES:(index + 1) * ROW_BYTES]:
            raise ValueError("exact Huffman indexed row roundtrip differs")
    account = bank.accounting()
    raw_bytes = len(raw) + 4
    windows, cursor = [], 0
    for window in samples.windows:
        stats = _row_stats(window.raw)
        row_count = len(window.raw) // ROW_BYTES
        stats.update(file=window.file, sha256=window.sha256, region=window.region,
                     window_index=window.window_index, split=window.split,
                     huffman_row_payload_bytes=bank.offsets[cursor + row_count] - bank.offsets[cursor],
                     shared_codebook_and_scale_accounted_in_aggregate_only=True)
        windows.append(stats)
        cursor += row_count
        _check_deadline(deadline)
    aggregate = _row_stats(raw)
    by_split = {split: _row_stats(b"".join(window.raw for window in samples.windows
                                         if window.split == split))
                for split in ("train", "eval")}
    longest = max(lengths)
    huffman = dict(account, rows=len(raw) // ROW_BYTES, exact_roundtrip=True,
                   training_bytes=len(train), evaluation_bytes=len(raw) - len(train),
                   pseudocount_per_symbol=1, independently_byte_aligned_rows=True,
                   zero_padding_verified=True, directory_type="little-endian uint32 offsets with sentinel",
                   row_checksums="CRC32; error detection, not cryptographic identity",
                   raw_bytes_including_scale=raw_bytes, net_ratio=account["net_bytes"] / raw_bytes,
                   net_saving_bytes=raw_bytes - account["net_bytes"],
                   minimum_code_length=min(lengths), maximum_code_length=longest,
                   code_length_counts={str(length): lengths.count(length) for length in sorted(set(lengths))},
                   canonical_lengths_hex=lengths.hex(),
                   native_decoder_lut_statistics=dict(entry_bytes=2,
                       minimum_direct_table_bytes=2 * (1 << longest),
                       maximum_code_length_at_most12=longest <= 12,
                       native_placement_qualified=False))
    zlib_results = [zlib_blocks(raw, rows_per_block=count, global_scale=samples.global_scale,
                               deadline=deadline) for count in (1, 4, 16, 64, 256)]
    _check_deadline(deadline)
    return dict(schema="halogen.ple-lossless-probe.v1",
                probe_source=str(source_path), probe_source_sha256=probe_source_sha256,
                input_manifest_sha256=samples.manifest_sha256, source=samples.source,
                source_receipt_revalidated=False, source_provenance="retained from sealed sample manifest",
                source_row_ranges_revalidated=False,
                sample_payload_bytes=len(raw), global_scale_bits=samples.global_scale.hex(),
                sample_sha256=hashlib.sha256(raw).hexdigest(),
                raw_bytes_including_scale=raw_bytes, aggregate=aggregate, by_split=by_split,
                windows=windows, huffman=huffman, block_zlib=zlib_results,
                entropy_is_empirical_model_statistic_not_realized_saving=True,
                comparison_scope="sample files and CPU format accounting only; not source fault or consumer latency",
                whole_table_extrapolation=False, live_consumer_implemented=False,
                npu_executed=False, target_weights_changed=False, speed_claim=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--deadline-seconds", type=float, default=60)
    args = parser.parse_args()
    if not math.isfinite(args.deadline_seconds) or not 0 < args.deadline_seconds <= 120:
        parser.error("deadline-seconds must be positive and at most120")
    deadline = time.monotonic() + args.deadline_seconds
    try:
        samples = load_samples(args.manifest, args.manifest_sha256, deadline=deadline)
        report = probe_samples(samples, deadline=deadline)
        rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.out is not None:
            if not args.out.is_absolute() or ".." in args.out.parts:
                raise ValueError("absolute fresh report path without traversal required")
            if os.path.normcase(str(args.out.resolve())) in {
                    os.path.normcase(str(args.manifest.resolve())),
                    *(os.path.normcase(str(Path(window.file).resolve())) for window in samples.windows)}:
                raise ValueError("report cannot replace an input")
            with args.out.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
            print(json.dumps(dict(report=str(args.out), schema=report["schema"],
                                  sample_payload_bytes=report["sample_payload_bytes"],
                                  exact_roundtrip=report["huffman"]["exact_roundtrip"],
                                  huffman_net_ratio=report["huffman"]["net_ratio"],
                                  live_consumer_implemented=False, speed_claim=False)))
        else:
            print(rendered, end="")
    except (OSError, ValueError, TypeError, KeyError, zlib.error) as error:
        print(json.dumps(dict(schema="halogen.ple-lossless-probe.v1", passed=False,
                              error=str(error), npu_executed=False, speed_claim=False)), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
