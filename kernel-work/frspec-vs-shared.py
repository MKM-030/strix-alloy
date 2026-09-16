#!/usr/bin/env python3
"""Compare the FR-Spec 65k head's tensors against what the fork's nextn block requires."""
import sys
sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
from gguf_inventory import parse_shard

frs = parse_shard('/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf')
shared = parse_shard('/home/revn/models/flash-next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf')

def names(s):
    return sorted(t['name'] for t in s['tensors'])

a, b = set(names(frs)), set(names(shared))
print("=== FR-Spec head tensors ===")
for n in sorted(a):
    print("  ", n)
print("\n=== in FR-Spec but NOT in the working shared head (the naming difference) ===")
for n in sorted(a - b):
    print("  +", n)
print("\n=== in shared but NOT in FR-Spec ===")
for n in sorted(b - a):
    print("  -", n)
print("\n=== metadata keys (hparams-relevant) ===")
for k in sorted(frs['meta']):
    if any(x in k for x in ('nextn', 'block_count', 'd2t', 't2d', 'expert', 'shared')):
        v = frs['meta'][k]
        print(f"  {k} = {v}")
