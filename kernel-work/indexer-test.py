#!/usr/bin/env python3
"""Test the Halogen 0.9.1 insight on our Bug B: does the MTP acceptance cliff move with
qwen4exp.attention.indexer.top_k?  Hypothesis: acceptance dies at n_kv > top_k + ratio - 1.
Run against a server started with a given --override-kv value; print acceptance per depth."""
import json, sys, urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8200
LABEL = sys.argv[2] if len(sys.argv) > 2 else "?"
DEPTHS = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else [1024, 2048, 4096, 8192]
BASE = r"C:\Projects\REV-N-ornith-eval-20260911\kernel-work"
POOL = json.load(open(BASE + r"\bench-tokens.json"))

def post(payload):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/completion",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode()).get("timings", {})

print(f"=== {LABEL}")
for n in DEPTHS:
    t = post({"prompt": POOL[:n], "n_predict": 96, "cache_prompt": False,
              "temperature": 0.0, "top_k": 1, "seed": 42, "stream": False})
    dn, da = t.get("draft_n"), t.get("draft_n_accepted")
    acc = round(da / dn * 100, 1) if dn else None
    pf, dc = t.get("prompt_per_second"), t.get("predicted_per_second")
    print(f"  n={n:<6} prefill={pf and round(pf,1):>7} decode={dc and round(dc,2):>6} "
          f"draft={da}/{dn} acc={acc}%")
