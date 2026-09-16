#!/usr/bin/env python3
"""Test the 0%-acceptance-at-depth hypothesis: is it a prompt-cache artifact?
Sends the same 8k prompt twice: once cold (cache_prompt=false) and once warm (cache_prompt=true)."""
import json
import sys
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8180
POOL = json.load(open(r"C:\Projects\REV-N-ornith-eval-20260911\kernel-work\bench-tokens.json"))
prompt = POOL[:8192]

def call(cache):
    payload = {"prompt": prompt, "n_predict": 128, "cache_prompt": cache,
               "temperature": 0.0, "top_k": 1, "seed": 42, "stream": False}
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/completion",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode())["timings"]

for label, cache in (("cold (cache_prompt=false)", False),
                     ("warm1 (cache_prompt=true)", True),
                     ("warm2 (cache_prompt=true)", True)):
    t = call(cache)
    dn, da = t.get("draft_n"), t.get("draft_n_accepted")
    acc = (da / dn * 100) if dn else None
    print(f"{label:28s} prompt_n={t.get('prompt_n')} prefill={t.get('prompt_per_second'):7.1f} "
          f"decode={t.get('predicted_per_second'):6.2f} draft={da}/{dn} acc={acc and round(acc,1)}%")
