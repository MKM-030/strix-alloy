#!/usr/bin/env python3
"""Compare unsloth UD-IQ4_XS vs ilintar IQ4_NL PROJFIX: active bytes per decoded token.
Exact formula: active = total_bytes - PLE_table - experts*(1 - K/512) - (token_embd - 1 row).
Everything else (attention, GDN, hc, shared expert, router, output head, norms) is read fully per token."""
import json

K = 10
E = 512

def load(p):
    d = json.load(open(p))
    tot = d["total_bytes"]
    ple = 0.0
    embd = 0.0
    out = 0.0
    experts = d["by_class"]["moe_routed"]["bytes"]
    for t in d["big_tensors_gt_500MB"]:
        if "per_layer_token_embd" in t["name"]:
            ple = t["bytes"]
        elif t["name"] == "output.weight":
            out = t["bytes"]
        elif t["name"] == "token_embd.weight":
            embd = t["bytes"]
    active = tot - ple - experts * (E - K) / E - (embd - 2560 * 34)
    return dict(total=tot, ple=ple, embd=embd, out=out, experts=experts,
                experts_active=experts * K / E, active=active)

a = load("gguf-inventory-udiq4xs.json")
b = load("gguf-inventory-iq4nl.json")

for name, d in (("unsloth UD-IQ4_XS", a), ("ilintar IQ4_NL PROJFIX", b)):
    print("%-22s total %6.2f GiB | PLE %5.2f | embd %5.2f | experts %5.2f (active %5.2f) | output %4.2f"
          % (name, d["total"] / 2**30, d["ple"] / 2**30, d["embd"] / 2**30,
             d["experts"] / 2**30, d["experts_active"] / 2**30, d["out"] / 2**30))
    print("  => ACTIVE per decoded token: %.2f GiB = %.2f GB  (%.1f%% of unsloth's)"
          % (d["active"] / 2**30, d["active"] / 1e9, 100.0 * d["active"] / a["active"]))
    for bw in (119e9, 140e9, 170e9, 230e9):
        print("     at %3.0f GB/s effective: %5.1f ms/token -> %5.1f t/s"
              % (bw / 1e9, d["active"] / bw * 1e3, bw / d["active"]))
    print()

ratio = a["active"] / b["active"]
print("PROJFIX active traffic is %.2fx lower than unsloth." % ratio)
print("With MTP depth 3 at acceptance a: speedup ~ 1/((1-a)+a/3):")
for acc in (0.45, 0.60, 0.75):
    print("  a=%.2f -> x%.2f weight-traffic" % (acc, 1.0 / ((1 - acc) + acc / 3.0)))
