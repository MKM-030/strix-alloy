#!/usr/bin/env python3
"""Convert the FR-Spec 65k MTP head into the pwilkin fork's head layout.

Two mechanical transforms, NO requantization:

 1. RENAME  hc_norm/hc_down/hc_up  ->  hc_head_norm/hc_head_down/hc_head_up   (identical shapes)
 2. CONCAT  fc_embd [2560,2560] + fc_hidden [2560,2560]  ->  eh_proj [5120,2560]
            (the fork's eh_proj consumes concat(embed, hidden) along K, so the two per-row
             projections are row-wise concatenated: row r of eh_proj = fc_embd row r ++ fc_hidden row r)
 3. KEEP    d2t [65536] I64 and output.weight [2560,65536] Q8_0 as-is (the vocab trim the fork reads)

Only Q8_0 blocks of 32 elements are involved, so 2560/32 = 80 blocks per row align exactly and the
concat is byte-exact block concatenation. All other tensors are copied verbatim.

usage: convert-frspec-head.py <in.gguf> <out.gguf>
"""
import struct
import sys
from collections import OrderedDict

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
from gguf_inventory import GT   # (block_bytes, block_len) per ggml type

RENAME = {
    "blk.48.nextn.hc_norm.weight": "blk.48.nextn.hc_head_norm.weight",
    "blk.48.nextn.hc_down.weight": "blk.48.nextn.hc_head_down.weight",
    "blk.48.nextn.hc_up.weight":   "blk.48.nextn.hc_head_up.weight",
}
FC_EMBD   = "blk.48.nextn.fc_embd.weight"
FC_HIDDEN = "blk.48.nextn.fc_hidden.weight"
EH_PROJ   = "blk.48.nextn.eh_proj.weight"

VT = {0: ("B", 1), 1: ("b", 1), 2: ("H", 2), 3: ("h", 2), 4: ("I", 4), 5: ("i", 4),
      6: ("f", 4), 7: ("?", 1), 10: ("Q", 8), 11: ("q", 8), 12: ("d", 8)}


def rstr(f):
    n = struct.unpack("<Q", f.read(8))[0]
    return f.read(n).decode("utf-8", "replace")


def wstr(out, s):
    b = s.encode("utf-8")
    return out + struct.pack("<Q", len(b)) + b


def rval(f, t):
    if t == 8:
        return rstr(f)
    if t == 9:
        et = struct.unpack("<I", f.read(4))[0]
        n = struct.unpack("<Q", f.read(8))[0]
        # preserve the declared element type: it is authoritative and must be written back verbatim
        return ("ARR", et, [rval(f, et) for _ in range(n)])
    fmt, sz = VT[t]
    return struct.unpack("<" + fmt, f.read(sz))[0]


def wval(out, t, v):
    if t == 8:
        return wstr(out, v)
    if t == 9:
        _, et, items = v
        out += struct.pack("<I", et) + struct.pack("<Q", len(items))
        for x in items:
            out = wval(out, et, x)
        return out
    fmt, _ = VT[t]
    return out + struct.pack("<" + fmt, v)


def tbytes(ne, ty):
    bb, bl = GT[ty]
    n = 1
    for d in ne:
        n *= d
    return (n + bl - 1) // bl * bb


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        assert f.read(4) == b"GGUF"
        version = struct.unpack("<I", f.read(4))[0]
        n_tensors = struct.unpack("<Q", f.read(8))[0]
        n_kv = struct.unpack("<Q", f.read(8))[0]
        kvs = []
        for _ in range(n_kv):
            k = rstr(f); t = struct.unpack("<I", f.read(4))[0]; kvs.append((k, t, rval(f, t)))
        tens = []
        for _ in range(n_tensors):
            name = rstr(f)
            nd = struct.unpack("<I", f.read(4))[0]
            ne = [struct.unpack("<Q", f.read(8))[0] for _ in range(nd)]
            ty = struct.unpack("<I", f.read(4))[0]
            off = struct.unpack("<Q", f.read(8))[0]
            tens.append({"name": name, "ne": ne, "ty": ty, "off": off})
        hdr_end = f.tell()
        # alignment from metadata (default 32)
        align = 32
        for k, t, v in kvs:
            if k == "general.alignment":
                align = int(v)

        # read the data section -- tensor offsets are relative to hdr_end ROUNDED UP to
        # general.alignment, not hdr_end itself. Seeking to hdr_end shifts every blob by
        # (-hdr_end) % align bytes and corrupts the copy (incl. d2t).
        f.seek((hdr_end + align - 1) // align * align)
        data = f.read()

    by_name = {t["name"]: t for t in tens}
    for n in (FC_EMBD, FC_HIDDEN):
        assert n in by_name, f"missing {n}"

    out_tensors = []
    out_data = bytearray()

    def place(name, ne, ty, blob):
        nonlocal out_data
        pad = (-len(out_data)) % align
        out_data += b"\0" * pad
        off = len(out_data)
        out_data += blob
        out_tensors.append({"name": name, "ne": ne, "ty": ty, "off": off})

    for t in tens:
        n = t["name"]
        if n in (FC_EMBD, FC_HIDDEN):
            continue  # handled together below
        blob = data[t["off"]: t["off"] + tbytes(t["ne"], t["ty"])]
        place(RENAME.get(n, n), t["ne"], t["ty"], blob)

    # build eh_proj = row-wise concat(fc_embd, fc_hidden) along K
    e = by_name[FC_EMBD]; h = by_name[FC_HIDDEN]
    assert e["ty"] == h["ty"] == 8, "expected Q8_0"
    K, M = e["ne"][0], e["ne"][1]          # 2560, 2560
    assert h["ne"] == [K, M]
    eb = tbytes(e["ne"], e["ty"])
    hb = tbytes(h["ne"], h["ty"])
    rb = eb // M                            # bytes per row (80 blocks * 34 = 2720)
    rb2 = hb // M
    eb_src = data[e["off"]: e["off"] + eb]
    hb_src = data[h["off"]: h["off"] + hb]
    merged = bytearray()
    for r in range(M):
        merged += eb_src[r * rb:(r + 1) * rb]
        merged += hb_src[r * rb2:(r + 1) * rb2]
    place(EH_PROJ, [K * 2, M], e["ty"], bytes(merged))
    print(f"eh_proj = concat(fc_embd, fc_hidden) -> ne=[{K*2},{M}] {len(merged)} bytes")

    # rebuild header
    out = b"GGUF" + struct.pack("<I", version) + struct.pack("<Q", len(out_tensors)) + struct.pack("<Q", n_kv)
    for k, t, v in kvs:
        out = wstr(out, k) + struct.pack("<I", t)
        out = wval(out, t, v)
    for t in out_tensors:
        out = wstr(out, t["name"]) + struct.pack("<I", len(t["ne"]))
        for d in t["ne"]:
            out += struct.pack("<Q", d)
        out += struct.pack("<I", t["ty"]) + struct.pack("<Q", t["off"])
    pad = (-len(out)) % align
    out += b"\0" * pad

    with open(dst, "wb") as g:
        g.write(out)
        g.write(out_data)
    print(f"tensors in={len(tens)} out={len(out_tensors)}")
    print(f"wrote {dst}: header {len(out)} + data {len(out_data)} = {len(out)+len(out_data)} bytes")


if __name__ == "__main__":
    main()
