#!/usr/bin/env python3
"""Compare the two MTP heads' tensor sets to find which has eh_proj (what the fork wants)."""
import sys
sys.path.insert(0, '.')
from gguf_inventory import parse_shard

for path in ('/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0.gguf',
             '/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf',
             '/home/revn/models/flash-next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'):
    try:
        s = parse_shard(path)
    except Exception as e:
        print(f"{path.split('/')[-1]}: ERROR {e}")
        continue
    names = [t['name'] for t in s['tensors']]
    print(f"=== {path.split('/')[-1]} : {len(names)} tensors")
    print("   eh_proj :", [n for n in names if 'eh_proj' in n])
    print("   d2t     :", [n for n in names if n == 'd2t'])
    print("   output  :", [(t['name'], t['ne']) for t in s['tensors'] if t['name'] == 'output.weight'])
    print("   nextn   :", len([n for n in names if 'nextn' in n]), "->", sorted(n for n in names if 'nextn' in n)[:6])
