#!/usr/bin/env python3
"""Is the CONVERTED head's d2t intact? If not, the earlier HIP fault was my converter's bug."""
import struct
import sys

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
src = open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/d2t-inspect.py').read()
exec(src.split('def main')[0])

for label, path in (("ORIGINAL", '/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf'),
                    ("CONVERTED", '/mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf')):
    v, kvs, tens, data = read_gguf(path)
    print(f"=== {label}: {len(tens)} tensors, data {len(data)} bytes")
    for t in tens:
        if t['name'] in ('d2t', 'output.weight', 'blk.48.nextn.eh_proj.weight'):
            nb = 0
            from gguf_inventory import GT
            bb, bl = GT[t['ty']]
            n = 1
            for d in t['ne']:
                n *= d
            nb = (n + bl - 1) // bl * bb
            # is the claimed extent inside the data buffer?
            ok = t['off'] + nb <= len(data)
            print(f"   {t['name']:34s} ty={t['ty']:3d} off={t['off']:>12d} ne={t['ne']} size={nb:>12d} fits={ok}")
    d = next(t for t in tens if t['name'] == 'd2t')
    n = d['ne'][0]
    step = 8 if d['ty'] == 27 else 4
    raw = data[d['off']: d['off'] + n * step]
    if len(raw) == n * step:
        fmt = 'q' if d['ty'] == 27 else 'i'
        vals = struct.unpack(f'<{n}{fmt}', raw)
        inr = sum(1 for x in vals if 0 <= x < 248320)
        print(f"   d2t first10={vals[:10]}  in-range={inr}/{n}")
    else:
        print(f"   d2t TRUNCATED: have {len(raw)} need {n*step}")
    # max extent
    maxend = 0
    for t in tens:
        bb, bl = GT[t['ty']]
        nn = 1
        for dd in t['ne']:
            nn *= dd
        maxend = max(maxend, t['off'] + (nn + bl - 1) // bl * bb)
    print(f"   max tensor end = {maxend}   data len = {len(data)}   (data covers: {maxend <= len(data)})")
