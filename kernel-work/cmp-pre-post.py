import json, os
R = r'C:/Projects/REV-N-ornith-eval-20260911/kernel-work/results'

def rows(name):
    p = os.path.join(R, name)
    if not os.path.exists(p):
        return None
    return json.load(open(p))['rows']

def best_by_size(rs, key, rep_min=1):
    out = {}
    for r in rs or []:
        if 'error' in r: continue
        n = r['target_n']
        if r.get('rep', 0) >= rep_min and r.get(key):
            out.setdefault(n, []).append(r[key])
    return {n: max(v) for n, v in out.items()}

print("=== PRE-CHANGE ===")
pre = rows('lc-lc-prefill.json')
mtp_pre = rows('lc-lc-mtp-g256.json')
cap_pre = rows('cap-262144.json')
print("prefill (lc-lc-prefill, max of reps>0):", best_by_size(pre, 'prefill_tps'))
print("prefill cap-262144 (4 reps):", best_by_size(cap_pre, 'prefill_tps'))
print("mtp decode (lc-mtp-g256):", best_by_size(mtp_pre, 'decode_tps'))

print("\n=== POST-CHANGE ===")
post = rows('lc-post-prefill.json')
print("prefill (post-prefill):", best_by_size(post, 'prefill_tps'))
