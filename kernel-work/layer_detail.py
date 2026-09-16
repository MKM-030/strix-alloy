#!/usr/bin/env python3
"""Per-layer tensor detail + active-bytes/token bandwidth model for Flash-Next UD-IQ4_XS."""
import json, re, sys
from collections import defaultdict

sys.path.insert(0, '.')
from gguf_inventory import parse_shard, GT, NAME2TYPE

K = 10  # expert_used_count

shards = [
    "/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf",
    "/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf",
    "/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf",
]
tensors = []
for p in shards:
    tensors.extend(parse_shard(p)["tensors"])

layers = defaultdict(list)
core = []
for t in tensors:
    m = re.match(r"blk\.(\d+)\.(.+)", t["name"])
    if m:
        layers[int(m.group(1))].append(t)
    else:
        core.append(t)

def tsize(t):
    bb, bl = GT[t["type"]]
    n = 1
    for d in t["ne"]:
        n *= d
    return (n + bl - 1) // bl * bb, n

# full-attn layers: every 4th (blk 3,7,11,...) per compress_ratios[3]=4
full_attn_layers = set(range(3, 48, 4))

per_layer = {}
for il in sorted(layers):
    expert_b = 0; expert_n = 0; attn_b = 0; shared_b = 0; router_b = 0; other_b = 0
    detail = []
    for t in layers[il]:
        b, n = tsize(t)
        nm = t["name"].split(".", 2)[2]
        ty = NAME2TYPE.get(t["type"], str(t["type"]))
        detail.append((nm, ty, t["ne"], b))
        if re.search(r"ffn_(gate|up|down)_exps", nm):
            expert_b += b; expert_n += n
        elif re.search(r"ffn_(gate|up|down)_shexp", nm):
            shared_b += b
        elif re.search(r"ffn_gate_inp|exp_probs_b", nm):
            router_b += b
        elif "per_layer_embd" in nm or "per_layer_token_embd" in nm:
            other_b += b  # PLE-related per-layer embedding row (lazy)
        else:
            attn_b += b
    per_layer[il] = dict(expert_bytes_per_layer=expert_b, expert_params=expert_n,
                         experts=512, per_expert_bytes=expert_b / 512,
                         attention_gdn_bytes=attn_b, shared_bytes=shared_b,
                         router_bytes=router_b, other_bytes=other_b,
                         is_full_attn=il in full_attn_layers, detail=detail)

# bandwidth model: active bytes per decoded token
act = dict(experts=0, attention_gdn=0, shared=0, router=0, other=0, core=0)
for il, d in per_layer.items():
    act["experts"] += K * d["per_expert_bytes"]
    act["attention_gdn"] += d["attention_gdn_bytes"]
    act["shared"] += d["shared_bytes"]
    act["router"] += d["router_bytes"]
    act["other"] += d["other_bytes"]
for t in core:
    b, n = tsize(t)
    if "per_layer_token_embd" in t["name"]:
        act["other"] += 0  # PLE table: lazy/paged, excluded from resident traffic
    else:
        act["core"] += b

total_active = sum(act.values())
print("=== active resident weight bytes per token (k=%d experts) ===" % K)
for k, v in act.items():
    print("%-14s %8.1f MiB" % (k, v / 2**20))
print("%-14s %8.1f MiB  -> %.2f GiB" % ("TOTAL", total_active / 2**20, total_active / 2**30))
for bw in (200e9, 220e9, 240e9):
    print("  at %d GB/s: %.1f ms/token -> %.1f t/s" % (bw/1e9, total_active/bw*1e3, bw/total_active))

# KV + GDN state per token
kv_bytes_per_tok = 0
n_fa = len(full_attn_layers)
heads_kv, head_dim = 2, 256
kv_bytes_per_tok = n_fa * 2 * heads_kv * head_dim * 2  # f16 k+v
print("full-attn layers: %d, KV f16 bytes/token: %d (%.1f KiB); at 36k ctx: %.2f GiB total KV"
      % (n_fa, kv_bytes_per_tok, kv_bytes_per_tok/1024, kv_bytes_per_tok*36864/2**30))
gdn_state = 36 * (6144 * 128 * 4)  # f32 state read+write per token per GDN layer (approx)
print("GDN state (f32, 36 layers, approx read+write per token): %.1f MiB" % (gdn_state / 2**20))

# per-expert composition for a typical layer
il = 10
print("\n=== detail blk.%d (GDN layer) ===" % il)
for nm, ty, ne, b in per_layer[il]["detail"]:
    print("  %-28s %-7s %-22s %8.2f MiB" % (nm, ty, str(ne), b / 2**20))
il = 4
print("=== detail blk.%d (full-attn layer) ===" % il)
for nm, ty, ne, b in per_layer[il]["detail"]:
    print("  %-28s %-7s %-22s %8.2f MiB" % (nm, ty, str(ne), b / 2**20))

json.dump({"per_layer": {str(k): v for k, v in per_layer.items()},
           "active_bytes_per_token": act, "total_active": total_active},
          open("layer-detail.json", "w"), indent=1, default=str)
print("\nsaved layer-detail.json")
