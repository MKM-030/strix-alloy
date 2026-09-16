#!/usr/bin/env python3
"""Minimal GGUF header parser: metadata + tensor inventory with exact byte counts.
No external deps. Usage: python3 gguf_inventory.py <shard1.gguf> [shard2 ...] [--out out.json]
"""
import json
import re
import struct
import sys
from collections import defaultdict

TYPE_SIZES = {  # (bytes_per_block, elems_per_block) from ggml-common.h
    0: (4, 1), 1: (1, 1), 2: (2, 1), 3: (2, 1),      # F32 I8 U8? -> 0:F32 1:F16 actually
    4: (2, 1), 5: (2, 1),                              # Q4_0 handled below
}
# authoritative table: ggml type enum -> (block_bytes, block_len), per ggml.h + ggml-common.h
GT = {
    0: (4, 1),      # F32
    1: (2, 1),      # F16
    2: (18, 32),    # Q4_0
    3: (20, 32),    # Q4_1
    6: (22, 32),    # Q5_0
    7: (24, 32),    # Q5_1
    8: (34, 32),    # Q8_0
    9: (36, 32),    # Q8_1
    10: (84, 256),  # Q2_K
    11: (110, 256), # Q3_K
    12: (144, 256), # Q4_K
    13: (176, 256), # Q5_K
    14: (210, 256), # Q6_K
    15: (292, 256), # Q8_K
    16: (66, 256),  # IQ2_XXS
    17: (100, 256), # IQ2_XS
    18: (66, 256),  # IQ3_XXS
    19: (50, 256),  # IQ1_S
    20: (18, 32),   # IQ4_NL
    21: (110, 256), # IQ3_S
    22: (110, 256), # IQ2_S
    23: (136, 256), # IQ4_XS
    24: (1, 1),     # I8
    25: (2, 1),     # I16
    26: (4, 1),     # I32
    27: (8, 1),     # I64
    28: (8, 1),     # F64
    29: (56, 256),  # IQ1_M
    30: (2, 1),     # BF16
    34: (17, 256),  # TQ1_0? not used here
    35: (33, 256),  # TQ2_0? not used here
    39: (17, 32),   # MXFP4 (2+16? actually 1+32=33?) unused here
}
GT[31] = (2, 1)   # BF16

VTYPE_NAMES = {0: "u8", 1: "i8", 2: "u16", 3: "i16", 4: "u32", 5: "i32", 6: "f32",
               7: "bool", 8: "str", 9: "arr", 10: "u64", 11: "i64", 12: "f64"}

class R:
    def __init__(self, f):
        self.f = f
    def u32(self):
        return struct.unpack("<I", self.f.read(4))[0]
    def u64(self):
        return struct.unpack("<Q", self.f.read(8))[0]
    def i64(self):
        return struct.unpack("<q", self.f.read(8))[0]
    def f32(self):
        return struct.unpack("<f", self.f.read(4))[0]
    def f64(self):
        return struct.unpack("<d", self.f.read(8))[0]
    def b(self):
        return self.f.read(1)[0] != 0
    def raw(self, n):
        return self.f.read(n)
    def s(self):
        n = self.u64()
        return self.f.read(n).decode("utf-8", "replace")

def read_val(r, t):
    if t == 0: return r.u32() if False else r.f.read(1)[0]
    if t == 1: return struct.unpack("<b", r.f.read(1))[0]
    if t == 2: return struct.unpack("<H", r.f.read(2))[0]
    if t == 3: return struct.unpack("<h", r.f.read(2))[0]
    if t == 4: return r.u32()
    if t == 5: return struct.unpack("<i", r.f.read(4))[0]
    if t == 6: return r.f32()
    if t == 7: return r.b()
    if t == 8: return r.s()
    if t == 9:
        et = r.u32(); n = r.u64()
        return [read_val(r, et) for _ in range(n)]
    if t == 10: return r.u64()
    if t == 11: return r.i64()
    if t == 12: return r.f64()
    raise ValueError(f"unknown vtype {t}")

def parse_shard(path):
    out = {"path": path.split("/")[-1]}
    with open(path, "rb") as f:
        r = R(f)
        magic = f.read(4)
        assert magic == b"GGUF", f"bad magic {magic!r}"
        out["version"] = r.u32()
        n_tensors = r.u64()
        n_kv = r.u64()
        meta = {}
        for _ in range(n_kv):
            k = r.s()
            t = r.u32()
            v = read_val(r, t)
            meta[k] = v
        out["meta"] = meta
        tensors = []
        for _ in range(n_tensors):
            name = r.s()
            nd = r.u32()
            ne = [r.u64() for _ in range(nd)]
            ty = r.u32()
            off = r.u64()
            tensors.append({"name": name, "ne": ne, "type": ty, "off": off})
        out["tensors"] = tensors
    return out

NAME2TYPE = {0:"F32",1:"F16",2:"Q4_0",3:"Q4_1",6:"Q5_0",7:"Q5_1",8:"Q8_0",9:"Q8_1",
    10:"Q2_K",11:"Q3_K",12:"Q4_K",13:"Q5_K",14:"Q6_K",15:"Q8_K",16:"IQ2_XXS",17:"IQ2_XS",
    18:"IQ3_XXS",19:"IQ1_S",20:"IQ4_NL",21:"IQ3_S",22:"IQ2_S",23:"IQ4_XS",24:"I8",
    25:"I16",26:"I32",27:"I64",28:"F64",29:"IQ1_M",30:"BF16"}

def classify(name):
    if re.search(r"ffn_(gate|up|down)_exps", name): return "moe_routed"
    if re.search(r"ffn_(gate|up|down)_shexp", name): return "moe_shared"
    if re.search(r"ffn_gate_inp|exp_probs_b", name): return "moe_router"
    if re.search(r"attn_", name): return "attention"
    if re.search(r"(gdn|conv|delta|recurrent)", name, re.I): return "gdn"
    if re.search(r"ngram|ple|lookup", name, re.I): return "ple_ngram"
    if re.search(r"(token_embd|output|norm)", name): return "core"
    return "other"

def main():
    argv = list(sys.argv[1:])
    outfile = None
    if "--out" in argv:
        i = argv.index("--out")
        outfile = argv[i + 1]
        del argv[i:i + 2]
    args = argv
    shards = [parse_shard(p) for p in args]
    meta = shards[0]["meta"]
    allt = []
    for s in shards:
        allt.extend(s["tensors"])
    agg = defaultdict(lambda: {"bytes": 0, "params": 0, "n": 0})
    types_agg = defaultdict(lambda: {"bytes": 0, "params": 0, "n": 0})
    layers = defaultdict(lambda: defaultdict(int))
    big = []
    for t in allt:
        bb, bl = GT.get(t["type"], (None, None))
        if bb is None:
            print(f"UNKNOWN TYPE {t['type']} for {t['name']}", file=sys.stderr)
            continue
        n = 1
        for d in t["ne"]: n *= d
        nbytes = (n + bl - 1) // bl * bb
        c = classify(t["name"])
        agg[c]["bytes"] += nbytes
        agg[c]["params"] += n
        agg[c]["n"] += 1
        tn = NAME2TYPE.get(t["type"], str(t["type"]))
        types_agg[tn]["bytes"] += nbytes
        types_agg[tn]["params"] += n
        types_agg[tn]["n"] += 1
        m = re.search(r"blk\.(\d+)\.", t["name"])
        if m:
            layers[int(m.group(1))][c] += nbytes
        if nbytes > 0.5e9:
            big.append({"name": t["name"], "bytes": nbytes, "type": tn, "ne": t["ne"]})
    total_bytes = sum(a["bytes"] for a in agg.values())
    total_params = sum(a["params"] for a in agg.values())
    report = {
        "meta": meta,
        "total_bytes": total_bytes,
        "total_params": total_params,
        "bits_per_weight_all": total_bytes * 8 / total_params,
        "by_class": {k: dict(v) for k, v in agg.items()},
        "by_type": {k: dict(v) for k, v in types_agg.items()},
        "big_tensors_gt_500MB": sorted(big, key=lambda x: -x["bytes"])[:30],
    }
    # per-layer summary for a representative layer
    if layers:
        l0 = max(layers.keys())
        report["layer_n"] = len(layers)
        report["layer_bytes_example"] = {str(k): v for k, v in layers[l0].items()}
        moe_by_layer = {str(k): v.get("moe_routed", 0) for k, v in sorted(layers.items())}
        report["moe_bytes_per_layer"] = moe_by_layer
    print(json.dumps(report, indent=1, default=str))
    if outfile:
        with open(outfile, "w") as f:
            json.dump(report, f, indent=1, default=str)

if __name__ == "__main__":
    main()
