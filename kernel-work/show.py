#!/usr/bin/env python3
"""Show results from a results JSON compactly."""
import json, sys
for path in sys.argv[1:]:
    d = json.load(open(path))
    print(f"=== {d.get('label', path)} (gen={d.get('gen')}) ===")
    for r in d["rows"]:
        pf, dc = r.get("prefill_tps"), r.get("decode_tps")
        acc = r.get("draft_n_accepted"); dn = r.get("draft_n")
        print("  n=%-6s rep=%s prompt_n=%-6s prefill=%-7s decode=%-6s%s" % (
            r.get("target_n"), r.get("rep"), r.get("prompt_n"),
            round(pf, 1) if pf else pf, round(dc, 2) if dc else dc,
            f" acc={acc}/{dn}" if dn else ""))
