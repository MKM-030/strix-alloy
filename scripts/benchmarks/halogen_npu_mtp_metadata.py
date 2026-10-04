"""Bounded metadata-only v2/w4b MTP comparison; never decode model payloads."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from host_frames import frame


GIB = 1024**3


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reserve(samples):
    current = frame()
    samples.append(current)
    if min(current["available_bytes"], current["commit_headroom_bytes"]) < 18 * GIB:
        raise RuntimeError("18 GiB physical/commit reserve unavailable")


def metadata(path):
    before = path.stat()
    with path.open("rb") as stream:
        header = stream.read(104)
        if len(header) != 104:
            raise ValueError("truncated HGN header")
        magic, version = struct.unpack_from("<II", header)
        count, table, _, size = struct.unpack_from("<QQQQ", header, 8)
        if magic != 0x314e4748 or version != 2 or size != before.st_size:
            raise ValueError("HGN header identity or bounds differ")
        if not 31 <= count <= 2500 or table < 104 or table + 160 * count > size:
            raise ValueError("tensor table exceeds the bounded metadata budget")
        stream.seek(table)
        table_bytes = stream.read(160 * count)
        if len(table_bytes) != 160 * count:
            raise ValueError("truncated HGN tensor table")
    entries = []
    for start in range(0, len(table_bytes), 160):
        record = table_bytes[start:start + 160]
        name = record[:96].split(b"\0", 1)[0].decode("ascii")
        if not name.startswith("mtp."):
            continue
        store, rank = struct.unpack_from("<II", record, 96)
        dims = list(struct.unpack_from("<qqqq", record, 104))[:rank]
        offset, length = struct.unpack_from("<QQ", record, 136)
        checksum, variant = struct.unpack_from("<II", record, 152)
        if not 1 <= rank <= 4 or any(value <= 0 for value in dims) or offset + length > size:
            raise ValueError("invalid MTP metadata geometry or bounds")
        entries.append(dict(name=name, store=store, rank=rank, dims=dims, offset=offset,
                            size=length, xor32=checksum, variant=variant))
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("checkpoint changed during metadata read")
    if len(entries) != 31 or len({entry["name"] for entry in entries}) != 31:
        raise ValueError("expected 31 unique MTP records")
    return dict(path=str(path), file_size=size, version=version, tensor_count=count,
                identity=header[40:104].split(b"\0", 1)[0].decode("ascii"),
                metadata_bytes_read=104 + len(table_bytes), mtime_ns=before.st_mtime_ns,
                header_sha256=hashlib.sha256(header).hexdigest(),
                table_sha256=hashlib.sha256(table_bytes).hexdigest(), entries=entries)


def compare(v2_path, w4b_path, manifest_path):
    samples = []
    reserve(samples)
    w4b = metadata(w4b_path)
    reserve(samples)
    v2 = metadata(v2_path)
    reserve(samples)
    extracted = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = {entry["name"]: entry for entry in extracted["entries"]}
    for entry in w4b["entries"]:
        if any(entry[key] != manifest[entry["name"]][key] for key in
               ["store", "rank", "dims", "offset", "size", "xor32", "variant"]):
            raise ValueError("existing w4b extracted manifest metadata differs")
    left = {entry["name"]: entry for entry in w4b["entries"]}
    right = {entry["name"]: entry for entry in v2["entries"]}
    if left.keys() != right.keys():
        raise ValueError("MTP tensor name sets differ")
    rows = []
    for name in sorted(left):
        a, b = left[name], right[name]
        rows.append(dict(name=name, geometry_equal=a["dims"] == b["dims"],
                         encoding_equal=(a["store"], a["variant"]) == (b["store"], b["variant"]),
                         size_equal=a["size"] == b["size"], xor32_equal=a["xor32"] == b["xor32"],
                         w4b_store=a["store"], v2_store=b["store"],
                         w4b_variant=a["variant"], v2_variant=b["variant"],
                         w4b_xor32=a["xor32"], v2_xor32=b["xor32"]))
    gate = right["mtp.layers.0.mlp.experts.gate_up_proj.weight"]
    down = right["mtp.layers.0.mlp.experts.down_proj.weight"]

    def selected_payload(entry, rows):
        width = entry["dims"][-1]
        return rows * (width // 2 + width // 32 * 2) + 64

    plan = dict(selected_experts=list(range(10)), width=gate["dims"][-1],
                intermediate=gate["dims"][-2] // 2,
                gate_up_decoded_shape=[10, *gate["dims"][1:]],
                down_decoded_shape=[10, *down["dims"][1:]],
                gate_up_runtime_shape=[10, gate["dims"][-1], gate["dims"][-2]],
                down_runtime_shape=[10, down["dims"][-1], down["dims"][-2]],
                decoded_fp32_weights_bytes=10 * (math.prod(gate["dims"][1:]) + math.prod(down["dims"][1:])) * 4,
                selected_q4c_payload_bytes=selected_payload(gate, 10 * gate["dims"][-2]) + selected_payload(down, 10 * down["dims"][-2]),
                sparse_decoder_compatible=(gate["store"], gate["variant"], down["store"], down["variant"]) == (5, 2, 5, 2),
                frozen_read_top10_identity_compatible=v2["identity"] == "qwen3.8-flash-next",
                full_head_expansion_needed=False)
    return dict(schema=1, scope="metadata only; no payload decode, whole-file hash, accelerator or whole-head expansion",
                script_sha256=digest(__file__), sources={"w4b": w4b, "v2": v2},
                existing_w4b_manifest_sha256=digest(manifest_path), comparisons=rows,
                all_geometry_equal=all(row["geometry_equal"] for row in rows),
                all_encoding_equal=all(row["encoding_equal"] for row in rows),
                all_sizes_equal=all(row["size_equal"] for row in rows),
                all_xor32_equal=all(row["xor32_equal"] for row in rows),
                mtp_byte_identity_established=False,
                identity_limitation="Matching XOR32 is not cryptographic payload equality; v2 MTP payload SHA256 was not computed",
                selected_conversion_plan=plan, memory_samples=samples,
                minimum_available_gib=min(sample["available_bytes"] for sample in samples) / GIB,
                minimum_commit_headroom_gib=min(sample["commit_headroom_bytes"] for sample in samples) / GIB)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v2", type=Path, required=True)
    parser.add_argument("--w4b", type=Path, required=True)
    parser.add_argument("--w4b-manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("completed metadata receipt exists; overwrite refused")
    result = compare(args.v2, args.w4b, args.w4b_manifest)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ["sources", "comparisons", "memory_samples"]}, indent=2))
    print(json.dumps({"report": str(args.report), "report_sha256": digest(args.report),
                      "metadata_bytes_read": {name: value["metadata_bytes_read"] for name, value in result["sources"].items()},
                      "differences": [row for row in result["comparisons"] if not all(row[key] for key in
                                      ["geometry_equal", "encoding_equal", "size_equal", "xor32_equal"])]}, indent=2))


if __name__ == "__main__":
    main()
