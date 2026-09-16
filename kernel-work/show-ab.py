#!/usr/bin/env python3
import glob
import json
import os

base = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'
f = sorted(glob.glob(os.path.join(base, 'ab-*.json')))[0]
d = json.load(open(f))
print('KEYS:', list(d.keys()))
print(json.dumps(d, indent=1)[:2500])
