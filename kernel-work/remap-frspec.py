#!/usr/bin/env python3
"""Remap the FR-Spec MTP head's tensor names to the pwilkin fork's naming so it loads there.

Only the NAME STRINGS change; the tensor data, shapes and types are untouched. The mapping is
mechanical and reversible:

  blk.48.nextn.fc_embd.weight   -> blk.48.nextn.eh_proj.weight      (the token/hidden projection)
  blk.48.nextn.fc_hidden.weight -> (dropped: fork has no counterpart; fc_hidden feeds the hidden
                                   state; check shape before dropping)
  blk.48.nextn.hc_norm.weight   -> blk.48.nextn.hc_head_norm.weight
  blk.48.nextn.hc_down.weight   -> blk.48.nextn.hc_head_down.weight
  blk.48.nextn.hc_up.weight     -> blk.48.nextn.hc_head_up.weight

Rewrites only the GGUF header strings in place (same byte length required, or we pad/rewrite the
header block). Because renaming changes string lengths, we rebuild the header: read metadata+tensor
table, rewrite with new names, then copy the tensor data region unchanged.

usage: remap-frspec.py <in.gguf> <out.gguf>
"""
import json
import struct
import sys

MAP = {
    "blk.48.nextn.fc_embd.weight":   "blk.48.nextn.eh_proj.weight",
    "blk.48.nextn.hc_norm.weight":   "blk.48.nextn.hc_head_norm.weight",
    "blk.48.nextn.hc_down.weight":   "blk.48.nextn.hc_head_down.weight",
    "blk.48.nextn.hc_up.weight":     "blk.48.nextn.hc_head_up.weight",
}
DROP = {"blk.48.nextn.fc_hidden.weight"}

# --- minimal GGUF reader/writer for the header only ---
VT = {0: ("B", 1), 1: ("b", 1), 2: ("H", 2), 3: ("h", 2), 4: ("I", 4), 5: ("i", 4),
      6: ("f", 4), 7: ("?", 1), 10: ("Q", 8), 11: ("q", 8), 12: ("d", 8)}


def read_str(f):
    n = struct.unpack("<Q", f.read(8))[0]
    return f.read(n).decode("utf-8", "replace")


def write_str(out, s):
    b = s.encode("utf-8")
    out += struct.pack("<Q", len(b)) + b
    return out


def read_val(f, t):
    if t == 8:
        return read_str(f)
    if t == 9:
        et = struct.unpack("<I", f.read(4))[0]
        n = struct.unpack("<Q", f.read(8))[0]
        return [read_val(f, et) for _ in range(n)]
    fmt, sz = VT[t]
    return struct.unpack("<" + fmt, f.read(sz))[0]


def write_val(out, t, v):
    if t == 8:
        return write_str(out, v)
    if t == 9:
        et = 4 if isinstance(v[0], int) else (6 if isinstance(v[0], float) else 8)
        out += struct.pack("<I", et) + struct.pack("<Q", len(v))
        for x in v:
            out = write_val(out, et, x)
        return out
    fmt, _ = VT[t]
    return out + struct.pack("<" + fmt, v)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        assert f.read(4) == b"GGUF"
        version = struct.unpack("<I", f.read(4))[0]
        n_tensors = struct.unpack("<Q", f.read(8))[0]
        n_kv = struct.unpack("<Q", f.read(8))[0]

        kvs = []
        for _ in range(n_kv):
            k = read_str(f)
            t = struct.unpack("<I", f.read(4))[0]
            kvs.append((k, t, read_val(f, t)))

        tensors = []
        for _ in range(n_tensors):
            name = read_str(f)
            nd = struct.unpack("<I", f.read(4))[0]
            ne = [struct.unpack("<Q", f.read(8))[0] for _ in range(nd)]
            ty = struct.unpack("<I", f.read(4))[0]
            off = struct.unpack("<Q", f.read(8))[0]
            tensors.append((name, nd, ne, ty, off))
        header_end = f.tell()

    renamed = dropped = 0
    out_tensors = []
    kept = []
    for name, nd, ne, ty, off in tensors:
        if name in DROP:
            print(f"  dropping {name} ne={ne} type={ty}")
            dropped += 1
            continue
        new = MAP.get(name, name)
        if new != name:
            print(f"  renaming {name} -> {new}")
            renamed += 1
        kept.append(off)
        out_tensors.append((new, nd, ne, ty, off))
    print(f"renamed={renamed} dropped={dropped} tensors_out={len(out_tensors)}")

    # rebuild header with new names; tensor offsets are relative to the data region, which we copy verbatim
    out = b"GGUF" + struct.pack("<I", version) + struct.pack("<Q", len(out_tensors)) + struct.pack("<Q", n_kv)
    for k, t, v in kvs:
        out = write_str(out, k) + struct.pack("<I", t)
        out = write_val(out, t, v)
    for name, nd, ne, ty, off in out_tensors:
        out = write_str(out, name) + struct.pack("<I", nd)
        for d in ne:
            out += struct.pack("<Q", d)
        out += struct.pack("<I", ty) + struct.pack("<Q", off)

    # pad to the original header alignment
    pad = (-len(out)) % 32
    out += b"\0" * pad
    print(f"header: {header_end} -> {len(out)} bytes (+{pad} pad)")

    with open(dst, "wb") as g:
        g.write(out)
        with open(src, "rb") as f:
            f.seek(header_end)
            while True:
                chunk = f.read(64 * 1024 * 1024)
                if not chunk:
                    break
                g.write(chunk)
    print(f"wrote {dst}")


if __name__ == "__main__":
    main()
