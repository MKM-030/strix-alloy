# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Strict offline proof of emitted transfers/allocations and retained map inventory.

Reads compiler text and artifact bytes only. Never imports compiler or devices.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integers(text: str) -> list[int]:
    return [int(v.strip()) for v in text.split(",")]


def transfers(text: str) -> list[dict]:
    pattern = re.compile(r"aiex\.npu\.dma_memcpy_nd\(%arg(\d+)\[([^\]]+)\]\[([^\]]+)\]\[([^\]]+)\]\)\s*\{([^}]+)\}\s*:\s*memref<([^>]+)>")
    result = []
    for match in pattern.finditer(text):
        arg, offsets, sizes, strides, attrs, typ = match.groups()
        metadata = re.search(r"metadata = @([\w]+)", attrs)
        require(metadata is not None, "DMA has no named metadata")
        name = metadata.group(1).removesuffix("_shim_alloc")
        kind, col = re.fullmatch(r"(input|weight|output)_host_c(\d+)", name).groups()
        element_bytes = 1 if typ.endswith(("xi8", "xui8")) else 2 if typ.endswith(("xi16", "xui16")) else 0
        require(element_bytes != 0, "unexpected DMA type")
        values = integers(sizes)
        result.append({"kind": "weights" if kind == "weight" else kind, "column": int(col), "bo": int(arg),
            "element_bytes": element_bytes, "base_element": sum(integers(offsets)),
            "sizes": values, "strides": integers(strides), "bytes": math.prod(values) * element_bytes})
        if kind in ("weight", "input"):
            require("issue_token = true" in attrs, "MM2S completion token missing")
    return result


def canonical_transfer(value: dict) -> dict:
    """Preserve the ordered address traversal through compiler dimension folding."""
    axes = [(n, stride) for n, stride in zip(value["sizes"], value["strides"]) if n != 1]
    index = len(axes) - 2
    while index >= 0:
        left, right = axes[index], axes[index + 1]
        if left[1] == right[0] * right[1]:
            axes[index:index + 2] = [(left[0] * right[0], right[1])]
        index -= 1
    return {**value, "sizes": [n for n, _ in axes], "strides": [stride for _, stride in axes]}


def allocations(text: str) -> dict:
    tiles = {name: (int(c), int(r)) for name, c, r in re.findall(r"(%[\w]+) = aie\.tile\((\d+), (\d+)\)", text)}
    result = {}
    for tile_name, attrs, typ in re.findall(r"aie\.buffer\((%[\w]+)\)\s*\{([^}]+)\}\s*:\s*memref<([^>]+)>", text):
        address = re.search(r"address = (\d+) : i32", attrs)
        symbol = re.search(r'sym_name = "([^"\n]+)"', attrs)
        require(address is not None and symbol is not None, "unaddressed/unnamed emitted buffer")
        dims = typ.split("x")
        element = dims.pop()
        require(element in ("i8", "ui8", "i16", "ui16", "i32", "f32"), "unexpected buffer type")
        size = math.prod(int(d) for d in dims) * {"i8": 1, "ui8": 1, "i16": 2, "ui16": 2, "i32": 4, "f32": 4}[element]
        column, row = tiles[tile_name]
        result.setdefault(f"{column},{row}", []).append({"name": symbol.group(1), "address": int(address.group(1)), "bytes": size, "type": typ})
    for column in range(8):
        for row in range(2, 6):
            key = f"{column},{row}"; require(key in result, "missing worker allocation " + key)
            objects = result[key]
            require(sum(v["bytes"] == 20480 for v in objects) == 1, "worker must have exactly one whole hidden input buffer")
            require(any(v["name"] == f"partial_c{column}_w{row - 2}" and v["bytes"] == 4096 for v in objects), "partial allocation missing")
            require(not any(v["name"].startswith("decoded_") for v in objects), "per-projection decode scratch must be absent")
            require(sum(v["bytes"] == 8192 for v in objects) == 2, "worker requires exactly two BF16 streamed weight buffers")
            vector_objects = [v for v in objects if v["bytes"] in (8192, 20480)]
            require(len(vector_objects) == 3 and all(v["address"] % 64 == 0 for v in vector_objects),
                    "all worker input/weight buffers require64-byte vector load alignment")
            require(sum(v["bytes"] == 128 for v in objects) == 2, "worker output buffers missing")
    for key, objects in result.items():
        _, row = map(int, key.split(","))
        # Installed AIETargetModel.h BaseAIE2TargetModel::getMemTileSize()
        # is0x80000:512KiB per memtile, and64KiB compute local memory.
        # Bank-aware allocation spreads small buffers beyond the first256KiB.
        limit = 524288 if row == 1 else 65536
        intervals = sorted((v["address"], v["address"] + v["bytes"], v["name"]) for v in objects)
        for start, end, name in intervals:
            require(start >= (4096 if row >= 2 else 0) and end <= limit, f"buffer/declared stack bounds failed {key}:{name}")
        for left, right in zip(intervals, intervals[1:]):
            require(left[1] <= right[0], f"buffer overlap {key}:{left[2]}/{right[2]}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args()
    base = args.dir.resolve(); intermediate = base / "intermediates"
    source = base / "design.mlir"; addressed = intermediate / "input_with_addresses.mlir"
    physical = intermediate / "input_physical.mlir"; lowered = intermediate / "main_npu_lowered.mlir"
    schedule = json.loads((base / "schedule.json").read_text(encoding="utf-8"))
    require(schedule["format"] == "halogen-native-hidden-vector-source-schedule-v1", "wrong vector source schedule format")
    require(schedule["weight_layout"] == "row16,pair8,component2,lane16"
            and schedule["input_layout"] == "stream4,Kchunk10,pair8,component2,lane16"
            and schedule["wire_input_layout"] == "canonical-stream4-K2560"
            and schedule["vector_alignment_bytes"] == 64, "vector layout/alignment contract mismatch")
    require(sha(source) == schedule["mlir_sha256"], "source/schedule hash mismatch")
    expected = schedule["transfers"]
    for path in (source, physical):
        actual = transfers(path.read_text(encoding="utf-8"))
        require(actual == expected if path == source else
                [canonical_transfer(v) for v in actual] == [canonical_transfer(v) for v in expected],
                "emitted transfer traversal differs from schedule: " + path.name)
        waits = re.findall(r"aiex\.npu\.dma_wait\s*\{symbol = @([\w]+)\}", path.read_text(encoding="utf-8"))
        require(len(waits) == 24 and len(set(waits)) == 24, "all24 MM2S/S2MM completion tokens must drain")
    maps = allocations(addressed.read_text(encoding="utf-8"))
    lowered_text = lowered.read_text(encoding="utf-8")
    patches = re.findall(r"aiex\.npu\.address_patch\s*\{([^}]+)\}", lowered_text)
    require(len(patches) == 24, "lowered runtime must contain exactly24 live BO patches")
    patch_args = [int(re.search(r"arg_idx = (\d+)", v).group(1)) for v in patches]
    require(all(patch_args.count(i) == 8 for i in (0, 1, 2)), "lowered BO patches must be8 weights/8 input/8 output")
    syncs = re.findall(r"aiex\.npu\.sync\s*\{([^}]+)\}", lowered_text)
    require(len(syncs) == 24, "lowered completion sync count differs from24")
    map_inventory = []
    for column in range(8):
        for row in range(2, 6):
            stem = f"main_core_{column}_{row}"
            for suffix in (".elf", ".ld.script", ".opt.ll"):
                path = intermediate / (stem + suffix)
                require(path.is_file() and path.stat().st_size > 0, "missing compiler map/code evidence: " + path.name)
                map_inventory.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)})
            linker = (intermediate / (stem + ".ld.script")).read_text(encoding="utf-8")
            require("_sp_start_value_DM_stack" in linker and re.search(r"\. \+= 0x1000; /\* stack \*/", linker), "declared4096 stack missing in linker map")
    totals = {kind: sum(v["bytes"] for v in expected if v["kind"] == kind) for kind in ("weights", "input", "output")}
    require(totals == {"weights": 13107200, "input": 163840, "output": 20480}, "DDR byte totals mismatch")
    receipt = {"format": "halogen-native-hidden-vector-emission-v1", "status": "passed", "device_opened": False,
        "source_and_physical_dma_verified": True, "lowered_address_patch_and_sync_counts_verified": True,
        "allocated_buffers_and_declared_stack_verified": True, "linked_stack_usage_review_required": True,
        "worker_vector_alignment_verified": True, "vector_alignment_bytes": 64,
        "vector_input_weight_buffer_count": 96, "weight_layout": schedule["weight_layout"], "input_layout": schedule["input_layout"],
        "native_numeric_validation_required": True, "allocations": maps, "dma": expected,
        "ddr_bytes": totals, "ddr_total_bytes": sum(totals.values()), "maps": map_inventory,
        "evidence_hashes": {p.name: sha(p) for p in (source, addressed, physical, lowered)}}
    (base / "emission-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    artifacts = {"format": "halogen-native-hidden-vector-artifacts-v1", "emission_verified": "true",
        "weight_layout": schedule["weight_layout"], "input_layout": schedule["input_layout"], "vector_alignment_bytes": "64",
        "xclbin_sha256": sha(base / "design.xclbin"), "instructions_sha256": sha(base / "insts.bin"),
        "abi_sha256": sha(base / "design.abi"), "kernel_sha256": sha(base / "kernels.o"),
        "emission_receipt_sha256": sha(base / "emission-receipt.json"), "schedule_sha256": sha(base / "schedule.json")}
    (base / "artifacts.abi").write_text("".join(f"{k}={v}\n" for k, v in artifacts.items()), encoding="utf-8", newline="\n")
    print(json.dumps({"status": "offline-emission-verified", "artifacts_abi_sha256": sha(base / "artifacts.abi"), "ddr_bytes_per_call": sum(totals.values())}))


if __name__ == "__main__":
    main()
