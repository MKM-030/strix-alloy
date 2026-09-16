#!/usr/bin/env python3
"""Pin down the converter's offset bug using the known-good read_gguf."""
import os
import struct
import sys

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
src = open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/d2t-inspect.py').read()
exec(src.split('def main')[0])

P = '/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf'
v, kvs, tens, data = read_gguf(P)
fs = os.path.getsize(P)
d = next(t for t in tens if t['name'] == 'd2t')
print(f'filesize      {fs}')
print(f'data len      {len(data)}')
print(f'=> data_start {fs - len(data)}   (%32 = {(fs - len(data)) % 32})')
print(f'd2t off       {d["off"]}')
abs_good = (fs - len(data)) + d['off']
raw = open(P, 'rb').read()
vals = struct.unpack('<8q', raw[abs_good:abs_good + 64])
print(f'd2t first8 at data_start: {vals}')
# how many tensors, and which names
print(f'tensors: {len(tens)}')
# shift hypothesis: converter read data from hdr_end = data_start - shift
for sh in range(0, 32):
    st = abs_good - sh
    if st < 0:
        continue
    v2 = struct.unpack('<8q', raw[st:st + 64])
    if v2[0] == 0 and v2[1] == 1 and v2[2] == 2:
        print(f'!!! shift {sh} gives clean start: {v2}')
