import json, sys
p = r'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'
for tag in ('serial', 'n2', 'n2-nograph'):
    try:
        d = json.load(open(fr'{p}\vwe-{tag}.json'))
    except FileNotFoundError:
        print('====', tag, 'MISSING'); continue
    print('====', tag)
    for row in d['rows']:
        pr = row.get('probs') or []
        print(f"  size={row['requested_prompt_tokens']} n={row['n']} nprobs_len={len(pr)}")
        for i in range(min(5, len(pr))):
            top = sorted(pr[i].items(), key=lambda kv: -float(kv[1]))[:6]
            print(f"    pos{i}: emit={row['tokens'][i]} top={[(int(k), round(float(v),3)) for k, v in top]}")
