#!/usr/bin/env python3
"""Replicate the converter's header build and print exact lengths to locate the 6-byte skew."""
import os
import struct
import sys
from collections import OrderedDict

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
src = open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/d2t-inspect.py').read()
exec(src.split('def main')[0])

O = '/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf'
C = '/mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf'

for label, P in (('ORIG', O), ('CONV', C)):
    v, kvs, tens, data = read_gguf(P)
    fs = os.path.getsize(P)
    # metadata-only header length
    hdr = b'GGUF' + struct.pack('<I', v) + struct.pack('<Q', len(tens)) + struct.pack('<Q', len(kvs))
    for k, t, val in kvs:
        hdr = wstr(hdr, k) + struct.pack('<I', t)
        hdr = wval(hdr, t, val)
    meta_len = len(hdr)
    # full header incl tensor infos
    full = hdr
    for t in tens:
        full = wstr(full, t['name']) + struct.pack('<I', len(t['ne']))
        for d in t['ne']:
            full += struct.pack('<Q', d)
        full += struct.pack('<I', t['ty']) + struct.pack('<Q', t['off'])
    hdr_end = len(full)
    pad = (-hdr_end) % 32
    print(f'{label}: meta_len={meta_len} hdr_end={hdr_end} pad={pad} aligned={hdr_end+pad}')
    print(f'   file_size={fs} data_len={len(data)} => implied data_start={fs-len(data)}')
    d = next(t for t in tens if t['name'] == 'd2t')
    print(f'   d2t off={d["off"]}  implied abs={fs-len(data)+d["off"]}')
