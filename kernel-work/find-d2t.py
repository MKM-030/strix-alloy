#!/usr/bin/env python3
"""Where did the converter put the d2t bytes? Search the converted file for the 0,1,2.. int64 pattern."""
import struct
import sys

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
src = open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/d2t-inspect.py').read()
exec(src.split('def main')[0])

C = '/mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf'
raw = open(C, 'rb').read()
pat = struct.pack('<8q', 0, 1, 2, 3, 4, 5, 6, 7)
pos = raw.find(pat)
print(f'clean d2t pattern found at file offset: {pos}')
v, kvs, tens, data = read_gguf(C)
print(f'read_gguf data_start = {len(raw) - len(data)}')
d = next(t for t in tens if t['name'] == 'd2t')
print(f'd2t recorded abs = {len(raw) - len(data) + d["off"]}')
for t in tens:
    print(f'  {t["name"]:38s} off={t["off"]:>12d} ne={t["ne"]} ty={t["ty"]}')
