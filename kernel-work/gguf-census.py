#!/usr/bin/env python3
"""gguf-census.py — dump a GGUF's metadata keys and tensor names/types/shapes.

Pure header parse, no deps. Used to check whether the 'shared' MTP sidecar omits the
tensors a normal model would carry (token_embd / output_norm / output), which is the
documented precondition for the shared-MTP fit/load failure.
"""
import struct
import sys

GGUF_TYPE = {
    0: ("u8", 1), 1: ("i8", 1), 2: ("u16", 2), 3: ("i16", 2), 4: ("u32", 4), 5: ("i32", 4),
    6: ("f32", 4), 7: ("bool", 1), 8: ("str", None), 9: ("arr", None), 10: ("u64", 8),
    11: ("i64", 8), 12: ("f64", 8),
}

# ggml type ids we care about (subset)
GGML_TYPE = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1", 8: "Q8_0", 9: "Q8_1",
    10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 15: "Q8_K", 16: "IQ2_XXS",
    17: "IQ2_XS", 18: "IQ3_XXS", 19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S",
    23: "IQ4_XS", 24: "I8", 25: "I16", 26: "I32", 27: "I64", 28: "F64", 30: "BF16",
    39: "MXFP4",
}


class R:
    def __init__(self, f):
        self.f = f

    def raw(self, n):
        b = self.f.read(n)
        if len(b) != n:
            raise EOFError("short read")
        return b

    def u32(self):
        return struct.unpack("<I", self.raw(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.raw(8))[0]

    def i32(self):
        return struct.unpack("<i", self.raw(4))[0]

    def st(self):
        n = self.u64()
        return self.raw(n).decode("utf-8", "replace")

    def val(self, t):
        name, size = GGUF_TYPE[t]
        if name == "u8":  return struct.unpack("<B", self.raw(1))[0]
        if name == "i8":  return struct.unpack("<b", self.raw(1))[0]
        if name == "u16": return struct.unpack("<H", self.raw(2))[0]
        if name == "i16": return struct.unpack("<h", self.raw(2))[0]
        if name == "u32": return self.u32()
        if name == "i32": return self.i32()
        if name == "f32": return struct.unpack("<f", self.raw(4))[0]
        if name == "f64": return struct.unpack("<d", self.raw(8))[0]
        if name == "u64": return self.u64()
        if name == "i64": return struct.unpack("<q", self.raw(8))[0]
        if name == "bool": return struct.unpack("<B", self.raw(1))[0]
        if name == "str": return self.st()
        if name == "arr":
            et = self.u32()
            n = self.u64()
            # only fully materialize small scalar arrays; skip big ones
            vals = []
            for _ in range(n):
                vals.append(self.val(et))
            return vals
        raise ValueError(t)


def main():
    path = sys.argv[1]
    show_meta = "--meta" in sys.argv
    with open(path, "rb") as f:
        r = R(f)
        magic = r.raw(4)
        if magic != b"GGUF":
            print("NOT GGUF:", magic); return
        ver = r.u32()
        n_tensors = r.u64()
        n_kv = r.u64()
        print(f"file    : {path}")
        print(f"version : {ver}")
        print(f"tensors : {n_tensors}")
        print(f"kv      : {n_kv}")
        meta = {}
        for _ in range(n_kv):
            k = r.st()
            t = r.u32()
            v = r.val(t)
            meta[k] = v
            if show_meta:
                sv = v if not isinstance(v, list) or len(v) <= 8 else f"[array len={len(v)}]"
                print(f"  {k} = {sv}")
        names = []
        for _ in range(n_tensors):
            nm = r.st()
            nd = r.u32()
            dims = [r.u64() for _ in range(nd)]
            tt = r.u32()
            off = r.u64()
            names.append((nm, GGML_TYPE.get(tt, f"t{tt}"), dims, off))
        align = meta.get("general.alignment", 32)
        hdr_end = f.tell()
        data_off = (hdr_end + align - 1) // align * align
        print(f"hdr_end : {hdr_end}  data_off(align {align}) : {data_off}")
        print("--- tensors ---")
        for nm, tt, dims, off in names:
            print(f"  {nm:60s} {tt:8s} {dims}")
        # shared-tensor check
        joined = "\n".join(n for n, _, _, _ in names)
        for probe in ("token_embd.weight", "output_norm.weight", "output.weight"):
            print(f"  HAS {probe:24s} : {probe in joined}")
    return


if __name__ == "__main__":
    main()
