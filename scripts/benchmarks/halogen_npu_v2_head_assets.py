"""Prepare integrity-bound v2 attention/HC and shared vocabulary external data.

CPU weight preparation only; no head/provider is built or run. HT output rows
use the recovered 0.15.0 NumPy reference with synthetic parity. Current 0.16.2
numerical equivalence and NPU integration remain unproven.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct

import numpy as np

from halogen_npu_mtp_metadata import metadata
from halogen_npu_v2_sparse import (
    CHECKPOINT_SHA256, METADATA_SHA256, WindowStream, native_identity, reserve,
)
from hgn_q4c_slice import decode_rows as decode_q4c_rows
from hgn_q8g64_slice import decode_rows as decode_q8_rows, row_geometry
from hgn_ht_slice import decode_rows as decode_ht_rows, HT_VARIANT


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKEND = ROOT / "backends/halogen-wsl2-0.16.2/.local"
DEFAULT_METADATA = Path(r"C:\AI\halogen-mtp-npu\v2-metadata-20261004\mtp-metadata.json")
SOURCE_BYTES = 66687678432
MAX_TILE_BYTES = 8 * 1024**2
MAX_WORKSPACE_BYTES = 64 * 1024**2
DEFAULT_OUTPUT_BYTES = 256 * 1024**2
MAX_OUTPUT_BYTES = 6 * 1024**3
MAX_TILES = 4096
MAX_JSON_BYTES = 8 * 1024**2
READER_FILES = ("halogen_npu_v2_head_assets.py", "hgn_q8g64_slice.py", "hgn_q4c_slice.py",
                "halogen_npu_v2_sparse.py", "halogen_npu_mtp_metadata.py", "hgn_ht_slice.py",
                "hgn_ht_slice.NOTICE.md", "hgn_ht_slice.LICENSE")
HT_REFERENCE = ("recovered 0.15.0 NumPy decoder; synthetic parity only; "
                "current 0.16.2 numerical equivalence and NPU integration unproven")


def small_bytes(path):
    path = Path(path)
    if not 0 < path.stat().st_size <= MAX_JSON_BYTES:
        raise ValueError("source/receipt exceeds bounded small-file budget: " + str(path))
    with path.open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if not 0 < len(data) <= MAX_JSON_BYTES:
        raise ValueError("source/receipt changed beyond small-file budget")
    return data


def small_digest(path):
    return hashlib.sha256(small_bytes(path)).hexdigest()


def reader_sources():
    return {name: small_digest(HERE / name) for name in READER_FILES}


def file_identity(value):
    return dict(size=value.st_size, device=value.st_dev, inode=value.st_ino,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def inspect_selected_table(path, expected, names):
    """Re-read only header/table; their frozen hashes bind additional shared rows."""
    with Path(path).open("rb") as stream:
        header = stream.read(104)
        if len(header) != 104:
            raise ValueError("truncated v2 header")
        magic, version, count, table, data, size = struct.unpack_from("<IIQQQQ", header)
        if (magic != 0x314e4748 or version != 2 or size != SOURCE_BYTES or
                count != expected["tensor_count"] or not 31 <= count <= 2500 or
                table < 104 or table + count * 160 > data or data % 64 or data > size):
            raise ValueError("v2 header/table bounds differ")
        stream.seek(table)
        table_bytes = stream.read(count * 160)
    if (len(table_bytes) != count * 160 or
            hashlib.sha256(header).hexdigest() != expected["header_sha256"] or
            hashlib.sha256(table_bytes).hexdigest() != expected["table_sha256"]):
        raise ValueError("v2 full header/table cryptographic binding differs")
    result = {}
    for at in range(0, len(table_bytes), 160):
        record = table_bytes[at:at + 160]
        name = record[:96].split(b"\0", 1)[0].decode("ascii")
        if name not in names:
            continue
        store, rank = struct.unpack_from("<II", record, 96)
        dims = list(struct.unpack_from("<qqqq", record, 104))[:rank]
        offset, length, checksum, variant = struct.unpack_from("<QQII", record, 136)
        if (name in result or not 1 <= rank <= 2 or any(value <= 0 for value in dims) or
                offset < data or offset % 64 or length <= 0 or length > size - offset):
            raise ValueError("invalid selected v2 tensor metadata: " + name)
        result[name] = dict(name=name, store=store, rank=rank, dims=dims, offset=offset,
                            size=length, xor32=checksum, variant=variant)
    if set(result) != set(names):
        raise ValueError("missing selected v2 tensor metadata")
    return result


def geometry(entry):
    dims = entry.get("dims")
    if (not isinstance(dims, list) or not 1 <= len(dims) <= 2 or
            any(type(value) is not int or value <= 0 for value in dims)):
        raise ValueError("invalid selected tensor geometry")
    width, count = dims[-1], math.prod(dims[:-1])
    if (type(entry.get("offset")) is not int or entry["offset"] < 0 or
            type(entry.get("size")) is not int or entry["size"] <= 0 or
            entry["offset"] + entry["size"] > SOURCE_BYTES):
        raise ValueError("selected tensor exceeds checkpoint extent")
    encoding = (entry.get("store"), entry.get("variant"))
    if entry["name"] == "lm_head.weight" and encoding != (16, HT_VARIANT):
        raise ValueError("store16 lm_head.weight export refused: unsupported variant; no embedding alias")
    if encoding == (7, 0):
        row_geometry(entry)
    elif encoding == (0, 0):
        if entry["size"] != count * width * 2:
            raise ValueError("BF16 payload size differs")
    elif encoding == (5, 2) and entry["name"] == "embed_tokens.weight":
        stride = ((width // 16 + 15) // 16) * 16
        encoded = 64 + ((count * (width // 2) + 63) // 64) * 64 + count * stride
        if dims != [248320, 2560] or width % 32 or encoded != entry["size"]:
            raise ValueError("shared q4c embedding geometry or payload differs")
    elif encoding == (16, HT_VARIANT) and entry["name"] == "lm_head.weight":
        if (entry.get("rank") != 2 or len(dims) != 2 or count % 128 or width % 128 or
                entry["size"] != count * width // 2):
            raise ValueError("HT head requires complete 128-row groups and exact packed size")
    else:
        raise ValueError("unsupported selected tensor encoding: " + entry["name"])
    return width, count


def ht_sideplanes(entry, sideplanes):
    width, count = geometry(entry)
    if not isinstance(sideplanes, dict) or set(sideplanes) != {"suh", "svh"}:
        raise ValueError("internally resolved HT side planes required")
    for key, dims in (("suh", [width]), ("svh", [count])):
        item = sideplanes[key]
        if (item.get("name") != "lm_head." + key or
                (item.get("store"), item.get("variant"), item.get("rank")) != (2, 0, 1) or
                item.get("dims") != dims or item.get("size") != dims[0] * 2 or
                type(item.get("offset")) is not int or item["offset"] < 0 or
                item["offset"] + item["size"] > SOURCE_BYTES):
            raise ValueError("HT side-plane metadata differs")
    spans = sorted((item["offset"], item["offset"] + item["size"])
                   for item in (entry, *sideplanes.values()))
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError("HT head and side-plane extents overlap")
    return sideplanes


def source_ranges(entry, row_start, rows, sideplanes=None):
    width, _ = geometry(entry)
    offset = entry["offset"]
    if entry["store"] == 7:
        stride = width + width // 16
        ranges = [(entry, offset + row_start * stride, rows * stride)]
    elif entry["store"] == 0:
        ranges = [(entry, offset + row_start * width * 2, rows * width * 2)]
    elif entry["store"] == 16:
        if row_start % 128 or rows % 128:
            raise ValueError("HT source ranges require aligned complete 128-row groups")
        planes = ht_sideplanes(entry, sideplanes)
        ranges = [(entry, offset + row_start * width // 2, rows * width // 2),
                  (planes["suh"], planes["suh"]["offset"], width * 2),
                  (planes["svh"], planes["svh"]["offset"] + row_start * 2, rows * 2)]
    else:
        count = math.prod(entry["dims"][:-1])
        stride = ((width // 16 + 15) // 16) * 16
        scale_base = offset + 64 + ((count * (width // 2) + 63) // 64) * 64
        ranges = [(entry, offset, 64), (entry, offset + 64 + row_start * (width // 2), rows * (width // 2)),
                  (entry, scale_base + row_start * stride, rows * stride)]
    if any(start < owner["offset"] or length <= 0 or start + length > owner["offset"] + owner["size"]
           for owner, start, length in ranges):
        raise ValueError("planned row range exceeds declared tensor")
    return [dict(name=owner["name"], offset=start, bytes=length) for owner, start, length in ranges]


def tensor_plan(entry, row_start, rows, tile_bytes, output_offset, sideplanes=None):
    width, count = geometry(entry)
    if (type(row_start) is not int or not 0 <= row_start < count or
            (rows is not None and (type(rows) is not int or not 0 < rows <= count - row_start))):
        raise ValueError("selected row span exceeds tensor")
    rows = count - row_start if rows is None else rows
    tile_rows = tile_bytes // (width * 4)
    if entry["store"] == 16:
        ht_sideplanes(entry, sideplanes)
        if row_start % 128 or rows % 128:
            raise ValueError("HT row span must contain aligned complete 128-row groups")
        tile_rows = tile_rows // 128 * 128
    if tile_rows < 1 or math.ceil(rows / tile_rows) > MAX_TILES:
        raise ValueError("tile budget cannot represent the bounded row selection")
    tiles = []
    for start in range(row_start, row_start + rows, tile_rows):
        amount = min(tile_rows, row_start + rows - start)
        ranges = source_ranges(entry, start, amount, sideplanes)
        decoded = amount * width * 4
        if entry["store"] == 16:
            # The decoder retains the tile while unpacking one 128-row group.
            # Budget codes/states/rotation/matmul temporaries and cached tables
            # independently of tile size; 4*decoded undercounts small HT tiles.
            workspace = decoded + 12 * (128 * width * 4) + 8 * 1024**2
        else:
            workspace = 4 * decoded
        workspace += sum(item["bytes"] for item in ranges)
        if workspace > MAX_WORKSPACE_BYTES:
            raise ValueError("tile exceeds the 64 MiB allocation/I/O workspace budget")
        tiles.append(dict(row_start=start, rows=amount, decoded_bytes=decoded,
                          workspace_bytes=workspace, source_ranges=ranges,
                          output_offset=output_offset + (start - row_start) * width * 4))
    shape = entry["dims"] if row_start == 0 and rows == count else [rows, width]
    return dict(entry=entry, row_start=row_start, rows=rows, output_shape=shape,
                output_offset=output_offset, output_bytes=rows * width * 4, tiles=tiles,
                sideplanes=sideplanes, reference=HT_REFERENCE if entry["store"] == 16 else "stored q8/q4c/BF16 decoder")


def prepare(metadata_path, integrity_path, machine_path, out, names, row_start=0,
            rows=None, tile_bytes=MAX_TILE_BYTES, max_output_bytes=DEFAULT_OUTPUT_BYTES):
    if (not names or len(names) != len(set(names)) or len(names) > 26 or
            any(not isinstance(name, str) for name in names)):
        raise ValueError("explicit unique tensor names required")
    if (type(tile_bytes) is not int or not 1 <= tile_bytes <= MAX_TILE_BYTES or
            type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES):
        raise ValueError("invalid bounded tile or total output budget")
    paths = dict(metadata=str(Path(metadata_path).resolve()), integrity=str(Path(integrity_path).resolve()),
                 machine=str(Path(machine_path).resolve()))
    raw = {key: small_bytes(path) for key, path in paths.items()}
    hashes = {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()}
    if hashes["metadata"] != METADATA_SHA256:
        raise ValueError("frozen v2 metadata receipt differs")
    expected = json.loads(raw["metadata"])["sources"]["v2"]
    allowed = {item["name"] for item in expected["entries"]
               if not item["name"].startswith("mtp.layers.0.mlp.")}
    if not set(names) <= allowed | {"embed_tokens.weight", "lm_head.weight"}:
        raise ValueError("selection outside attention/HC/shared embedding-output scope")
    integrity, machine = json.loads(raw["integrity"]), json.loads(raw["machine"])
    if (integrity.get("sha256") != CHECKPOINT_SHA256 or
            integrity.get("identity", {}).get("size") != SOURCE_BYTES):
        raise ValueError("complete v2 integrity receipt differs")
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", machine["distro"]) or
            not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", machine["user"])):
        raise ValueError("invalid native metadata identity target")
    source = machine["models"] + "/qwen38-flash-next-v2.hgn"
    unc = Path("\\\\wsl.localhost\\" + machine["distro"] + source.replace("/", "\\"))
    if str(unc) != expected["path"]:
        raise ValueError("machine source differs from the frozen v2 path")
    samples = []
    reserve(samples, MAX_WORKSPACE_BYTES)
    before = native_identity(machine, source)
    if before != integrity["identity"]:
        raise ValueError("native checkpoint identity differs from complete integrity receipt")
    actual = metadata(unc)
    if any(actual[key] != expected[key] for key in
           ("identity", "file_size", "version", "tensor_count", "header_sha256", "table_sha256", "entries")):
        raise ValueError("v2 metadata differs from frozen receipt")
    table_names = list(names)
    if "lm_head.weight" in names:
        table_names += ["lm_head.suh", "lm_head.svh"]
    entries = inspect_selected_table(unc, expected, table_names)
    tensors, total = [], 0
    for name in names:
        planes = None
        if name == "lm_head.weight":
            if entries[name]["dims"] != [248320, 2560]:
                raise ValueError("frozen shared vocabulary head geometry differs")
            planes = {key: entries["lm_head." + key] for key in ("suh", "svh")}
        item = tensor_plan(entries[name], row_start, rows, tile_bytes, total, planes)
        total += item["output_bytes"]
        if total > max_output_bytes:
            raise ValueError("selected external data exceeds explicit total output budget")
        tensors.append(item)
    if sum(len(item["tiles"]) for item in tensors) > MAX_TILES:
        raise ValueError("selection exceeds bounded tile/receipt count")
    if native_identity(machine, source) != before:
        raise ValueError("native checkpoint changed during metadata preparation")
    if hashes != {key: small_digest(path) for key, path in paths.items()}:
        raise ValueError("lineage receipt changed during metadata preparation")
    return dict(schema=1, scope=__doc__, paths=paths, parameters=dict(out=str(Path(out).resolve()),
                names=list(names), row_start=row_start, rows=rows, tile_bytes=tile_bytes,
                max_output_bytes=max_output_bytes), reader_sources=reader_sources(),
                source=dict(checkpoint_sha256=CHECKPOINT_SHA256, checkpoint_source=source,
                            checkpoint_unc=str(unc), native_identity=before, receipt_sha256=hashes,
                            header_sha256=actual["header_sha256"], table_sha256=actual["table_sha256"],
                            metadata_bytes_read=2 * actual["metadata_bytes_read"]),
                dtype="little-endian FP32; stored row orientation; HT: " + HT_REFERENCE,
                output_bytes=total, tensors=tensors)


def output_paths(plan):
    prefix = plan["parameters"]["out"]
    return {key: Path(prefix + suffix) for key, suffix in
            (("data", ".data"), ("receipt", ".json"), ("plan", ".plan.json"),
             ("partial", ".data.partial"), ("lock", ".lock"))}


def write_json_exclusive(path, value):
    data = json.dumps(value, indent=2, allow_nan=False).encode("utf-8")
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("publication exceeds bounded receipt budget")
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def decode_tile(window, tensor, tile):
    """Decode an already bounded in-memory source window; no file/provider I/O."""
    entry = tensor["entry"]
    width, _ = geometry(entry)
    if (not 0 < tile["decoded_bytes"] <= MAX_TILE_BYTES or
            not 0 < tile["workspace_bytes"] <= MAX_WORKSPACE_BYTES or
            tile["source_ranges"] != source_ranges(entry, tile["row_start"], tile["rows"], tensor["sideplanes"])):
        raise ValueError("tile differs from bounded source/geometry plan")
    decoder_receipt = None
    if entry["store"] == 7:
        value = decode_q8_rows(window, entry, tile["row_start"], tile["rows"])
    elif entry["store"] == 5:
        value = decode_q4c_rows(window, entry, tile["row_start"], tile["rows"])
    elif entry["store"] == 16:
        planes = ht_sideplanes(entry, tensor["sideplanes"])
        value, decoder_receipt = decode_ht_rows(window, entry, tile["row_start"], tile["rows"],
                                                planes["suh"], planes["svh"])
    else:
        item = tile["source_ranges"][0]
        window.seek(item["offset"])
        payload = window.read(item["bytes"])
        if len(payload) != item["bytes"]:
            raise ValueError("truncated BF16 tile")
        value = (np.frombuffer(payload, dtype="<u2").astype(np.uint32) << 16).view(np.float32)
    value = np.ascontiguousarray(value, dtype="<f4").reshape(tile["rows"], width)
    if value.nbytes != tile["decoded_bytes"] or not np.isfinite(value).all():
        raise ValueError("nonfinite or incorrectly sized external-data tile")
    return value, decoder_receipt


def extract(prepared_plan, prepared_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", prepared_sha256):
        raise ValueError("independent prepared-plan SHA256 required")
    raw = small_bytes(prepared_plan)
    if hashlib.sha256(raw).hexdigest() != prepared_sha256:
        raise ValueError("prepared plan identity differs")
    plan = json.loads(raw)
    p = plan["parameters"]
    fresh = prepare(plan["paths"]["metadata"], plan["paths"]["integrity"], plan["paths"]["machine"], **p)
    if fresh != plan:
        raise ValueError("prepared source/geometry/decoder plan changed; refuse payload read")
    paths = output_paths(plan)
    if any(paths[key].exists() for key in ("data", "receipt", "partial", "lock")):
        raise FileExistsError("existing complete/partial external data or writer refused")
    paths["data"].parent.mkdir(parents=True, exist_ok=True)
    with paths["lock"].open("x", encoding="utf-8"):
        machine = json.loads(small_bytes(plan["paths"]["machine"]))
        samples, records, complete_hash = [], [], hashlib.sha256()
        with Path(plan["source"]["checkpoint_unc"]).open("rb") as source, paths["partial"].open("xb", buffering=0) as output:
            before = file_identity(os.fstat(source.fileno()))
            if (before["size"] != SOURCE_BYTES or
                    native_identity(machine, plan["source"]["checkpoint_source"]) != plan["source"]["native_identity"]):
                raise ValueError("native source identity changed immediately before payload read")
            for tensor in plan["tensors"]:
                entry = tensor["entry"]
                geometry(entry)
                for tile in tensor["tiles"]:
                    reserve(samples, tile["workspace_bytes"])
                    ranges, lineage = [], []
                    for item in tile["source_ranges"]:
                        source.seek(item["offset"])
                        payload = source.read(item["bytes"])
                        if len(payload) != item["bytes"]:
                            raise ValueError("truncated prepared source range")
                        ranges.append((item["offset"], payload))
                        lineage.append(dict(item, sha256=hashlib.sha256(payload).hexdigest()))
                    window = WindowStream(ranges)
                    value, decoder_receipt = decode_tile(window, tensor, tile)
                    view = memoryview(value).cast("B")
                    if output.tell() != tile["output_offset"]:
                        raise ValueError("external-data output offset drift")
                    decoded_sha256 = hashlib.sha256(view).hexdigest()
                    complete_hash.update(view)
                    while view:
                        written = output.write(view)
                        if not written:
                            raise OSError("short external-data write")
                        view = view[written:]
                    os.fsync(output.fileno())
                    records.append(dict(tensor=entry["name"], row_start=tile["row_start"], rows=tile["rows"],
                                        output_offset=tile["output_offset"], output_bytes=tile["decoded_bytes"],
                                        decoded_sha256=decoded_sha256, source_ranges=lineage,
                                        reference=tensor["reference"], decoder_receipt=decoder_receipt))
                    del view, value, payload, ranges, window, decoder_receipt
                    reserve(samples)
            if output.tell() != plan["output_bytes"] or file_identity(os.fstat(source.fileno())) != before:
                raise ValueError("output extent or open source identity changed")
        after = native_identity(machine, plan["source"]["checkpoint_source"])
        if after != plan["source"]["native_identity"] or reader_sources() != plan["reader_sources"]:
            raise ValueError("native source/decoder identity changed; partial data retained without receipt")
        if plan["source"]["receipt_sha256"] != {key: small_digest(path) for key, path in plan["paths"].items()}:
            raise ValueError("raw lineage receipt changed; partial data retained without receipt")
        receipt = dict(schema=1, scope=__doc__, prepared_plan=str(Path(prepared_plan).resolve()),
                       prepared_plan_sha256=prepared_sha256, source=plan["source"],
                       reader_sources=plan["reader_sources"], source_identity_after=after,
                       data=str(paths["data"]), data_bytes=plan["output_bytes"], data_sha256=complete_hash.hexdigest(),
                       source_bytes_read=sum(row["bytes"] for record in records for row in record["source_ranges"]),
                       dtype=plan["dtype"], tiles=records,
                       tensors=[dict(name=item["entry"]["name"], source_entry=item["entry"],
                                     row_start=item["row_start"], rows=item["rows"], shape=item["output_shape"],
                                     sideplanes=item["sideplanes"], reference=item["reference"],
                                     external_data=dict(location=paths["data"].name, offset=item["output_offset"],
                                                        length=item["output_bytes"])) for item in plan["tensors"]],
                       minimum_available_gib=min(row["available_bytes"] for row in samples) / 2**30,
                       minimum_commit_headroom_gib=min(row["commit_headroom_bytes"] for row in samples) / 2**30)
        # Only verified data receives its final name and completion receipt.
        os.rename(paths["partial"], paths["data"])
        write_json_exclusive(paths["receipt"], receipt)
    paths["lock"].unlink()
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--extract", action="store_true")
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--integrity", type=Path, default=BACKEND / "v2-integrity.json")
    parser.add_argument("--machine", type=Path, default=BACKEND / "machine.json")
    parser.add_argument("--tensor", action="append")
    parser.add_argument("--row-start", type=int, default=0)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--tile-bytes", type=int, default=MAX_TILE_BYTES)
    parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_OUTPUT_BYTES)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--prepared-plan", type=Path)
    parser.add_argument("--prepared-plan-sha256")
    args = parser.parse_args(argv)
    if args.prepare_only:
        if args.out is None or not args.tensor or args.prepared_plan or args.prepared_plan_sha256:
            parser.error("prepare-only requires --out and explicit --tensor; no prepared-plan inputs")
        plan = prepare(args.metadata, args.integrity, args.machine, args.out, args.tensor,
                       args.row_start, args.rows, args.tile_bytes, args.max_output_bytes)
        paths = output_paths(plan)
        if any(path.exists() for path in paths.values()):
            raise FileExistsError("existing plan/data/receipt/partial writer refused")
        paths["plan"].parent.mkdir(parents=True, exist_ok=True)
        write_json_exclusive(paths["plan"], plan)
        print(json.dumps(dict(plan=str(paths["plan"]), plan_sha256=small_digest(paths["plan"]),
                              output_bytes=plan["output_bytes"], checkpoint_payload_bytes_read=0,
                              tensors=[item["entry"]["name"] for item in plan["tensors"]]), indent=2))
    else:
        if args.prepared_plan is None or args.prepared_plan_sha256 is None or args.tensor or args.out:
            parser.error("extract requires independent --prepared-plan and SHA256; selection comes from that plan")
        receipt = extract(args.prepared_plan, args.prepared_plan_sha256)
        print(json.dumps(dict(data=receipt["data"], receipt=receipt["data"][:-5] + ".json",
                              data_bytes=receipt["data_bytes"], data_sha256=receipt["data_sha256"]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
