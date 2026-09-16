#!/usr/bin/env python3
"""Locate where MTP draft acceptance breaks: sweep depth with the SAME prefix (so content is held
constant as depth grows), and separately test a natural chat prompt at depth."""
import json
import sys
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8190
BASE = r"C:\Projects\REV-N-ornith-eval-20260911\kernel-work"
POOL = json.load(open(BASE + r"\bench-tokens.json"))

def post(url, payload, timeout=1800):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def row(label, t):
    dn, da = t.get("draft_n"), t.get("draft_n_accepted")
    acc = round(da / dn * 100, 1) if dn else None
    pf = t.get("prompt_per_second"); dc = t.get("predicted_per_second")
    print(f"{label:34s} prompt_n={str(t.get('prompt_n')):>6} prefill={pf and round(pf,1):>7} "
          f"decode={dc and round(dc,2):>6} draft={da}/{dn} acc={acc}%")

print("=== same-prefix depth sweep (content held constant, only length grows) ===")
for n in (512, 1024, 2048, 4096, 8192):
    t = post(f"http://127.0.0.1:{PORT}/completion",
             {"prompt": POOL[:n], "n_predict": 96, "cache_prompt": False,
              "temperature": 0.0, "top_k": 1, "seed": 42, "stream": False}).get("timings", {})
    row(f"corpus prefix n={n}", t)

print()
print("=== natural chat prompt at depth (long system doc + a question) ===")
# use real text from the corpus file, not token ids
with open(BASE + r"\bench-corpus.txt", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()
doc = text[:24000]  # ~6k tokens of natural text
system = "You are a precise engineer. Answer using only the document."
user = "Summarize the document's main themes in three sentences."
msgs = [{"role": "system", "content": system},
        {"role": "user", "content": doc + "\n\n" + user}]
r = post(f"http://127.0.0.1:{PORT}/v1/chat/completions",
         {"messages": msgs, "n_predict": 128, "cache_prompt": False,
          "temperature": 0.0, "top_k": 1, "seed": 42, "stream": False})
row("chat w/ ~6k text doc", r.get("timings", {}))
