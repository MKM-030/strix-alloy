#!/usr/bin/env python3
"""Compare a HEALTHY native run's log against the current failing one, line by line."""
import os
import re

RES = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'


def read_any(p):
    with open(p, 'rb') as f:
        raw = f.read()
    if len(raw) > 4 and raw[1::2].count(0) > max(2, len(raw) // 8):
        return raw.decode('utf-16', errors='replace').replace('\x00', '')
    return raw.decode('utf-8', errors='replace').replace('\x00', '')


def show(name, label):
    p = os.path.join(RES, name)
    print(f'===== {label}: {name} =====')
    if not os.path.exists(p):
        print('  MISSING\n'); return
    t = read_any(p)
    lines = [l.rstrip() for l in t.splitlines() if l.strip()]
    print(f'  ({len(t)} chars, {len(lines)} lines)')
    for l in lines[:22]:
        print('   ', l)
    print()


show('ps-n2.err', 'HEALTHY (17:10, arm A)')
show('gpuprobe.err', 'FAILING (now)')

print('===== signature search across logs =====')
for name in ('ps-n2.err', 'gpuprobe.err', 'ir-il-prefill-ub16k.err'):
    p = os.path.join(RES, name)
    if not os.path.exists(p):
        continue
    t = read_any(p)
    flags = []
    for needle in ('found 1 ROCm devices', 'Device 0: AMD', 'cudaMemGetInfo',
                   'threadpool init', 'constructing llama_context', 'listening on',
                   'using device ROCm0', 'load_tensors', 'llama_model_loader'):
        flags.append(('YES' if needle in t else '--', needle))
    print(f'  {name}:')
    for mark, needle in flags:
        print(f'      {mark:4s} {needle}')
