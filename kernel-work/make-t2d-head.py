#!/usr/bin/env python3
"""Rewrite the FR-Spec head's 'd2t' tensor as the INVERSE map (t2d) the fork prefers.

Fork logic (qwen4exp.cpp):
  loader : d2t_meta->ne[0] == n_vocab(248320)  -> t2d mode, n_vocab_out = output.weight->ne[1]
  graph  : d2t->ne[0] == vocab.n_tokens()      -> expand with ggml_get_rows (gather)
The other branch (ne[0] = 65536) uses ggml_set_rows, which faults on this HIP runtime.

So: keep the tensor NAME 'd2t' (the loader looks that up), make it I32 with 248320 entries where
t2d[v] = draft row for target token v, and a sentinel (n_draft) for tokens the draft cannot emit.

t2d is computed from the existing d2t: t2d[d2t[i]] = i for i in [0, n_draft), else sentinel.

usage: make-t2d-head.py <in.gguf> <out.gguf>
"""
import struct
import sys

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
src = open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/d2t-inspect.py').read()
exec(src.split('def main')[0])
from gguf_inventory import GT, NAME2TYPE


def tensor_bytes(ne, ty):
    bb, bl = GT[ty]
    n = 1
    for d in ne:
        n *= d
    return (n + bl - 1) // bl * bb


def main():
    in_path, out_path = sys.argv[1], sys.argv[2]
    version, kvs, tens, data = read_gguf(in_path)

    n_vocab = 248320
    d2t = next(t for t in tens if t['name'] == 'd2t')
    n_draft = d2t['ne'][0]
    assert d2t['ty'] == 27, "expected I64 d2t"
    fwd = struct.unpack_from(f"<{n_draft}q", data, d2t['off'])

    # invert
    t2d = [n_draft] * n_vocab                 # sentinel = n_draft (out of range -> -inf row in the graph)
    for i, v in enumerate(fwd):
        if 0 <= v < n_vocab:
            t2d[v] = i
    mapped = sum(1 for x in t2d if x != n_draft)
    print(f"d2t(forward) {n_draft} entries -> t2d {n_vocab} entries, mapped={mapped} sentinel={n_vocab - mapped}")
    print(f"  sample t2d[0:8] = {t2d[0:8]}   t2d[d2t[0]] should be 0 -> {t2d[fwd[0]]}")

    blob = struct.pack(f"<{n_vocab}i", *t2d)

    align = 32
    for k, t, v in kvs:
        if k == 'general.alignment':
            align = int(v) if not isinstance(v, tuple) else align

    outs = []
    datanew = bytearray()
    for t in tens:
        if t['name'] == 'd2t':
            ne, ty, b = [n_vocab], 26, blob          # 26 = I32
        else:
            ne, ty = t['ne'], t['ty']
            b = data[t['off']: t['off'] + tensor_bytes(ne, ty)]
        pad = (-len(datanew)) % align
        datanew += b"\0" * pad
        outs.append({'name': t['name'], 'ne': ne, 'ty': ty, 'off': len(datanew)})
        datanew += b

    out = b"GGUF" + struct.pack("<I", version) + struct.pack("<Q", len(outs)) + struct.pack("<Q", len(kvs))
    for k, t, v in kvs:
        out = wstr(out, k) + struct.pack("<I", t)
        out = wval(out, t, v)
    for t in outs:
        out = wstr(out, t['name']) + struct.pack("<I", len(t['ne']))
        for d in t['ne']:
            out += struct.pack("<Q", d)
        out += struct.pack("<I", t['ty']) + struct.pack("<Q", t['off'])
    out += b"\0" * ((-len(out)) % align)
    with open(out_path, 'wb') as g:
        g.write(out)
        g.write(datanew)
    print(f"wrote {out_path}: header {len(out)} + data {len(datanew)}")
    print("now verify: eye of the d2t tensor should be I32, 248320 entries")


if __name__ == "__main__":
    main()
