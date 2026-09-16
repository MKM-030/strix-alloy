#!/usr/bin/env python3
"""Compute the draft/target step-cost ratio r from the high-repeat sweep.

S_0 = 1 (no MTP). S_k = decode_tps(k) / decode_tps(0) = (1 + A_k) / (k*r + 1).
=> r = ((1 + A_k)/S_k - 1)/k
Use the mean of reps 1..3 (rep0 warmed the page cache but still carries graph-capture cost).
"""
import json
import os

base = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'


def rows(tag):
    return json.load(open(os.path.join(base, tag + '.json')))['rows']


def mean_rep13(rs, size):
    v = [r['decode_tps'] for r in rs if r['prompt_n'] == size and r['rep'] >= 1]
    return sum(v) / len(v)


def acc(r):
    return r['draft_n_accepted'] / r['draft_n']


for size in (1024, 8192):
    S0 = mean_rep13(rows('r-none'), size)
    print(f'\n=== prompt {size}  (no-MTP decode = {S0:.2f} t/s) ===')
    for k, tag in ((1, 'r-nmax1'), (2, 'r-nmax2')):
        rs = rows(tag)
        Sk_tps = mean_rep13(rs, size)
        Sk = Sk_tps / S0
        # acceptance per round A_k: accepted tokens per round = draft_n_accepted / (draft_n/k)
        a = [acc(r) for r in rs if r['prompt_n'] == size and r['rep'] >= 1]
        a_mean = sum(a) / len(a)
        # per-round accepted A_k = k * alpha_k
        A_k = k * a_mean
        r = ((1 + A_k) / Sk - 1) / k
        print(f'  n-max {k}: decode {Sk_tps:5.2f} t/s  S={Sk:.4f}  alpha={a_mean:.3f}  '
              f'A_k={A_k:.3f}  ->  r={r:.3f}')
