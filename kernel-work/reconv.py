#!/usr/bin/env python3
"""Re-run the converter in-process, then immediately verify the output's d2t integrity."""
import os
import struct
import subprocess
import sys

KW = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work'
sys.path.insert(0, KW)
src = open(os.path.join(KW, 'd2t-inspect.py')).read()
exec(src.split('def main')[0])

O = '/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf'
C = '/mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf'

print(f'existing converted file mtime: {os.path.getmtime(C)}  size {os.path.getsize(C)}')
r = subprocess.run(['python3', os.path.join(KW, 'convert-frspec-head.py'), O, C],
                   capture_output=True, text=True)
print('--- converter stdout ---')
print(r.stdout)
print('--- converter stderr ---')
print(r.stderr[-2000:])

v, kvs, tens, data = read_gguf(C)
d = next(t for t in tens if t['name'] == 'd2t')
raw = data[d['off']: d['off'] + 65536 * 8]
vals = struct.unpack('<65536q', raw)
inr = sum(1 for x in vals if 0 <= x < 248320)
print(f'AFTER re-convert: d2t first8={vals[:8]}  in-range={inr}/65536')
