import csv
p = r'C:/Projects/REV-N-ornith-eval-20260911/docs/benchmarks/patch-applicability.csv'
rows = list(csv.reader(open(p, newline='', encoding='utf-8')))
hdr = rows[0]

# Repair S11/S12: the mechanism cell absorbed the applies_to_our_fork value. Split it back so the
# columns keep their headers' meaning.
fix = {
    'S11': ['S11', 'ggml-org/llama.cpp', 'QSA gather sparse attention', 'PR 28213', 'indexer/QSA',
            'gather-based sparse attention for QSA decode', 'UNKNOWN',
            'PARTIAL - we already ship d67d5883 sparse QSA + 0f295019 incremental indexer state',
            'medium', 'medium', 'CHECK whether already covered by d67d5883'],
    'S12': ['S12', 'ggml-org/llama.cpp', 'QSA incremental pooled-key cache', 'PR 28699', 'indexer/QSA',
            'incremental pooled-key cache', 'UNKNOWN',
            'PARTIAL - incremental indexer state is already in d67d5883',
            'medium', 'medium', 'CHECK whether already covered'],
}

out = [hdr]
for r in rows[1:]:
    out.append(fix.get(r[0], r))

# final consistency pass: quote every field so embedded commas can never re-break the file
with open(p, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
    w.writerows(out)

rows2 = list(csv.reader(open(p, newline='', encoding='utf-8')))
print('rows', len(rows2), 'widths', sorted(set(len(r) for r in rows2)))
for r in rows2:
    print(r[0], '|', r[5][:40], '|', r[6])
