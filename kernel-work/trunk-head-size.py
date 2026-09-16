#!/usr/bin/env python3
"""Trunk output.weight + token_embd size for PROJFIX (IQ4_NL), to complete the draft census."""
import json

KW = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work'
for name in ('gguf-inventory-iq4nl.json', 'gguf-inventory-udiq4xs.json'):
    try:
        d = json.load(open(f'{KW}/{name}'))
    except Exception as e:
        print(name, 'ERR', e)
        continue
    print(f'=== {name}: keys={list(d.keys())[:10] if isinstance(d, dict) else "list"}')
    tens = d.get('tensors') if isinstance(d, dict) else None
    if tens is None:
        continue
    for t in tens:
        if t.get('name') in ('output.weight', 'token_embd.weight'):
            print('  ', t)
