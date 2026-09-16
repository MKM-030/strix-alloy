#!/usr/bin/env python3
"""Read indexer/attention head counts from the PROJFIX GGUF to test the 4x-width hypothesis."""
import os
import struct
import sys

KW = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work'
sys.path.insert(0, KW)
src = open(os.path.join(KW, 'd2t-inspect.py')).read()
exec(src.split('def main')[0])

P = '/mnt/c/AI/models/qwen38-flash/projfix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
v, kvs, tens, data = read_gguf(P)

print('=== indexer / attention keys ===')
for k, t, val in kvs:
    if any(s in k.lower() for s in ('indexer', 'head_count', 'head_size', 'attention.key_length', 'attention.value_length')):
        print(f'  {k} = {val}')

print()
print('=== indexer tensors (shape reveals head count) ===')
for t in tens:
    if 'indexer' in t['name']:
        print(f"  {t['name']:42s} ne={t['ne']} ty={t['ty']}")
