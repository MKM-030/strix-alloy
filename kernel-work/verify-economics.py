#!/usr/bin/env python3
"""Economics of verification: what does each extra verified row actually buy?

Measured phase timer (target verify = enqueue + sync, generation-gated):
  n-max 1: 46.30 ms/round, 2 rows verified, 1.52 tokens emitted
  n-max 2: 57.19 ms/round, 3 rows verified, 1.82 tokens emitted
Serial baseline: 28.6 t/s = 34.97 ms/token
"""
serial_ms_per_token = 1000.0 / 28.6

cases = {
    'serial      (1 row)':  (34.97, 1.00),
    'mtp n-max 1 (2 rows)': (46.30, 1.52),
    'mtp n-max 2 (3 rows)': (57.19, 1.82),
}
print(f'{"config":24s} {"ms/round":>9s} {"rows":>5s} {"tok/round":>10s} {"ms/token":>9s} {"vs serial":>10s}')
rows = {'serial      (1 row)': 1, 'mtp n-max 1 (2 rows)': 2, 'mtp n-max 2 (3 rows)': 3}
for k, (ms, toks) in cases.items():
    per = ms / toks
    print(f'{k:24s} {ms:9.2f} {rows[k]:5d} {toks:10.2f} {per:9.2f} {100*(serial_ms_per_token/per-1):9.1f}%')

print()
print('--- marginal cost of an extra verified row ---')
# n-max1 -> n-max2 adds one row and 0.30 tokens
d_ms  = 57.19 - 46.30
d_tok = 1.82 - 1.52
print(f'  +1 row costs   +{d_ms:.2f} ms/round')
print(f'  +1 row yields  +{d_tok:.2f} tokens/round')
print(f'  marginal       {d_ms/d_tok:.1f} ms per extra accepted token')
print(f'  serial bench    {serial_ms_per_token:.1f} ms per token')
print()
print('--- what a 1-row verify would cost (ideal amortization) ---')
print(f'  if verify scaled perfectly linearly: 2 rows = {2*34.97:.1f} ms, 3 rows = {3*34.97:.1f} ms')
print(f'  measured 2 rows = 46.30 ms ({(46.30/(2*34.97)-1)*100:+.0f}% overhead vs linear)')
print(f'  measured 3 rows = 57.19 ms ({(57.19/(3*34.97)-1)*100:+.0f}% vs linear)')
print()
print('  => verification DOES amortize (rows 2-3 cost less than 2-3 full passes),')
print('     but not enough to beat single-token decoding once acceptances are ~50%.')
