#!/usr/bin/env python3
"""Shapes of the FR-Spec vs shared head nextn tensors — decides rename vs concat."""
import sys
sys.path.insert(0, '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work')
from gguf_inventory import parse_shard, GT, NAME2TYPE

for label, path in (("FR-Spec 65k", '/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf'),
                    ("shared",     '/home/revn/models/flash-next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf')):
    s = parse_shard(path)
    print(f"=== {label}")
    for t in s['tensors']:
        n = t['name']
        if 'nextn' in n or n in ('d2t', 'output.weight', 'token_embd.weight'):
            print(f"   {n:44s} {NAME2TYPE.get(t['type'], t['type']):6s} ne={t['ne']}")
