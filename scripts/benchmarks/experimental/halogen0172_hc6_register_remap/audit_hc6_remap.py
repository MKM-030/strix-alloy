"""CPU-only audit and guarded plan for the pinned native HC6<3> VGPR remap.

Default operation writes only a JSON patch plan, never an executable object.
It reads inert retained ELF data and retained llvm-objdump text. No HIP/runtime
imports, loading, compilation, subprocess execution, or device access occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

DEVICE_SHA = "18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039"
ENGINE_SHA = "ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913"
SYMBOL = "_ZN7halogen12_GLOBAL__N_112k_hc6_fused3ILi3EEEvPtPKtPKfS4_iNS0_5LqGrpES2_liPKhS4_S2_PfPyySB_y"
ENTRY, END, KD = 0x3B3C00, 0x3B8FDC, 0x1FEFC0
LOOP_START, LOOP_END = 0x3B764C, 0x3B8068
DEVICE_ENGINE_OFFSET = 335872
# old VGPR, replacement, full definition RVA, sole use RVA
INTERVALS = [
    (121, 109, 0x3B793C, 0x3B7958),
    (120, 119, 0x3B7BC0, 0x3B7C18),
    (122, 109, 0x3B7BD8, 0x3B7C20),
    (121, 119, 0x3B7C8C, 0x3B7CEC),
    (123, 119, 0x3B7D0C, 0x3B7D40),
    (124, 109, 0x3B7D20, 0x3B7D48),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def vgprs(text):
    result = set()
    for match in re.finditer(r"\bv(?:\[(\d+):(\d+)\]|(\d+)\b)", text):
        if match[3] is not None:
            result.add(int(match[3]))
        else:
            result.update(range(int(match[1]), int(match[2]) + 1))
    return result


def instructions(text):
    result = []
    for line in text.splitlines():
        match = re.search(r"// ([0-9A-Fa-f]+): ([0-9A-Fa-f ]+)", line)
        if not match:
            continue
        words = [int(w, 16) for w in match[2].split()]
        result.append({"rva": int(match[1], 16),
                       "text": line.split("//", 1)[0].strip(),
                       "words": words})
    require(result[0]["rva"] == ENTRY, "wrong kernel entry")
    require(result[-1]["rva"] + 4 * len(result[-1]["words"]) == END,
            "wrong kernel extent")
    for left, right in zip(result, result[1:]):
        require(left["rva"] + 4 * len(left["words"]) == right["rva"],
                "noncontiguous retained disassembly")
    return result


def sections(data):
    require(data[:6] == b"\x7fELF\x02\x01", "expected ELF64 little endian")
    require(struct.unpack_from("<H", data, 18)[0] == 224, "expected AMDGPU ELF")
    offset = struct.unpack_from("<Q", data, 40)[0]
    stride, count, names_index = struct.unpack_from("<HHH", data, 58)
    result = [struct.unpack_from("<IIQQQQIIQQ", data, offset + i * stride)
              for i in range(count)]
    names = data[result[names_index][4]:result[names_index][4] + result[names_index][5]]
    return [{"name": names[s[0]:names.index(b"\0", s[0])].decode(),
             "type": s[1], "rva": s[3], "offset": s[4], "size": s[5]}
            for s in result]


def file_offset(section_list, rva, size):
    matches = [s for s in section_list if s["type"] != 8 and
               s["rva"] <= rva and rva + size <= s["rva"] + s["size"]]
    require(len(matches) == 1, f"ambiguous/unmapped RVA {rva:#x}")
    return matches[0]["offset"] + rva - matches[0]["rva"]


def msgpack_with_locations(data):
    """Decode metadata and retain exact byte spans; no external dependency."""
    locations = {}
    def take(offset, count):
        require(offset + count <= len(data), "truncated metadata")
        return data[offset:offset + count], offset + count
    def integer(offset, count, signed=False):
        raw, end = take(offset, count)
        return int.from_bytes(raw, "big", signed=signed), end
    def decode(offset, path):
        start = offset
        tag, offset = integer(offset, 1)
        if tag < 128:
            value = tag
        elif tag >= 224:
            value = tag - 256
        elif tag in (0xC0, 0xC2, 0xC3):
            value = {0xC0: None, 0xC2: False, 0xC3: True}[tag]
        elif tag in (0xCC, 0xCD, 0xCE, 0xCF, 0xD0, 0xD1, 0xD2, 0xD3):
            count = {0xCC: 1, 0xCD: 2, 0xCE: 4, 0xCF: 8,
                     0xD0: 1, 0xD1: 2, 0xD2: 4, 0xD3: 8}[tag]
            value, offset = integer(offset, count, tag >= 0xD0)
        elif tag in (0xCA, 0xCB):
            raw, offset = take(offset, 4 if tag == 0xCA else 8)
            value = struct.unpack(">f" if tag == 0xCA else ">d", raw)[0]
        elif 0xA0 <= tag <= 0xBF or tag in (0xD9, 0xDA, 0xDB, 0xC4, 0xC5, 0xC6):
            if 0xA0 <= tag <= 0xBF:
                count = tag & 31
            else:
                count, offset = integer(offset, {0xD9: 1, 0xDA: 2, 0xDB: 4,
                                                 0xC4: 1, 0xC5: 2, 0xC6: 4}[tag])
            raw, offset = take(offset, count)
            value = raw if tag in (0xC4, 0xC5, 0xC6) else raw.decode()
        elif 0x90 <= tag <= 0x9F or tag in (0xDC, 0xDD):
            count = tag & 15
            if tag in (0xDC, 0xDD):
                count, offset = integer(offset, 2 if tag == 0xDC else 4)
            value = []
            for index in range(count):
                item, offset = decode(offset, path + (index,))
                value.append(item)
        elif 0x80 <= tag <= 0x8F or tag in (0xDE, 0xDF):
            count = tag & 15
            if tag in (0xDE, 0xDF):
                count, offset = integer(offset, 2 if tag == 0xDE else 4)
            value = {}
            for _ in range(count):
                key, offset = decode(offset, path + ("<key>",))
                item, offset = decode(offset, path + (key,))
                require(key not in value, "duplicate metadata key")
                value[key] = item
        else:
            raise ValueError(f"unsupported metadata tag {tag:#x}")
        locations[path] = (start, offset)
        return value, offset
    root, end = decode(0, ())
    require(end == len(data), "trailing metadata bytes")
    return root, locations


def metadata(data, section_list, expected_vgprs=125):
    candidates = []
    for section in section_list:
        if section["type"] != 7:
            continue
        pos, limit = section["offset"], section["offset"] + section["size"]
        while pos < limit:
            namesize, descsize, kind = struct.unpack_from("<III", data, pos)
            pos += 12
            name = data[pos:pos + namesize].rstrip(b"\0")
            pos = (pos + namesize + 3) & ~3
            descriptor_offset = pos
            descriptor = data[pos:pos + descsize]
            pos = (pos + descsize + 3) & ~3
            if name == b"AMDGPU" and kind == 32:
                candidates.append((descriptor_offset, descriptor))
        require(pos == limit, "note section alignment mismatch")
    require(len(candidates) == 1, "expected one AMDGPU metadata note")
    base, raw = candidates[0]
    root, locations = msgpack_with_locations(raw)
    kernels = root["amdhsa.kernels"]
    indexes = [i for i, kernel in enumerate(kernels) if kernel[".name"] == SYMBOL]
    require(len(indexes) == 1, "expected one selected kernel metadata record")
    index = indexes[0]
    selected = kernels[index]
    require(selected[".vgpr_count"] == expected_vgprs, "wrong metadata VGPR count")
    start, end = locations[("amdhsa.kernels", index, ".vgpr_count")]
    require(raw[start:end] == bytes([expected_vgprs]), "VGPR count not encoded as positive fixint")
    return selected, base + start


def audit(device, retained_disassembly, engine=None):
    require(sha(device) == DEVICE_SHA, "device SHA256 mismatch")
    insns = instructions(retained_disassembly)
    by_address = {i["rva"]: i for i in insns}
    section_list = sections(device)
    for insn in insns:
        raw = struct.pack("<" + "I" * len(insn["words"]), *insn["words"])
        offset = file_offset(section_list, insn["rva"], len(raw))
        require(device[offset:offset + len(raw)] == raw, "disassembly/ELF mismatch")
    native_regs = {v for i in insns for v in vgprs(i["text"])}
    require(max(native_regs) == 124, "unexpected whole-kernel VGPR maximum")
    branch_targets = []
    for insn in insns:
        op = insn["text"].split()[0]
        if op.startswith("s_cbranch") or op == "s_branch":
            operand = int(insn["text"].split()[1])
            signed = operand - 65536 if operand > 32767 else operand
            branch_targets.append(insn["rva"] + 4 + signed * 4)
    require(not any(INTERVALS[0][2] <= t <= INTERVALS[-1][3]
                    for t in branch_targets), "control edge enters remap interval")
    loop = [i for i in insns if LOOP_START < i["rva"] < LOOP_END]
    require(not any("branch" in i["text"] for i in loop), "unexpected branch in core")
    require(not any(i["text"].startswith("v_cmpx") or
                    i["text"].split()[1].rstrip(",") in ("exec", "exec_lo", "exec_hi")
                    for i in loop if len(i["text"].split()) > 1),
            "unexpected EXEC modification in core")
    # The reused native lower-register values have one full definition and use
    # in the loop. Neither is loop-carried or used by either exit/other path.
    require([(i["rva"], i["text"]) for i in insns
             if i["rva"] >= 0x3B7234 and 109 in vgprs(i["text"])] == [
                 (0x3B7A94, "v_lshrrev_b32_e32 v109, 20, v3"),
                 (0x3B7B6C, "v_and_or_b32 v100, v109, 15, v106")],
            "v109 has unexpected consumer/tail references")
    require([(i["rva"], i["text"]) for i in insns
             if i["rva"] >= 0x3B7234 and 119 in vgprs(i["text"])] == [
                 (0x3B7A44, "v_lshrrev_b32_e32 v119, 4, v2"),
                 (0x3B7AEC, "v_and_or_b32 v94, v119, 15, v96")],
            "v119 has unexpected consumer/tail references")
    planned, patches = {}, []
    for old, new, first, last in INTERVALS:
        touches = [i for i in insns if first <= i["rva"] <= last and old in vgprs(i["text"])]
        require([i["rva"] for i in touches] == [first, last], "temporary has extra reference")
        require(by_address[first]["text"].split()[1].rstrip(",") == f"v{old}",
                "temporary does not begin with a full definition")
        require(not any(new in vgprs(i["text"]) for i in insns
                        if first <= i["rva"] <= last), "replacement aliases a live operand")
        for other_old, other_new, other_first, other_last in INTERVALS:
            if first != other_first and new == other_new:
                require(last < other_first or other_last < first, "replacement intervals overlap")
        for insn in touches:
            changed = list(insn["words"])
            if insn["rva"] == first:
                require(len(changed) == 1 and insn["text"].split()[0]
                        in ("v_and_b32_e32", "v_lshrrev_b32_e32"), "unexpected E32 definition")
                require((changed[0] >> 17) & 255 == old, "wrong E32 VGPR destination encoding")
                changed[0] = (changed[0] & ~(255 << 17)) | (new << 17)
            else:
                require(len(changed) == 2 and insn["text"].startswith("v_and_or_b32 "),
                        "unexpected VOP3 use")
                fields = [shift for shift in (0, 9, 18)
                          if (changed[1] >> shift) & 511 == 256 + old]
                require(len(fields) == 1, "ambiguous VOP3 VGPR source encoding")
                shift = fields[0]
                changed[1] = (changed[1] & ~(511 << shift)) | ((256 + new) << shift)
            old_bytes = struct.pack("<" + "I" * len(changed), *insn["words"])
            new_bytes = struct.pack("<" + "I" * len(changed), *changed)
            new_text = re.sub(rf"\bv{old}\b", f"v{new}", insn["text"])
            planned[insn["rva"]] = new_text
            patches.append({"kind": "instruction_operand", "rva": insn["rva"],
                            "file_offset": file_offset(section_list, insn["rva"], len(old_bytes)),
                            "old_hex": old_bytes.hex(), "new_hex": new_bytes.hex(),
                            "old_asm": insn["text"], "new_asm": new_text})
    expected_high_refs = {rva for _, _, first, last in INTERVALS for rva in (first, last)}
    actual_high_refs = {i["rva"] for i in insns if any(r >= 120 for r in vgprs(i["text"]))}
    require(expected_high_refs == actual_high_refs, "uncovered high-VGPR references")
    candidate_regs = {r for i in insns for r in vgprs(planned.get(i["rva"], i["text"]))}
    require(max(candidate_regs) == 119, "candidate does not lower whole-kernel max to119")
    kd_offset = file_offset(section_list, KD, 64)
    descriptor = device[kd_offset:kd_offset + 64]
    require(KD + struct.unpack_from("<q", descriptor, 16)[0] == ENTRY,
            "kernel descriptor entry mismatch")
    require(struct.unpack_from("<I", descriptor, 48)[0] == 0xE0AF000F,
            "unexpected COMPUTE_PGM_RSRC1")
    require(struct.unpack_from("<H", descriptor, 56)[0] & 0x400, "kernel is not wave32")
    patches.append({"kind": "kernel_descriptor_rsrc1", "rva": KD + 48,
                    "file_offset": kd_offset + 48, "old_hex": "0f00afe0", "new_hex": "0e00afe0"})
    selected, vgpr_offset = metadata(device, section_list)
    patches.append({"kind": "metadata_vgpr_count", "file_offset": vgpr_offset,
                    "old_hex": "7d", "new_hex": "78"})
    patches.sort(key=lambda p: p["file_offset"])
    memory_candidate = bytearray(device)
    allowed_differences = set()
    for patch in patches:
        offset = patch["file_offset"]
        before, after = bytes.fromhex(patch["old_hex"]), bytes.fromhex(patch["new_hex"])
        require(len(before) == len(after), "patch changes object length")
        require(memory_candidate[offset:offset + len(before)] == before, "patch guard mismatch")
        memory_candidate[offset:offset + len(before)] = after
        allowed_differences.update(offset + i for i, (a, b) in enumerate(zip(before, after)) if a != b)
    differences = {i for i, (a, b) in enumerate(zip(device, memory_candidate)) if a != b}
    require(differences == allowed_differences, "unexpected candidate difference")
    # Parse updated metadata independently; only the selected count may differ.
    after_metadata, after_vgpr_offset = metadata(bytes(memory_candidate), section_list, 120)
    expected_after_metadata = dict(selected, **{".vgpr_count": 120})
    require(after_metadata == expected_after_metadata and after_vgpr_offset == vgpr_offset,
            "candidate metadata changed beyond VGPR count")
    boundaries = [(ENTRY, 0x3B7234), (0x3B7234, 0x3B8110), (0x3B8110, END)]
    region_maxima = [max(r for i in insns if first <= i["rva"] < last
                        for r in vgprs(i["text"])) for first, last in boundaries]
    require(region_maxima == [115, 124, 73], "unexpected native regional VGPR maxima")
    candidate_middle_max = max(r for i in insns if 0x3B7234 <= i["rva"] < 0x3B8110
                               for r in vgprs(planned.get(i["rva"], i["text"])))
    require(candidate_middle_max == 119, "unexpected candidate middle VGPR maximum")
    if engine is not None:
        require(sha(engine) == ENGINE_SHA, "engine SHA256 mismatch")
        require(engine[DEVICE_ENGINE_OFFSET:DEVICE_ENGINE_OFFSET + len(device)] == device,
                "selected embedded bundle mismatch")
    for patch in patches:
        patch["engine_file_offset"] = DEVICE_ENGINE_OFFSET + patch["file_offset"]
    return {"schema": "halogen0172.hc6-register-remap.plan.v1",
            "operation": "audit_only_no_executable_written", "symbol": SYMBOL,
            "device_sha256": DEVICE_SHA, "engine_sha256": ENGINE_SHA,
            "device_bytes": len(device), "device_engine_file_offset": DEVICE_ENGINE_OFFSET,
            "in_memory_candidate_sha256": sha(memory_candidate),
            "retained_disassembly_sha256": sha(retained_disassembly.encode()),
            "kernel_entry_rva": ENTRY, "kernel_end_rva": END, "kernel_descriptor_rva": KD,
            "instruction_count": len(insns), "instruction_operand_edits": 12,
            "changed_bytes": len(differences), "metadata_native": selected,
            "logical_vgprs": {"native": 125, "candidate": 120},
            "wave32_encoding_granule": 8, "gfx1151_physical_granule": 24,
            "encoded_vgprs": {"native": 128, "candidate": 120},
            "physical_vgprs_per_wave": {"native": 144, "candidate": 120},
            "vgpr_limit_waves_per_simd": {"native": 10, "candidate": 12},
            "actual_residency_or_speedup_measured": False,
            "regions_max_vgpr": {"hc6_consumer": 115, "middle_consumer_native": 124,
                                 "middle_consumer_candidate": 119, "producer_and_tail": 73},
            "intervals": [{"old": a, "new": b, "first_rva": c, "last_rva": d}
                          for a, b, c, d in INTERVALS],
            "static_checks": [f"all{len(insns)}_instruction_words_match_pinned_ELF",
                              "all_high_VGPR_references_covered", "no_branch_enters_remap_intervals",
                              "no_EXEC_change_or_branch_within_intervals",
                              "replacement_native_values_not_loop_carried_or_live_out",
                              "replacement_intervals_disjoint", "no_VOPD_instruction_modified",
                              "only12_integer_operand_edits_plus_descriptor_and_metadata",
                              "same_object_length_and_embedded_bundle_identity"],
            "patches": patches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    prep = here.parent
    parser.add_argument("--device", type=Path,
                        default=prep / "gpu-moe-compute-20261008/bundle0-gfx1151-code-object.data")
    parser.add_argument("--disassembly", type=Path,
                        default=prep / "gpu-event-attribution-20261009/hc6-native-disassembly.txt")
    parser.add_argument("--engine", type=Path,
                        default=prep / "runtime-inventory/static-audit-data/usr/local/bin/flash_serve.data")
    parser.add_argument("--plan", type=Path, default=here / "patch-plan.json")
    args = parser.parse_args()
    report = audit(args.device.read_bytes(), args.disassembly.read_text(), args.engine.read_bytes())
    args.plan.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "plan": str(args.plan), "changed_bytes": report["changed_bytes"],
                      "candidate_sha256_in_memory": report["in_memory_candidate_sha256"],
                      "logical_vgprs": report["logical_vgprs"]}))


if __name__ == "__main__":
    main()
