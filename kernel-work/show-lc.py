import json
p = r'C:/Projects/REV-N-ornith-eval-20260911/kernel-work/results/lc-lc-prefill.json'
d = json.load(open(p))
print('rows:', len(d['rows']))
for r in d['rows']:
    if 'error' in r:
        print('ERR', r); continue
    print(f"  n={r['target_n']:>7} rep={r['rep']} prefill={r['prefill_tps']:.1f} decode={r['decode_tps']:.2f} prompt_ms={r['prompt_ms']:.0f}")
