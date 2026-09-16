import json
p = r'C:/Projects/REV-N-ornith-eval-20260911/kernel-work/results/lc-lc-mtp.json'
d = json.load(open(p))
print('rows:', len(d['rows']))
for r in d['rows']:
    if 'error' in r:
        print('ERR', r); continue
    dn = r.get('draft_n'); da = r.get('draft_n_accepted')
    acc = f"{100.0*da/dn:.1f}%" if dn else "n/a"
    print(f"  n={r['target_n']:>7} rep={r['rep']} prefill={r['prefill_tps']:.1f} decode={r['decode_tps']:.2f} acc={acc}")
