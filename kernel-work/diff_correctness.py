#!/usr/bin/env python3
"""Compare correctness A/B outputs."""
import json
import sys

a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
ta = a["choices"][0]["message"]["content"]
tb = b["choices"][0]["message"]["content"]
print("=== graphs-ON output ===")
print(ta)
print("=== graphs-OFF output ===")
print(tb)
print("=== identical:", ta == tb, "===")
if ta != tb:
    # token-level diff summary
    wa, wb = ta.split(), tb.split()
    n = max(len(wa), len(wb))
    first_diff = next((i for i in range(n) if i >= len(wa) or i >= len(wb) or wa[i] != wb[i]), None)
    print(f"lens: {len(wa)} vs {len(wb)}; first differing word index: {first_diff}")
    if first_diff is not None:
        print("ON :", " ".join(wa[max(0, first_diff - 5):first_diff + 8]))
        print("OFF:", " ".join(wb[max(0, first_diff - 5):first_diff + 8]))
