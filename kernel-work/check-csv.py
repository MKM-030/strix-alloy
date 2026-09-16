import csv
p = r'C:/Projects/REV-N-ornith-eval-20260911/docs/benchmarks/patch-applicability.csv'
rows = list(csv.reader(open(p, newline='', encoding='utf-8')))
print('total', len(rows), 'widths', sorted(set(len(r) for r in rows)))
for i in (0, 4, 11, 12):
    print('---', i)
    for j, c in enumerate(rows[i]):
        print(f'   {j}: {c}')
