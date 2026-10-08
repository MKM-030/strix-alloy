"""CPU metadata-only plan for exact current IDs over complete original HT blocks.

Reads the pinned small OCI vocabulary layer and existing metadata plan only.
Never opens checkpoint/model payloads, imports a backend, or runs accelerators.
An HT block contains 128 transformed output rows: it is not 128 independent
packed token rows. Plans preserve that block and mask outputs after rotation.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import struct
import tarfile

BASE = Path(__file__).resolve().parent.parent
LAYER_SHA = "4e6e9b3296da3f75cce57dadc0e3f3df9a74337d6a64143af8e2fb466b58c282"
ASSET_SHA = "cc322dc326c0ac39df81342211cbca196d83fc8dc3cc3a03d78120b5d1bf8c99"
PLAN_SHA = "83f5268efc74afd2459800394125b284e7748a73b06db760b5d0567f1fbab4e7"
DECODER_SHA = "4e0c72fdf63d8e1c12ed90c11f9400aa65ee3f531a9157a8257d6ebb899bd3c7"
DEFAULT_PLAN = Path(r"C:\AI\halogen-mtp-npu\v2-head-assets-20261004-postreboot\lmhead128.plan.json")
ROOT = BASE.parents[3]
WIDTH, FULL_ROWS, BLOCK_ROWS = 2560, 248320, 128
BLOCK_BYTES = BLOCK_ROWS * WIDTH // 2


def pinned_small(path: Path, expected: str, maximum: int) -> bytes:
    if not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise ValueError(f"small regular source missing/exceeds bound: {path}")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"source pin differs: {path}")
    return data


def vocab() -> tuple[bytes, list[int], list[dict]]:
    layer = BASE / "oci-layout/blobs/sha256" / LAYER_SHA
    raw = pinned_small(layer, LAYER_SHA, 1024 * 1024)
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:
        unpacked = source.read(4 * 1024 * 1024 + 1)
    if len(unpacked) > 4 * 1024 * 1024:
        raise ValueError("bounded vocabulary layer expansion exceeded")
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as source:
        matches = [m for m in source.getmembers() if m.name == "opt/halogen/draft-vocab.lists"]
        if len(matches) != 1 or not matches[0].isreg() or matches[0].size != 795612:
            raise ValueError("regular packaged vocabulary member differs")
        asset = source.extractfile(matches[0]).read(795613)
    if len(asset) != 795612 or hashlib.sha256(asset).hexdigest() != ASSET_SHA:
        raise ValueError("exact current packaged ID asset differs")
    magic, version, full, count, groups, reserved0, reserved1 = struct.unpack_from("<8s6I", asset)
    if (magic, version, full, count, groups, reserved0, reserved1) != (b"HGDVOC1\0", 1, FULL_ROWS, 198759, 17, 0, 0):
        raise ValueError("packaged header differs")
    if len(asset) != 32 + count * 4 + groups * 32:
        raise ValueError("packaged extent differs")
    ids = list(struct.unpack_from(f"<{count}I", asset, 32))
    if max(ids) >= FULL_ROWS:
        raise ValueError("out-of-range pooled token")
    result = []
    for at in range(32 + count * 4, len(asset), 32):
        name, core, tail, amount, reserved = struct.unpack_from("<16s4I", asset, at)
        name = name.split(b"\0", 1)[0].decode("ascii")
        if not name or not 0 < core <= count or tail + amount > count or (amount and tail < core) or reserved:
            raise ValueError("group descriptor bounds differ")
        selected = ids[:core] + ids[tail:tail + amount]
        if len(set(selected)) != len(selected):
            raise ValueError("duplicate selected token")
        result.append(dict(name=name, core_count=core, tail_offset=tail, tail_count=amount, ids=selected))
    if len({g["name"] for g in result}) != groups:
        raise ValueError("duplicate group name")
    return asset, ids, result


def merged_ranges(blocks: list[int], entry: dict, stride: int) -> list[dict]:
    result = []
    for block in blocks:
        at = entry["offset"] + block * stride
        if result and result[-1]["offset"] + result[-1]["bytes"] == at:
            result[-1]["bytes"] += stride
        else:
            result.append(dict(offset=at, bytes=stride))
    if any(r["offset"] < entry["offset"] or r["offset"] + r["bytes"] > entry["offset"] + entry["size"] for r in result):
        raise ValueError("planned source ranges exceed selected entry")
    return result


def selection(name: str, ids: list[int], entry: dict, planes: dict) -> dict:
    blocks = sorted({token // BLOCK_ROWS for token in ids})
    q4_bytes = len(ids) * 1440
    packed_bytes = len(blocks) * BLOCK_BYTES
    # For each selected logit ordinal: token/128 identifies the SOURCE block;
    # token%128 identifies its output lane after the inverse output transform.
    raw_ids = struct.pack(f"<{len(ids)}I", *ids)
    return dict(name=name, exact_selected_rows=len(ids), selected_order_sha256=hashlib.sha256(raw_ids).hexdigest(),
                required_original_blocks=len(blocks), required_original_output_rows=len(blocks) * BLOCK_ROWS,
                required_packed_bytes=packed_bytes, required_svh_bytes=len(blocks) * BLOCK_ROWS * 2,
                selected_svh_bytes_for_custom_masked_output_kernel=len(ids) * 2,
                selected_svh_source_offset="sideplanes.svh.offset + 2*token_id; exact packaged output order",
                shared_suh_bytes=WIDTH * 2, stock_q4_selected_payload_and_scales_bytes=q4_bytes,
                original_block_payload_vs_q4_selected_ratio=packed_bytes / q4_bytes,
                original_block_fraction=len(blocks) / (FULL_ROWS // BLOCK_ROWS),
                independent_token_packed_gather_valid=False,
                source_blocks=blocks, payload_ranges=merged_ranges(blocks, entry, BLOCK_BYTES),
                svh_ranges=merged_ranges(blocks, planes["svh"], BLOCK_ROWS * 2),
                output_selection="preserve original block output H128, then gather token lane; retain IDs in packaged order")


def build(metadata_path: Path) -> tuple[bytes, dict]:
    raw_plan = pinned_small(metadata_path, PLAN_SHA, 1024 * 1024)
    decoder = ROOT / "scripts/benchmarks/hgn_ht_slice.py"
    pinned_small(decoder, DECODER_SHA, 1024 * 1024)
    old = json.loads(raw_plan)
    tensor = old["tensors"][0]
    entry, planes = tensor["entry"], tensor["sideplanes"]
    if (entry["name"], entry["store"], entry["variant"], entry["dims"], entry["size"]) != ("lm_head.weight", 16, 0x1208, [FULL_ROWS, WIDTH], FULL_ROWS * WIDTH // 2):
        raise ValueError("original HT geometry differs")
    for key, rows in (("suh", WIDTH), ("svh", FULL_ROWS)):
        p = planes[key]
        if (p["name"], p["store"], p["variant"], p["dims"], p["size"]) != ("lm_head." + key, 2, 0, [rows], rows * 2):
            raise ValueError("HT sideplane geometry differs")
    asset, ids, groups = vocab()
    selected = [selection("pool", ids, entry, planes)]
    selected += [selection(g["name"], g["ids"], entry, planes) | {k: g[k] for k in ("core_count", "tail_offset", "tail_count")} for g in groups]
    return asset, dict(schema=1, scope=__doc__, source_payload_read=False, hardware_or_wsl_called=False,
                      exact_native0172_final_queries_available=False, exact_native0172_q4_rows_available=False,
                      lowrank_accuracy_evaluation_ready=False, original_row_gather_valid=False,
                      block_layout="[O/128, K/16, 8 output tiles, 32 little-endian uint32]; cyclic256-nibble trellis",
                      transform="W = diag(svH) * H128_output * decoded_rotated * H128_input * diag(suH)",
                      transform_evidence="existing recovered0.15 reference; native0172 device confirmation required",
                      plan_sha256=PLAN_SHA, decoder_sha256=DECODER_SHA, exact_id_asset_sha256=ASSET_SHA,
                      id_layer_sha256=LAYER_SHA, retained_source=old["source"], tensor_entry=entry, sideplanes=planes,
                      block_rows=BLOCK_ROWS, block_bytes=BLOCK_BYTES, selections=selected,
                      bounded_later_export=dict(max_extra_memory_bytes=64 * 1024**2, max_tile_blocks=32,
                          payload_tile_bytes=32 * BLOCK_BYTES, output="original complete blocks plus IDs; no BF16/Q4 re-encoding",
                          gates="current metadata/source lineage revalidation, explicit root-owned payload window, exact full-HT selected-logit oracle"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    asset, plan = build(args.metadata_plan)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in (("exact-draft-vocab.lists", asset), ("original-ht-block-plan.json", json.dumps(plan, indent=2, allow_nan=False).encode())):
        destination = args.out / name
        if destination.exists():
            if destination.read_bytes() != data:
                raise FileExistsError(f"existing different asset preserved: {destination}")
        else:
            with destination.open("xb") as stream:
                stream.write(data)
    print(json.dumps({"source_payload_read": False, "id_asset_sha256": ASSET_SHA,
          "summary": [{k: s[k] for k in ("name", "exact_selected_rows", "required_original_blocks", "required_packed_bytes", "original_block_payload_vs_q4_selected_ratio")} for s in plan["selections"]]}, indent=2))


if __name__ == "__main__":
    main()
