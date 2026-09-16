#!/usr/bin/env python3
"""Build the t2d inverse vocabulary map from the FR-Spec d2t, and inspect its contents.

d2t[i] = target token id for draft row i         (ne[0] = n_draft = 65536)
t2d[v] = draft row for target token v, or n_draft (sentinel) when absent  (ne[0] = n_vocab = 248320)

The fork's t2d branch expands logits with ggml_get_rows (a gather, already exercised everywhere),
which avoids the ggml_set_rows path that faults on HIP.

usage: d2t-inspect.py <head.gguf> [--write-t2d <out.gguf>]
"""
import struct
import sys

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


def read_gguf(path):
    with open(path, "rb") as f:
        assert f.read(4) == b"GGUF"
        version = struct.unpack("<I", f.read(4))[0]
        n_t = struct.unpack("<Q", f.read(8))[0]
        n_kv = struct.unpack("<Q", f.read(8))[0]
        kvs = []
        for _ in range(n_kv):
            k = rstr(f); t = struct.unpack("<I", f.read(4))[0]; kvs.append((k, t, rval(f, t)))
        tens = []
        for _ in range(n_t):
            name = rstr(f)
            nd = struct.unpack("<I", f.read(4))[0]
            ne = [struct.unpack("<Q", f.read(8))[0] for _ in range(nd)]
            ty = struct.unpack("<I", f.read(4))[0]
            off = struct.unpack("<Q", f.read(8))[0]
            tens.append({"name": name, "ne": ne, "ty": ty, "off": off})
        hdr_end = f.tell()
        # NB: tensor-data starts at hdr_end rounded up to general.alignment (usually 32).
        # Reading at hdr_end yields misaligned garbage.
        align = 32
        for k, t, v in kvs:
            if k == "general.alignment":
                align = int(v)
        data_start = (hdr_end + align - 1) // align * align
        f.seek(data_start)
        data = f.read()
    return version, kvs, tens, data


def main():
    path = sys.argv[1]
    out_path = None
    if "--write-t2d" in sys.argv:
        out_path = sys.argv[sys.argv.index("--write-t2d") + 1]

    version, kvs, tens, data = read_gguf(path)
    d2t = next((t for t in tens if t["name"] == "d2t"), None)
    assert d2t, "no d2t tensor"
    n_draft = d2t["ne"][0]
    nbytes = n_draft * (8 if d2t["ty"] == 27 else 4)
    raw = data[d2t["off"]: d2t["off"] + nbytes]
    fmt = "<q" if d2t["ty"] == 27 else "<i"
    vals = list(struct.unpack(f"<{n_draft}{fmt[1]}", raw))

    print(f"d2t: ne={d2t['ne']} type={'I64' if d2t['ty'] == 27 else 'I32'} entries={n_draft}")
    print(f"  min={min(vals)} max={max(vals)}")
    neg = sum(1 for v in vals if v < 0)
    oob = sum(1 for v in vals if v >= 248320)
    uniq = len(set(vals))
    print(f"  negatives={neg}  >=n_vocab(248320)={oob}  unique={uniq} (dupes={n_draft-uniq})")
    print(f"  first 12 = {vals[:12]}")
    print(f"  last  12 = {vals[-12:]}")

    if not out_path:
        return

    n_vocab = 248320
    t2d = [n_draft] * n_vocab          # sentinel = n_draft -> the -inf row of ext
    mapped = 0
    for i, v in enumerate(vals):
        if 0 <= v < n_vocab:
            t2d[v] = i
            mapped += 1
    print(f"\nt2d: {n_vocab} entries, {mapped} mapped, {n_vocab - mapped} sentinel")

    # rewrite the gguf with d2t replaced by t2d (I32)
    blob = struct.pack(f"<{n_vocab}i", *t2d)
    outs = []
    datanew = bytearray()
    align = 32
    for k, t, v in kvs:
        if k == "general.alignment":
            align = int(v)
    for t in tens:
        if t["name"] == "d2t":
            ne, ty, b = [n_vocab], 26, blob      # 26 = I32
        else:
            bb = 0
            from gguf_inventory import GT
            nels = 1
            for d in t["ne"]:
                nels *= d
            blk_b, blk_l = GT[t["ty"]]
            sz = (nels + blk_l - 1) // blk_l * blk_b
            ne, ty, b = t["ne"], t["ty"], data[t["off"]: t["off"] + sz]
        pad = (-len(datanew)) % align
        datanew += b"\0" * pad
        outs.append({"name": t["name"], "ne": ne, "ty": ty, "off": len(datanew)})
        datanew += b

    out = b"GGUF" + struct.pack("<I", version) + struct.pack("<Q", len(outs)) + struct.pack("<Q", len(kvs))
    for k, t, v in kvs:
        out = wstr(out, k) + struct.pack("<I", t)
        out = wval(out, t, v)
    for t in outs:
        out = wstr(out, t["name"]) + struct.pack("<I", len(t["ne"]))
        for d in t["ne"]:
            out += struct.pack("<Q", d)
        out += struct.pack("<I", t["ty"]) + struct.pack("<Q", t["off"])
    out += b"\0" * ((-len(out)) % align)
    with open(out_path, "wb") as g:
        g.write(out)
        g.write(datanew)
    print(f"wrote {out_path} ({len(out) + len(datanew)} bytes)")


if __name__ == "__main__":
    sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
    main()
