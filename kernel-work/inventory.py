#!/usr/bin/env python3
"""Consolidated inventory of every measured prefill/decode number this session."""
import glob, json, os

D = os.path.dirname(os.path.abspath(__file__)) + "/results"
LABELS = {
    "ax-ax-projfix2.json":        "WSL  PROJFIX + AUTHOR gates, ub8192",
    "f2-pf-ub16k.json":           "WSL  PROJFIX + AUTHOR gates, ub16384",
    "f2-ud-author.json":          "WSL  UD + AUTHOR gates, ub8192",
    "win-ud3.json":               "WIN  UD serial, ub8192",
    "win-mtp-final.json":         "WIN  UD + MTP shared, ub2048 (default top_k)",
    "mi-ud-mtp-nogates.json":     "WSL  UD + plain MTP, no gates",
}
print(f"{'config':44s} {'@1k':>16s} {'@8k':>16s} {'@16k':>16s} {'@32k':>16s}   (prefill / decode)")
for fn, label in LABELS.items():
    p = os.path.join(D, fn)
    if not os.path.exists(p):
        print(f"{label:44s}  (missing {fn})")
        continue
    d = json.load(open(p))
    best = {}
    for r in d["rows"]:
        n = r.get("target_n")
        if not n or not r.get("prefill_tps"):
            continue
        pf, dc = r["prefill_tps"], r.get("decode_tps") or 0
        if n not in best or pf > best[n][0]:
            best[n] = (pf, dc)
    cells = []
    for n in (1024, 8192, 16384, 32768):
        if n in best:
            cells.append(f"{best[n][0]:.0f}/{best[n][1]:.1f}")
        else:
            cells.append("-")
    print(f"{label:44s} {cells[0]:>16s} {cells[1]:>16s} {cells[2]:>16s} {cells[3]:>16s}")
print()
print("format: prefill t/s / decode t/s ; '-' = not measured")
