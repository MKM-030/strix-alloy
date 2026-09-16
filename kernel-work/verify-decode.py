#!/usr/bin/env python3
"""Ground-truth decode numbers per size/rep for the key A/B JSONs."""
import json

base = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'
for tag in ('ab-shared-n2', 'ab-frspec-n2', 'r-nmax2', 'r-nmax1', 'il-mtp-n2'):
    try:
        d = json.load(open(f'{base}/{tag}.json'))
    except Exception as e:
        print(tag, 'ERR', e)
        continue
    print(f'=== {tag} ===')
    for r in d['rows']:
        acc = f"{r['draft_n_accepted']}/{r['draft_n']}" if r.get('draft_n') else '-'
        print(f"  size={r['prompt_n']:6d} rep={r['rep']} decode={r['decode_tps']:.2f} "
              f"prefill={r['prefill_tps']:.0f} acc={acc}")
