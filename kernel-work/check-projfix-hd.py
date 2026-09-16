#!/usr/bin/env python3
"""Verify the PROJFIX hidden dump directly by size + content (manifest may be malformed)."""
import numpy as np
import struct

prefix = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/projfix-hd'
n, d = 8192, 10240
raw = open(prefix + '.h', 'rb').read()
print(f'.h size = {len(raw)}  expected = {n*d*2}  ok = {len(raw) == n*d*2}')
toks = list(struct.unpack(f'<{n}i', open(prefix + '.tokens', 'rb').read()))
print(f'tokens: n={len(toks)} first12={toks[:12]} unique={len(set(toks))} min={min(toks)} max={max(toks)}')

v = np.frombuffer(raw, dtype=np.float16).astype('float32').reshape(n, d)
print(f'hidden: min={v.min():.3f} max={v.max():.3f} mean={v.mean():.4f} std={v.std():.4f}')
print(f'finite={np.isfinite(v).all()}  NaN={np.isnan(v).any()}  zeros={int((v==0).sum())}/{v.size}')
# hyper-connection streams: 4 x 2560; check each stream is non-degenerate
for s in range(4):
    seg = v[:, s*2560:(s+1)*2560]
    print(f'  stream {s}: std={seg.std():.3f} mean={seg.mean():.4f}')
# windows: rows should differ within and across windows
print(f'L2(row0,row1)   = {np.linalg.norm(v[0]-v[1]):.3f}')
print(f'L2(row0,row2047)= {np.linalg.norm(v[0]-v[2047]):.3f}')
print(f'L2(row2048,row0)= {np.linalg.norm(v[2048]-v[0]):.3f}  (first row of window 2)')
print(f'L2(row0,row8191) = {np.linalg.norm(v[0]-v[8191]):.3f}')
