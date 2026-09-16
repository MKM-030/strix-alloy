#!/usr/bin/env python3
import json

KW = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work'
d = json.load(open(f'{KW}/gguf-inventory-iq4nl.json'))
print('big tensors >500MB:')
for t in d['big_tensors_gt_500MB']:
    print('  ', t)
print('\nby_class:', json.dumps(d.get('by_class'), indent=1))
