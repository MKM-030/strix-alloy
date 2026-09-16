#!/usr/bin/env python3
"""Validate my GGUF data reader: check a known-good F32 tensor and the d2t on the ORIGINAL file."""
import struct
import sys

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
src = open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/d2t-inspect.py').read()
exec(src.split('def main')[0])

PATH = '/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf'
version, kvs, tens, data = read_gguf(PATH)
print("tensors:", len(tens), " data bytes:", len(data))

# 1) F32 tensors should read near 1.0 if alignment is right
for t in tens:
    if t['name'].endswith(('enorm.weight', 'hc_norm.weight', 'hnorm.weight')):
        vals = struct.unpack_from('<6f', data, t['off'])
        print(f"  {t['name']:40s} ne={t['ne']} -> {['%.4f' % x for x in vals]}")

# 2) d2t
d2t = next(t for t in tens if t['name'] == 'd2t')
n = d2t['ne'][0]
raw = data[d2t['off']: d2t['off'] + n * 8]
vals = struct.unpack(f'<{n}q', raw)
print(f"\n  d2t ne={d2t['ne']} ty={d2t['ty']}  min={min(vals)} max={max(vals)}")
print(f"  first 10 = {vals[:10]}")
inrange = sum(1 for v in vals if 0 <= v < 248320)
print(f"  entries in [0,248320) = {inrange}/{n}")
