"""check-flip.py — is the speculative token the SERIAL #2 at the divergence position?

If speculative decode emits, at every divergence, a token that serial ranked as its runner-up
within a tiny margin, the divergence is floating-point reduction-order noise at a near-tie
(handover case c), not a state/layout corruption (case b). This script states that explicitly.

usage: check-flip.py <serial.json> <prompt_tokens> <div_pos> <spec_token>
"""
import json
import sys


def main():
    path, size, div, spec_tok = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    d = json.load(open(path))
    row = next(r for r in d["rows"] if r["requested_prompt_tokens"] == size)
    pr = row["probs"]
    p = pr[div]
    top = sorted(p.items(), key=lambda kv: -float(kv[1]))
    print(f"size={size} div_pos={div} spec_emitted={spec_tok}")
    print(f"  serial top-6 at that position:")
    for i, (tid, lp) in enumerate(top[:6]):
        mark = " <-- SPEC" if int(tid) == spec_tok else (" <-- SERIAL PICK" if i == 0 else "")
        print(f"    #{i+1}: token {int(tid):>7} logprob {float(lp):+.4f}{mark}")
    ranks = {int(tid): i + 1 for i, (tid, _) in enumerate(top)}
    r = ranks.get(spec_tok)
    if r is None:
        print(f"  spec token {spec_tok} NOT in serial top-{len(top)}")
    else:
        gap = float(top[0][1]) - float(top[r - 1][1])
        print(f"  spec token rank in serial = #{r}, logprob gap to serial #1 = {gap:+.4f} nats")


if __name__ == "__main__":
    main()
