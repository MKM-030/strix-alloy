"""Make an inert native HC6<3> candidate ELF by a guarded, fixed byte remap.

CPU byte transformation only. Does not compile, execute, load, or access HIP.
The pinned source object/engine remain unchanged. Output stays in this artifact
directory; an existing output is accepted only when its content is identical.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_hc6_remap import audit, require, sha


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
    parser.add_argument("--output", type=Path, default=here / "candidate.hsaco")
    parser.add_argument("--receipt", type=Path, default=here / "patch-receipt.json")
    args = parser.parse_args()
    output = args.output.resolve()
    receipt_path = args.receipt.resolve()
    require(output.parent == here and receipt_path.parent == here,
            "output and receipt must stay in this artifact directory")
    require(output not in (args.device.resolve(), args.engine.resolve()), "refusing to overwrite input")
    require(receipt_path not in (output, args.device.resolve(), args.engine.resolve()),
            "receipt cannot overwrite candidate or input")
    device = args.device.read_bytes()
    report = audit(device, args.disassembly.read_text(), args.engine.read_bytes())
    candidate = bytearray(device)
    for patch in report["patches"]:
        pos = patch["file_offset"]
        old, new = bytes.fromhex(patch["old_hex"]), bytes.fromhex(patch["new_hex"])
        require(candidate[pos:pos + len(old)] == old, "patch guard mismatch")
        candidate[pos:pos + len(old)] = new
    require(sha(candidate) == report["in_memory_candidate_sha256"], "candidate hash mismatch")
    if output.exists():
        require(output.read_bytes() == candidate, "existing output differs; refusing to overwrite")
    else:
        output.write_bytes(candidate)
    require(sha(output.read_bytes()) == report["in_memory_candidate_sha256"], "saved candidate mismatch")
    report["operation"] = "cpu_byte_transform_no_build_or_HIP"
    report["candidate_path"] = str(output)
    report["candidate_sha256"] = report.pop("in_memory_candidate_sha256")
    report["candidate_bytes"] = len(candidate)
    report["source_sha256"] = {name: sha((here / name).read_bytes())
                                for name in ("audit_hc6_remap.py", "transform.py")}
    receipt_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "candidate": str(output), "sha256": report["candidate_sha256"],
                      "bytes": len(candidate), "changed_bytes": report["changed_bytes"],
                      "receipt": str(receipt_path)}))


if __name__ == "__main__":
    main()
