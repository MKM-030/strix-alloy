#!/usr/bin/env python3
"""Corrected verification economics — computed ENTIRELY from one clean A/B dataset (r-sweep.json),
which has serial + n-max 1 + n-max 2 at the same sizes with reps 1-3.

Earlier tables mixed a -lv 4 instrumented run's ms/round with a clean run's serial baseline;
that is the arithmetic error this fixes. Phase RATIOS (verify ~80%, draft ~16%) come from the
instrumented run and are robust; THROUGHPUT must come from the clean runs.
"""
import json

BASE = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'


def rows(tag):
    return json.load(open(f'{BASE}/{tag}.json'))['rows']


def clean(tag, size):
    """mean of rep>=1 decode_tps, plus draft/emitted for tokens-per-round."""
    rs = [r for r in rows(tag) if r['prompt_n'] == size and r['rep'] >= 1]
    tps = sum(r['decode_tps'] for r in rs) / len(rs)
    return tps, rs[0]


for size in (1024, 8192):
    print(f'\n================ prompt {size} ================')
    print(f'{"config":16s} {"t/s":>7s} {"ms/tok":>7s} {"rounds":>7s} {"tok/round":>10s} {"gain":>7s}')
    base = None
    for tag, nmax, label in (('r-none','-','serial'), ('r-nmax1','1','n-max 1'), ('r-nmax2','2','n-max 2')):
        tps, r = clean(tag, size)
        ms_per_tok = 1000.0 / tps
        if nmax == '-':
            base = ms_per_tok
            print(f'{label:16s} {tps:7.2f} {ms_per_tok:7.2f} {"-":>7s} {"1.00":>10s} {"-":>7s}')
        else:
            k = int(nmax)
            rounds = r['draft_n'] / k
            tok_per_round = r['predicted_n'] / rounds
            gain = base / ms_per_tok - 1.0
            print(f'{label:16s} {tps:7.2f} {ms_per_tok:7.2f} {rounds:7.0f} {tok_per_round:10.2f} {gain:+6.1%}')

print('\n--- marginal row: n-max 1 -> n-max 2 (clean, 8192) ---')
t1, r1 = clean('r-nmax1', 8192)
t2, r2 = clean('r-nmax2', 8192)
ts, _  = clean('r-none', 8192)
ms1 = 1000.0 / t1; ms2 = 1000.0 / t2; mss = 1000.0 / ts
tok1 = r1['predicted_n'] / r1['draft_n']
tok2 = r2['predicted_n'] / (r2['draft_n'] / 2.0)
print(f'  tokens/round {tok1:.2f} -> {tok2:.2f}  (+{tok2-tok1:.2f})')
print(f'  ms/token     {ms1:.2f} -> {ms2:.2f}')
print(f'  serial       {mss:.2f} ms/token')
print(f'  => at 8k, deeper drafting is NET NEGATIVE ({ms2:.2f} vs {ms1:.2f} ms/token)')
