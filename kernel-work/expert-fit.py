#!/usr/bin/env python3
"""CORRECTED expert-ablation analysis.

ERROR IN THE FIRST PASS: I used the single-row expert delta (1.327-0.398 = 0.929 GB).
At width 2 the target verifies THREE rows, and each row selects its own experts, so the
round's expert payload is the UNION across rows, not one row's worth.

  per-expert-layer bytes = 1.327 GB / (10 experts x 48 layers) = 2.765 MB
  union of w rows of k experts over 512, steady state:  U(k,w) = 512*(1-(1-k/512)^w)
  round expert bytes = U(k,3) * 48 * 2.765 MB

Measured (warm): ms(10) = 49.27, ms(3) = 39.60 at width 2.
"""
from math import pow

PER_EXP_LAYER_GB = 1.327 / (10 * 48)      # GB per expert per layer
LAYERS = 48


def union(k, w):
    return 512.0 * (1.0 - pow(1.0 - k / 512.0, w))


def expert_gb(k, w):
    return union(k, w) * LAYERS * PER_EXP_LAYER_GB


W = 3   # verified rows at n-max 2
ms10, ms3 = 49.27, 39.60
e10, e3 = expert_gb(10, W), expert_gb(3, W)

print(f'verified rows w = {W}')
print(f'  k=10: union {union(10,W):5.1f} experts/layer -> {e10:.3f} GB expert payload/round')
print(f'  k= 3: union {union(3,W):5.1f} experts/layer -> {e3:.3f} GB expert payload/round')
print(f'  delta: {e10-e3:.3f} GB removed, {ms10-ms3:.2f} ms saved')
print()

slope = (ms10 - ms3) / (e10 - e3)
fixed = ms3 - slope * e3
print(f'two-point solve:  ms/round = {fixed:.1f} + {slope:.2f} x expert_GB')
print(f'  -> expert component at k=10 = {slope*e10:.1f} ms  ({100*slope*e10/ms10:.0f}% of the round)')
print(f'  -> k-independent remainder  = {fixed:.1f} ms  ({100*fixed/ms10:.0f}% of the round)')
print()

BW_READ = 235.7
print(f'implied expert-path bandwidth = {1.0/slope*1000:.0f} GB/s  vs measured ceiling {BW_READ} GB/s')
print('  ^ ABOVE the streaming ceiling. That means the union estimate is too high: real routing')
print('    overlaps more than uniform-independent predicts, OR the kernel reads fewer distinct')
print('    experts than the union (dedup/reuse). So treat expert GB, and this slope, as an UPPER bound.')
print()

DENSE_W = 2.927
dense_at_ceiling = DENSE_W / BW_READ * 1000.0
print(f'The fixed {fixed:.1f} ms contains the dense weights: {DENSE_W:.3f} GB -> {dense_at_ceiling:.1f} ms at ceiling.')
print(f'  => {fixed - dense_at_ceiling:.1f} ms of the fixed part is NOT dense weight bytes at all')
print(f'     (activations, attention, norms, LM head, and non-weight work).')
print()
print('ROBUST CONCLUSIONS (independent of the union assumption):')
print(f'  1. A large k-independent component exists: ~{fixed:.0f} of {ms10:.0f} ms (~{100*fixed/ms10:.0f}%).')
print(f'  2. Even making ALL expert cost free saves at most ~{100*slope*e10/ms10:.0f}% of the round.')
print(f'  3. Of the fixed part, only ~{dense_at_ceiling:.0f} ms is explained by dense weight bytes;')
print(f'     ~{fixed-dense_at_ceiling:.0f} ms/round is not weight-bandwidth at all.')
