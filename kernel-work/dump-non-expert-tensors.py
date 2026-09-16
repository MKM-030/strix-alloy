#!/usr/bin/env python3
"""dump-non-expert-tensors.py — list every non-routed-expert, non-PLE tensor with size.

The byte census showed routed experts are only ~32% of a decode step's read set; the other ~68% is
"dense" (attention, HC, GDN, head, norms). This dumps that dense part per tensor so kernel work can
be aimed at the actual majority, and so we can see the per-layer structure (which layers carry full
attention vs GDN vs what).
"""
import glob
import struct
import sys

GGML_TYPE = {0:("F32",1,4),1:("F16",1,2),2:("Q4_0",32,18),3:("Q4_1",32,20),6:("Q5_0",32,22),
    7:("Q5_1",32,24),8:("Q8_0",32,34),9:("Q8_1",32,36),10:("Q2_K",256,84),11:("Q3_K",256,110),
    12:("Q4_K",256,144),13:("Q5_K",256,176),14:("Q6_K",256,210),15:("Q8_K",256,292),
    16:("IQ2_XXS",256,66),17:("IQ2_XS",256,74),18:("IQ3_XXS",256,98),19:("IQ1_S",256,50),
    20:("IQ4_NL",32,18),21:("IQ3_S",256,110),22:("IQ2_S",256,82),23:("IQ4_XS",256,136),
    24:("I8",1,1),25:("I16",1,2),26:("I32",1,4),27:("I64",1,8),28:("F64",1,8),30:("BF16",1,2),
    39:("MXFP4",32,17),34:("TQ1_0",256,54),35:("TQ2_0",256,66)}


class R:
    def __init__(self, f): self.f = f
    def raw(self, n):
        b = self.f.read(n)
        if len(b) != n: raise EOFError
        return b
    def u32(self): return struct.unpack("<I", self.raw(4))[0]
    def u64(self): return struct.unpack("<Q", self.raw(8))[0]
    def st(self): return self.raw(self.u64()).decode("utf-8", "replace")


def read_tensors(path):
    with open(path, "rb") as f:
        r = R(f); assert r.raw(4) == b"GGUF"; r.u32()
        n_tensors = r.u64(); n_kv = r.u64()
        for _ in range(n_kv):
            r.st(); t = r.u32()
            if t == 8: r.st()
            elif t == 9:
                et = r.u32(); n = r.u64()
                if et == 8:
                    for _ in range(n): r.st()
                else:
                    f.seek({0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}.get(et,4)*n, 1)
            else:
                f.seek({0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}.get(t,4), 1)
        out = []
        for _ in range(n_tensors):
            nm = r.st(); nd = r.u32(); dims = [r.u64() for _ in range(nd)]; tt = r.u32(); r.u64()
            out.append((nm, tt, dims))
        return out


def tbytes(tt, dims):
    if tt not in GGML_TYPE: return None
    _, be, bb = GGML_TYPE[tt]
    numel = 1
    for d in dims: numel *= d
    return ((numel + be - 1)//be)*bb


def main():
    pat = sys.argv[1]
    filt = sys.argv[2] if len(sys.argv) > 2 else None
    agg = {}
    for path in sorted(glob.glob(pat)):
        for nm, tt, dims in read_tensors(path):
            if "exps" in nm or nm == "per_layer_token_embd.weight":
                continue
            if filt and filt not in nm:
                continue
            b = tbytes(tt, dims)
            ty = GGML_TYPE[tt][0]
            # strip the layer index so we aggregate by suffix
            import re
            suffix = re.sub(r"^blk\.\d+\.", "blk.*.", nm)
            key = (suffix, ty)
            agg[key] = agg.get(key, 0) + (b or 0)
    print(f"non-expert, non-PLE tensors{f' matching {filt}' if filt else ''}:")
    tot = 0
    for (suf, ty), b in sorted(agg.items(), key=lambda kv: -kv[1]):
        print(f"  {suf:42s} {ty:8s} {b/1e6:9.2f} MB")
        tot += b
    print(f"  {'TOTAL':42s} {'':8s} {tot/1e6:9.2f} MB")


if __name__ == "__main__":
    main()
