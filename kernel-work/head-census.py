#!/usr/bin/env python3
"""Tensor census of the MTP draft heads: exact type + byte size per tensor, and the
per-draft-step projection cost (output.weight rows dominate the draft LM head)."""
import os
import sys

KW = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work'
sys.path.insert(0, KW)
src = open(os.path.join(KW, 'd2t-inspect.py')).read()
exec(src.split('def main')[0])
from gguf_inventory import GT

HEADS = {
    'shared-Q8_0 (2.60 GiB)': '/mnt/c/AI/models/qwen38-flash/projfix/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf',
    'frspec-65k-pwhead (3.64 GiB)': '/mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf',
    'frspec-65k ORIGINAL': '/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf',
}


def tsz(ne, ty):
    bb, bl = GT[ty]
    n = 1
    for d in ne:
        n *= d
    return (n + bl - 1) // bl * bb


for label, p in HEADS.items():
    v, kvs, tens, data = read_gguf(p)
    print(f'\n=== {label}  ({os.path.getsize(p)} bytes, {len(tens)} tensors)')
    tot = 0
    for t in sorted(tens, key=lambda x: -tsz(x['ne'], x['ty'])):
        sz = tsz(t['ne'], t['ty'])
        tot += sz
        if sz > 100_000:
            print(f'  {t["name"]:40s} ty={t["ty"]:3d} ne={str(t["ne"]):18s} {sz/1e6:9.1f} MB')
    print(f'  TOTAL payload: {tot/1e9:.3f} GB')
    # the draft LM head projection
    ow = next((t for t in tens if t['name'] == 'output.weight'), None)
    if ow:
        print(f'  -> draft LM head output.weight: ne={ow["ne"]} ty={ow["ty"]} = {tsz(ow["ne"], ow["ty"])/1e6:.1f} MB per draft step')
    else:
        print('  -> no own output.weight (borrows trunk head)')
    te = next((t for t in tens if t['name'] == 'token_embd.weight' and t['ne'][1] > 1), None)
    if te:
        print(f'  -> token_embd.weight: ne={te["ne"]} = {tsz(te["ne"], te["ty"])/1e9:.3f} GB')
