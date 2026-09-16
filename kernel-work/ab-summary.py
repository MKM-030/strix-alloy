#!/usr/bin/env python3
"""Final A/B summary table: shared vs frspec head, rep1 (clean) decode/prefill + acceptance."""
import glob
import json
import os

base = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'
names = ['ab-shared-n1', 'ab-frspec-n1', 'ab-shared-n2', 'ab-frspec-n2']
print(f'{"run":16s} {"size":>7s} {"pref_r0":>8s} {"pref_r1":>8s} {"dec_r0":>7s} {"dec_r1":>7s} {"acc%":>6s} {"draft":>7s}')
for n in names:
    p = os.path.join(base, n + '.json')
    if not os.path.exists(p):
        print(n, 'MISSING')
        continue
    d = json.load(open(p))
    rows = d['rows']
    for i in range(0, len(rows), 2):
        r0, r1 = rows[i], rows[i + 1]
        acc = 100.0 * r1['draft_n_accepted'] / r1['draft_n'] if r1.get('draft_n') else 0
        print(f'{n:16s} {r1["prompt_n"]:7d} {r0["prefill_tps"]:8.0f} {r1["prefill_tps"]:8.0f} '
              f'{r0["decode_tps"]:7.2f} {r1["decode_tps"]:7.2f} {acc:6.1f} '
              f'{r1["draft_n_accepted"]:3d}/{r1["draft_n"]:<3d}')

print('\n--- rep1 decode deltas (frspec - shared), same n-max ---')
for nmax in ('n1', 'n2'):
    s = json.load(open(os.path.join(base, f'ab-shared-{nmax}.json')))['rows']
    f = json.load(open(os.path.join(base, f'ab-frspec-{nmax}.json')))['rows']
    for i in (1, 3, 5):
        sd, fd = s[i]['decode_tps'], f[i]['decode_tps']
        print(f'  n-max {nmax[1:]}: {s[i]["prompt_n"]:6d}  shared {sd:6.2f}  frspec {fd:6.2f}  '
              f'delta {100*(fd-sd)/sd:+5.1f}%')
