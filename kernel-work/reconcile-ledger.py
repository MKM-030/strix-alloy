#!/usr/bin/env python3
"""Reconcile the MEASURED draft/accept timers against the fitted r-model.

Trace line (cumulative over the server's lifetime):
  #calls(b,g,a) = 1  67  67      begin/draft/accept call counts
  #gen tokens = 134, #acc tokens = 53       (67 calls x n-max 2)
  dur(b,g,a)  = 0.004, 738.044, 0.354 ms
"""
import json

base = '/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results'
d = json.load(open(f'{base}/rl-n2.json'))
r = d['rows'][0]
wall_ms = r['predicted_ms']
n_tok   = r['predicted_n']

# first task: calls=67, dur totals
calls      = 67
draft_ms   = 738.044
accept_ms  = 0.354
accepted   = 53

print(f'generated {n_tok} tokens in {wall_ms:.0f} ms  -> {1000*n_tok/wall_ms:.2f} t/s')
print(f'draft calls (rounds) = {calls}')
print(f'draft total   = {draft_ms:8.1f} ms = {100*draft_ms/wall_ms:5.1f}% of decode wall')
print(f'accept total  = {accept_ms:8.3f} ms = {100*accept_ms/wall_ms:5.2f}%')
resid = wall_ms - draft_ms - accept_ms
print(f'residual      = {resid:8.1f} ms = {100*resid/wall_ms:5.1f}%  (target verify + host)')
print()
print(f'per round: draft {draft_ms/calls:.2f} ms, accept {accept_ms/calls:.4f} ms, '
      f'residual {resid/calls:.2f} ms, total {wall_ms/calls:.2f} ms')
print(f'tokens/round = {n_tok/calls:.2f}   accepted/round = {accepted/calls:.2f}  (mean acc len {1+accepted/calls:.2f})')
print()
print('=> measured draft:residual ratio = '
      f'{(draft_ms/calls)/(resid/calls):.3f}  (my fitted r was 0.47)')
