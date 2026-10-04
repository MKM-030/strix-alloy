"""Metadata/integrity-bound selected q4c v2 expert reader; CPU only."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from hgn_q4c_slice import decode_rows
from halogen_npu_mtp_metadata import metadata

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from host_frames import frame


GIB = 1024**3
WIDTH, INTERMEDIATE, TOP_K = 2560, 640, 10
WEIGHTS_BYTES_PER_SET = 196608000
CHECKPOINT_SHA256 = "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687"
METADATA_SHA256 = "4159d1ddb9094907ba82b62940777317d9bc89e4c7a8cb881809ecb17912e3cb"
DECODER_SHA256 = "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reserve(samples, additional_bytes=0):
    current = frame()
    samples.append(current)
    if current["available_bytes"] < 18 * GIB + additional_bytes or current["commit_headroom_bytes"] < 18 * GIB + additional_bytes:
        raise RuntimeError("18 GiB physical/commit reserve plus next allocation unavailable")
    return current


def native_identity(machine, source):
    code = "import os,json,sys;s=os.stat(sys.argv[1]);print(json.dumps(dict(size=s.st_size,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)))"
    command = ["wsl.exe", "-d", machine["distro"], "-u", machine["user"], "--exec", "python3", "-c", code, source]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=15,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return json.loads(result.stdout)


class WindowStream:
    """Feed the frozen decoder only three bounded source ranges per expert."""
    def __init__(self, ranges):
        self.ranges = ranges
        self.position = 0

    def seek(self, position):
        self.position = position

    def read(self, length):
        for start, data in self.ranges:
            if start <= self.position and self.position + length <= start + len(data):
                offset = self.position - start
                self.position += length
                return memoryview(data)[offset:offset + length]
        raise ValueError("decoder requested bytes outside the selected sparse ranges")


def expert(stream, entry, expert_id, rows):
    width = entry["dims"][-1]
    count = math.prod(entry["dims"][:-1])
    offset, size = entry["offset"], entry["size"]
    code_bytes = width // 2
    scale_stride = ((width // 16 + 15) // 16) * 16
    scale_base = offset + 64 + ((count * code_bytes + 63) // 64) * 64
    row_start = expert_id * rows
    requested = [(offset, 64), (offset + 64 + row_start * code_bytes, rows * code_bytes),
                 (scale_base + row_start * scale_stride, rows * scale_stride)]
    ranges, records = [], []
    for start, length in requested:
        if start < offset or start + length > offset + size:
            raise ValueError("selected sparse range exceeds declared tensor")
        stream.seek(start)
        data = stream.read(length)
        if len(data) != length:
            raise ValueError("truncated selected sparse range")
        ranges.append((start, data))
        records.append(dict(offset=start, bytes=length, sha256=hashlib.sha256(data).hexdigest()))
    decoded = decode_rows(WindowStream(ranges), entry, row_start, rows)
    return decoded, dict(expert=expert_id, tensor=entry["name"], ranges=records,
                         decoded_sha256=hashlib.sha256(decoded.tobytes()).hexdigest())


def read_sets(metadata_path, integrity_path, machine_path):
    started = time.perf_counter_ns()
    samples = []
    reserve(samples, 2 * WEIGHTS_BYTES_PER_SET)
    if digest(metadata_path) != METADATA_SHA256 or digest(Path(__file__).with_name("hgn_q4c_slice.py")) != DECODER_SHA256:
        raise ValueError("frozen metadata receipt or q4c decoder differs")
    evidence = json.loads(metadata_path.read_text())
    expected = evidence["sources"]["v2"]
    integrity = json.loads(integrity_path.read_text())
    machine = json.loads(machine_path.read_text())
    if integrity["sha256"] != CHECKPOINT_SHA256 or integrity["identity"]["size"] != 66687678432:
        raise ValueError("pinned v2 checkpoint integrity receipt differs")
    source = machine["models"] + "/qwen38-flash-next-v2.hgn"
    unc = Path("\\\\wsl.localhost\\" + machine["distro"] + source.replace("/", "\\"))
    if str(unc) != expected["path"]:
        raise ValueError("machine source differs from metadata-bound v2 path")
    native_before = native_identity(machine, source)
    if native_before != integrity["identity"]:
        raise ValueError("native v2 identity differs from complete integrity receipt")
    actual = metadata(unc)
    if any(actual[key] != expected[key] for key in ["identity", "file_size", "version", "tensor_count", "header_sha256", "table_sha256", "entries"]):
        raise ValueError("v2 header or tensor metadata differs from pinned receipt")
    entries = {entry["name"]: entry for entry in actual["entries"]}
    gate = entries["mtp.layers.0.mlp.experts.gate_up_proj.weight"]
    down = entries["mtp.layers.0.mlp.experts.down_proj.weight"]
    if (gate["dims"], down["dims"]) != ([512, 1280, 2560], [512, 2560, 640]):
        raise ValueError("v2 expert geometry differs")
    if any((entry["store"], entry["variant"]) != (5, 2) for entry in [gate, down]):
        raise ValueError("v2 experts require the pinned q4c variant-2 decoder")
    sets, ranges = {}, []
    with unc.open("rb") as stream:
        for label, first in [("A", 0), ("B", 10)]:
            reserve(samples, WEIGHTS_BYTES_PER_SET)
            gu = np.empty((TOP_K, 2 * INTERMEDIATE, WIDTH), dtype=np.float32)
            wd = np.empty((TOP_K, WIDTH, INTERMEDIATE), dtype=np.float32)
            for position, expert_id in enumerate(range(first, first + TOP_K)):
                reserve(samples, 2 * (2 * INTERMEDIATE * WIDTH * 4))
                gu[position], record = expert(stream, gate, expert_id, 2 * INTERMEDIATE)
                ranges.append(record)
                wd[position], record = expert(stream, down, expert_id, WIDTH)
                ranges.append(record)
            sets[label] = dict(gate_up=gu, down=wd, selected_experts=list(range(first, first + TOP_K)))
    native_after = native_identity(machine, source)
    if native_after != native_before:
        raise ValueError("native v2 checkpoint changed during sparse decode")
    reserve(samples)
    return sets, dict(scope="selected real v2 q4c expert weights only; no whole-head expansion",
                      checkpoint_source=source, checkpoint_unc=str(unc), checkpoint_sha256=CHECKPOINT_SHA256,
                      integrity_receipt_sha256=digest(integrity_path), machine_sha256=digest(machine_path),
                      native_identity=native_before, metadata_receipt_sha256=digest(metadata_path),
                      v2_header_sha256=actual["header_sha256"], v2_table_sha256=actual["table_sha256"],
                      decoder_sha256=DECODER_SHA256, reader_sha256=digest(__file__),
                      selected_source_ranges=ranges, source_bytes_read=sum(row["bytes"] for entry in ranges for row in entry["ranges"]),
                      metadata_bytes_read=actual["metadata_bytes_read"], decoded_fp32_bytes=2 * WEIGHTS_BYTES_PER_SET,
                      sparse_read_decode_ms=(time.perf_counter_ns() - started) / 1e6,
                      minimum_available_gib=min(row["available_bytes"] for row in samples) / GIB,
                      minimum_commit_headroom_gib=min(row["commit_headroom_bytes"] for row in samples) / GIB)
