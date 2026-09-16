#!/usr/bin/env python3
"""Solve for draft-step and target-step time from measured per-round data — no rebuild needed.

For n-max k, each speculative round costs (k*d + t) and yields (1 + A) tokens, where
d = draft step time, t = target step time, A = accepted draft tokens per round.

  R_k = draft_n / k                  (rounds)
  A_k = draft_n_accepted / R_k       (accepted per round)
  predicted_n = 1 + R_k*(1 + A_k)    (the leading 1 is the free first token)
  predicted_ms = R_k*(k*d + t)

Two n-max values give two equations -> solve for d and t directly.
"""
import glob
import json
import os

base = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'


def load(tag):
    return json.load(open(os.path.join(base, tag + '.json')))['rows']


def per_round(rows):
    """map prompt_n -> (R, A, ms, pred_n) using the rep1 (clean) row."""
    out = {}
    k = None
    for r in rows:
        pass
    return out


def solve(head):
    r1 = load(f'ab-{head}-n1')
    r2 = load(f'ab-{head}-n2')
    # pair rep1 rows (index 1,3,5)
    print(f'\n=== {head} head ===')
    print(f'{"size":>6s} {"R1":>6s} {"A1":>6s} {"R2":>6s} {"A2":>6s} {"d_ms":>7s} {"t_ms":>7s} {"r=d/t":>6s}')
    for i in (1, 3, 5):
        a, b = r1[i], r2[i]
        R1 = a['draft_n'] / 1.0
        A1 = a['draft_n_accepted'] / R1
        R2 = b['draft_n'] / 2.0
        A2 = b['draft_n_accepted'] / R2
        ms1, ms2 = a['predicted_ms'], b['predicted_ms']
        d = ms2 / R2 - ms1 / R1
        t = ms1 / R1 - d
        print(f'{a["prompt_n"]:6d} {R1:6.0f} {A1:6.3f} {R2:6.1f} {A2:6.3f} '
              f'{d:7.2f} {t:7.2f} {d/t:6.3f}')
        # sanity
        chk = 1 + R1 * (1 + A1)
        assert abs(chk - a['predicted_n']) < 2, (chk, a['predicted_n'])


for h in ('shared', 'frspec'):
    solve(h)
