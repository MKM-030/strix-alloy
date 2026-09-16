#!/usr/bin/env python3
"""Sanity-check a hidden-dump: values finite, non-degenerate, and rows differ across positions."""
import json
import os
import struct
import sys

prefix = sys.argv[1]
man = json.load(open(prefix + '.json'))
n, d, dt = man['n_tokens'], man['n_embd_out'], man['dtype']
toks = list(struct.unpack(f'<{n}i', open(prefix + '.tokens', 'rb').read()))
raw = open(prefix + '.h', 'rb').read()
print(f'manifest: n={n} d={d} dtype={dt} window={man["window"]}')
print(f'.h size = {len(raw)}  expected = {n*d*(4 if dt=="fp32" else 2)}  ok={len(raw)==n*d*(4 if dt=="fp32" else 2)}')
print(f'tokens first 12: {toks[:12]}  unique={len(set(toks))}')

if dt == 'fp32':
    vals = struct.unpack(f'<{n*d}f', raw)
else:
    import numpy as np
    vals = np.frombuffer(raw, dtype=np.float16).astype('float32')
import numpy as np
v = np.asarray(vals, dtype='float32').reshape(n, d)
print(f'hidden: min={v.min():.4f} max={v.max():.4f} mean={v.mean():.4f} std={v.std():.4f}')
print(f'finite: {np.isfinite(v).all()}   any-NaN: {np.isnan(v).any()}')
z = int((v == 0).sum())
print(f'zeros: {z}/{v.size} ({100*z/v.size:.1f}%)')
# rows should differ
r0, r1, rlast = v[0], v[1], v[-1]
print(f'row0 vs row1  L2 dist = {np.linalg.norm(r0-r1):.3f}')
print(f'row0 vs row-1 L2 dist = {np.linalg.norm(r0-rlast):.3f}')
print(f'norm(row0)={np.linalg.norm(r0):.3f}  norm(rowlast)={np.linalg.norm(rlast):.3f}')
