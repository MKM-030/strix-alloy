#!/usr/bin/env python3
"""Compare a healthy server startup with the arm-C one, and decode the arm-C log correctly."""
import os
import re

RES = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'


def read_any(path):
    with open(path, 'rb') as f:
        raw = f.read()
    if len(raw) > 4 and raw[1::2].count(0) > max(2, len(raw) // 8):
        return raw.decode('utf-16', errors='replace').replace('\x00', '')
    return raw.decode('utf-8', errors='replace').replace('\x00', '')


def show(name, n=14, pattern=None):
    p = os.path.join(RES, name)
    if not os.path.exists(p):
        print(f'  {name}: MISSING')
        return
    txt = read_any(p)
    lines = [l.rstrip() for l in txt.splitlines() if l.strip()]
    if pattern:
        lines = [l for l in lines if re.search(pattern, l)]
    print(f'  --- {name} ({len(txt)} chars) ---')
    for l in lines[:n]:
        print(f'    {l}')
    print()


print('=== HEALTHY run startup: ps-n2.err ===')
show('ps-n2.err', 12)

print('=== ARM-C run startup: ir-il-prefill-ub16k.err ===')
show('ir-il-prefill-ub16k.err', 16)

print('=== progression markers ===')
for name in ('ps-n2.err', 'ir-il-prefill-ub16k.err', 'ir-il-mtp-n2.err'):
    p = os.path.join(RES, name)
    if not os.path.exists(p):
        print(f'  {name}: MISSING'); continue
    txt = read_any(p)
    print(f'  {name}: len={len(txt)}')
    for label, needle in (('device-init', 'ROCm devices'), ('memfail', 'cudaMemGetInfo failed'),
                          ('load-model', 'loading model'), ('ctx', 'constructing llama_context'),
                          ('ready', 'listening on')):
        print(f'      {label:11s} {"YES" if needle in txt else "no"}')

print()
print('=== arm-C orchestration log (decoded) ===')
p = os.path.join(RES, 'ilintar-rebase.log')
if os.path.exists(p):
    txt = read_any(p)
    for l in txt.splitlines():
        if re.search(r'====|EXITED|READY|NOT READY|n=|error|wrote', l):
            print(f'  {l.rstrip()}')
