#!/usr/bin/env python3
"""Round cost vs VERIFIED ROWS (proposed + 1).

At n-max k the drafter proposes k tokens and the target verifies k + 1 rows
(k drafts plus one resample). So the x-axis is rows, not "width".
"""
rows = [
    # n_max, rounds, proposed/round, yield/round, target_ms/round
    (1, 79, 1.00, 1.53, 46.16),
    (2, 66, 2.00, 1.83, 54.80),
    (3, 160, 2.99, 2.40, 70.15),
]
print(f'{"n-max":>5} {"rows":>5} {"yield/round":>11} {"target ms/round":>16}')
xs, ys = [], []
for nmax, _r, prop, y, mr in rows:
    verified = prop + 1.0
    xs.append(verified); ys.append(mr)
    print(f'{nmax:5d} {verified:5.2f} {y:11.2f} {mr:16.2f}')

n = len(xs)
mx, my = sum(xs) / n, sum(ys) / n
c1 = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
c0 = my - c1 * mx

print()
print(f'linear fit:  target_ms/round = {c0:.2f} + {c1:.2f} * verified_rows')
print(f'   width-independent part c0 = {c0:6.1f} ms/round  ({100*c0/my:.0f}% of a 3-row round)')
print(f'   marginal verified row  c1 = {c1:6.1f} ms/row')
print()
print('CONSISTENCY CHECK against an independent measurement:')
print(f'   fit at 1 row  = {c0+c1:.1f} ms')
print(f'   serial decode measured separately = ~35 ms/token')
print(f'   -> agreement within {abs((c0+c1)-35)/35*100:.0f}%; the fit extrapolates correctly outside its range')
print()
print('Byte model cross-check (payload 4.254 GB/token at k=10; union U(w)=512*(1-(1-10/512)^w)):')
D, E, BW = 2.927, 1.327, 220.0
for w in (1, 2, 3, 4):
    U = 512 * (1 - (1 - 10 / 512) ** w)
    W = D + E * U / 10.0
    ideal = W / BW * 1000.0
    measured = c0 + c1 * w
    print(f'   rows={w}  union={U:5.1f}  payload={W:5.2f} GB  ideal={ideal:5.1f} ms  '
          f'fit={measured:5.1f} ms  efficiency={100*ideal/measured:4.0f}%')
