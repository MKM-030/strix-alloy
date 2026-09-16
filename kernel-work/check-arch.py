#!/usr/bin/env python3
"""Read general.architecture + nextn tensors from a GGUF to confirm MTP support."""
import os
import struct
import sys

sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
src = open('/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/d2t-inspect.py').read()
exec(src.split('def main')[0])

for p in sys.argv[1:]:
    if not os.path.exists(p):
        print(p, 'MISSING')
        continue
    v, kvs, tens, data = read_gguf(p)
    arch = next((val for k, t, val in kvs if k == 'general.architecture'), '?')
    nnext = [t['name'] for t in tens if 'nextn' in t['name']]
    print(f'{os.path.basename(p)}: arch={arch}  tensors={len(tens)}  size={os.path.getsize(p)/1e9:.1f}GB  nextn={len(nnext)}')
    for n in nnext[:4]:
        print('   ', n)
