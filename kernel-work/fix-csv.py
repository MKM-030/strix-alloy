import csv
p = r'C:/Projects/REV-N-ornith-eval-20260911/docs/benchmarks/patch-applicability.csv'
rows = list(csv.reader(open(p, newline='', encoding='utf-8')))
hdr = rows[0]
w = len(hdr)
print('rows', len(rows), 'header width', w)
bad = [(i, r) for i, r in enumerate(rows) if len(r) != w]
print('bad rows:', len(bad))
for i, r in bad:
    print(' idx', i, 'width', len(r), ':', r)

# repair: the offending rows have exactly one extra column; the mechanism field (index 5) is the
# one that gained a comma. Re-join everything between 5 and the tail so widths match the header.
fixed = [hdr]
for i, r in enumerate(rows[1:], start=1):
    if len(r) == w:
        fixed.append(r)
        continue
    extra = len(r) - w
    # keep fields 0..4, merge the next (1+extra) fields into the mechanism cell, keep the tail
    head = r[:5]
    mech = ','.join(r[5:5 + 1 + extra])
    tail = r[5 + 1 + extra:]
    fixed.append(head + [mech] + tail)

print('fixed widths', sorted(set(len(r) for r in fixed)))
with open(p, 'w', newline='', encoding='utf-8') as f:
    csv.writer(f).writerows(fixed)
print('rewrote', p)
