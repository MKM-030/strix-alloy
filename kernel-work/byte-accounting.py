#!/usr/bin/env python3
"""byte-accounting.py — sum GGUF tensor bytes by category across all shards.

Purpose: find where a DECODE step's weight traffic actually goes, so kernel work targets the
dominant path (quantized matvec / hyper-connection) rather than a minority (F32/BF16 MMVF).

Per-tensor bytes are computed exactly from the ggml type's block layout:
  bytes = (numel / block_elems) * block_bytes
plus 2 bytes for each quantized block with a bf16 shadow-free layout? No -- we use the nominal
block size, which is what is read from disk on a cold read.
"""
import glob
import os
import struct
import sys

GGML_TYPE = {
    0: ("F32", 1, 4), 1: ("F16", 1, 2), 2: ("Q4_0", 32, 18), 3: ("Q4_1", 32, 20),
    6: ("Q5_0", 32, 22), 7: ("Q5_1", 32, 24), 8: ("Q8_0", 32, 34), 9: ("Q8_1", 32, 36),
    10: ("Q2_K", 256, 84), 11: ("Q3_K", 256, 110), 12: ("Q4_K", 256, 144), 13: ("Q5_K", 256, 176),
    14: ("Q6_K", 256, 210), 15: ("Q8_K", 256, 292), 16: ("IQ2_XXS", 256, 66), 17: ("IQ2_XS", 256, 74),
    18: ("IQ3_XXS", 256, 98), 19: ("IQ1_S", 256, 50), 20: ("IQ4_NL", 32, 18), 21: ("IQ3_S", 256, 110),
    22: ("IQ2_S", 256, 82), 23: ("IQ4_XS", 256, 136), 24: ("I8", 1, 1), 25: ("I16", 1, 2),
    26: ("I32", 1, 4), 27: ("I64", 1, 8), 28: ("F64", 1, 8), 30: ("BF16", 1, 2), 39: ("MXFP4", 32, 17),
    34: ("TQ1_0", 256, 54), 35: ("TQ2_0", 256, 66),
}


class R:
    def __init__(self, f):
        self.f = f

    def raw(self, n):
        b = self.f.read(n)
        if len(b) != n:
            raise EOFError
        return b

    def u32(self):
        return struct.unpack("<I", self.raw(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.raw(8))[0]

    def st(self):
        return self.raw(self.u64()).decode("utf-8", "replace")


def read_tensors(path):
    with open(path, "rb") as f:
        r = R(f)
        assert r.raw(4) == b"GGUF"
        r.u32()
        n_tensors = r.u64()
        n_kv = r.u64()
        for _ in range(n_kv):
            r.st()
            t = r.u32()
            if t == 8:
                r.st()
            elif t == 9:
                et = r.u32(); n = r.u64()
                if et == 8:
                    for _ in range(n): r.st()
                else:
                    sz = {0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
                    f.seek(sz.get(et,4)*n, 1)
            else:
                sz = {0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
                f.seek(sz.get(t,4), 1)
        out = []
        for _ in range(n_tensors):
            nm = r.st()
            nd = r.u32()
            dims = [r.u64() for _ in range(nd)]
            tt = r.u32()
            r.u64()
            out.append((nm, tt, dims))
        return out


def tbytes(tt, dims):
    if tt not in GGML_TYPE:
        return None
    _, be, bb = GGML_TYPE[tt]
    numel = 1
    for d in dims:
        numel *= d
    nblk = (numel + be - 1) // be
    return nblk * bb


def main():
    files = sorted(glob.glob(sys.argv[1]))
    if not files:
        print("no files", sys.argv[1:]); return
    cat = {}
    percat = {}
    total = 0
    for path in files:
        for nm, tt, dims in read_tensors(path):
            b = tbytes(tt, dims)
            if b is None:
                print("unknown type", tt, nm); continue
            total += b
            # category. NOTE ordering: check hyper-connection BEFORE attention, because the HC tensors
            # are named blk.N.hc_attn_* / blk.N.hc_ffn_* and would otherwise match the attn_ rule.
            if "ffn_gate_exps" in nm or "ffn_up_exps" in nm or "ffn_down_exps" in nm:
                c = "routed_experts"
            elif "hc_" in nm or nm.startswith("output_hc"):
                c = "hyper_connection"
            elif "shexp" in nm:
                c = "shared_expert"
            elif "indexer" in nm:
                c = "qsa_indexer"
            elif nm.startswith("blk.") and "attn_" in nm:
                c = "attention"
            elif ".nextn" in nm:
                c = "mtp_head"
            elif nm.startswith("output") or nm == "token_embd.weight":
                c = "embed_head"
            elif nm == "per_layer_token_embd.weight":
                c = "ple_table"
            elif "conv" in nm or "ssm" in nm or "linear_attn" in nm or nm.endswith("a.weight") or nm.endswith("dt_bias"):
                c = "gdn_linear_attn"
            else:
                c = "other"
            cat[c] = cat.get(c, 0) + b
            percat.setdefault(c, {})
            ty = GGML_TYPE[tt][0]
            percat[c][ty] = percat[c].get(ty, 0) + b
    print(f"files: {len(files)}")
    print(f"total: {total/1e9:.3f} GB")
    print("--- by category ---")
    for c, b in sorted(cat.items(), key=lambda kv: -kv[1]):
        types = ", ".join(f"{t}={v/1e9:.3f}GB" for t, v in sorted(percat[c].items(), key=lambda kv: -kv[1])[:4])
        print(f"  {c:24s} {b/1e9:8.3f} GB  ({100*b/total:5.1f}%)  [{types}]")


if __name__ == "__main__":
    main()
