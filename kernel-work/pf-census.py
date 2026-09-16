#!/usr/bin/env python3
"""Tensor census: exact active weight payload per decoded token, decomposed by matrix family.

Answers the review's question: is it 4.61 GB (my figure) or ~3.75 GB (theirs)?
Method: parse the real PROJFIX GGUF (which we have on disk), take every tensor's exact stored bytes
from its block format, and count:
  - dense matrices        : fully read every token
  - routed expert matrices: read at k/512 of rows (k = expert_used_count = 10)
  - embedding tables      : rows only (gather), not the whole table
  - the PLE n-gram table  : excluded (paged from disk, ~16 rows/token)
"""
import json
import sys
from collections import defaultdict

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
from gguf_inventory import parse_shard, GT, NAME2TYPE

SHARDS = [f'/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-0000{i}-of-00009.gguf'
          for i in range(1, 10)]
K = 10          # expert_used_count
N_EXP = 512

tensors = []
for p in SHARDS:
    tensors.extend(parse_shard(p)["tensors"])


def nbytes(t):
    bb, bl = GT[t["type"]]
    n = 1
    for d in t["ne"]:
        n *= d
    return (n + bl - 1) // bl * bb, n


fam = defaultdict(lambda: {"bytes": 0, "n": 0, "type_bytes": defaultdict(int)})
detail = []

for t in tensors:
    nm = t["name"]
    b, n = nbytes(t)
    ty = NAME2TYPE.get(t["type"], str(t["type"]))
    if "per_layer_token_embd" in nm:
        # paged PLE table: count only the rows a token touches, not the table
        rows = 16                     # ngram_size(3) is the match; heads_per_ngram 8 -> ~16 rows/token
        # row length = ne[0] elements of the type
        t_bb, t_bl = GT[t["type"]]
        row_b = (t["ne"][0] + t_bl - 1) // t_bl * t_bb
        eff = row_b * rows
        fam["PLE n-gram table (rows read)"]["bytes"] += eff
        fam["PLE n-gram table (rows read)"]["n"] += 1
        detail.append((nm, ty, t["ne"], b, eff, "rows"))
        continue
    if "token_embd.weight" == nm or nm == "output.weight" and False:
        # input embedding: gather, 1 row per token
        t_bb, t_bl = GT[t["type"]]
        row_b = (t["ne"][0] + t_bl - 1) // t_bl * t_bb
        fam["input embedding (1 row)"]["bytes"] += row_b
        fam["input embedding (1 row)"]["n"] += 1
        detail.append((nm, ty, t["ne"], b, row_b, "rows"))
        continue
    # routed experts: 10 of 512 chosen -> K/N_EXP of their payload
    if nm.endswith("_exps.weight"):
        w = b * K / N_EXP
        fam["routed experts (k=10)"]["bytes"] += w
        fam["routed experts (k=10)"]["n"] += 1
        fam["routed experts (k=10)"]["type_bytes"][ty] += w
        detail.append((nm, ty, t["ne"], b, w, f"{K}/{N_EXP}"))
        continue
    # everything else: fully resident and fully read
    if nm == "per_layer_token_embd.weight":
        pass
    fam["dense / other (full read)"]["bytes"] += b
    fam["dense / other (full read)"]["n"] += 1
    fam["dense / other (full read)"]["type_bytes"][ty] += b
    detail.append((nm, ty, t["ne"], b, b, "full"))

print(f"{'family':34s} {'GiB':>9} {'GB':>9}  tensors")
total = 0
for k, v in sorted(fam.items(), key=lambda x: -x[1]["bytes"]):
    total += v["bytes"]
    types = ", ".join(f"{t}:{bb/2**20:.0f}M" for t, bb in sorted(v["type_bytes"].items(), key=lambda x: -x[1])[:3])
    print(f"{k:34s} {v['bytes']/2**30:9.3f} {v['bytes']/1e9:9.3f}  {v['n']:4d}   {types}")
print(f"{'TOTAL ACTIVE / TOKEN':34s} {total/2**30:9.3f} {total/1e9:9.3f}")

print()
for bw in (200, 220, 240, 256):
    print(f"  serial ceiling at {bw} GB/s: {bw/total*1e9:.1f} t/s")
print()
print("=== the biggest contributors ===")
for nm, ty, ne, raw, eff, how in sorted(detail, key=lambda x: -x[4])[:12]:
    print(f"  {nm:34s} {ty:6s} {str(ne):22s} eff {eff/2**20:8.2f} MiB  ({how})")

json.dump({k: {"bytes": v["bytes"], "n": v["n"]} for k, v in fam.items()},
          open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/pf-census.json', 'w'), indent=1)
print("\nwrote pf-census.json")
