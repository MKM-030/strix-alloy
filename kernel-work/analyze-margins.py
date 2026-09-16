"""analyze-margins.py — is the serial/verify divergence explained by near-tie margins?

For each serial arm run we have top-N logprobs at every generated position. A token-flip under a
tiny logit perturbation can only happen where the top-1 and top-2 logprobs are close. If every
observed divergence sits at a small top1-top2 margin, the divergence is consistent with
FP-reduction-order noise (handover case c) rather than a state/layout bug (case b).

usage: analyze-margins.py <serial.json> [divergence_positions ...]
"""
import json
import sys


def main():
    path = sys.argv[1]
    div_positions = [int(x) for x in sys.argv[2:]]
    d = json.load(open(path))
    for row in d["rows"]:
        print(f"== size={row['requested_prompt_tokens']} n={row['n']}")
        pr = row.get("probs") or []
        margins = []
        for i, p in enumerate(pr):
            if not p:
                margins.append((i, None, None, None))
                continue
            top = sorted(p.items(), key=lambda kv: -float(kv[1]))
            if len(top) < 2:
                margins.append((i, None, None, None))
                continue
            m = float(top[0][1]) - float(top[1][1])
            margins.append((i, m, int(top[0][0]), int(top[1][0])))
        ok = [m for (_, m, _, _) in margins if m is not None]
        if ok:
            ok_sorted = sorted(ok)
            print(f"   margins: n={len(ok)} min={ok_sorted[0]:.4f} "
                  f"p10={ok_sorted[len(ok_sorted)//10]:.4f} median={ok_sorted[len(ok_sorted)//2]:.4f} "
                  f"max={ok_sorted[-1]:.4f}")
            # rank of each divergence position within the margin distribution
            for dp in div_positions:
                if dp < len(margins) and margins[dp][1] is not None:
                    m = margins[dp][1]
                    rank = sum(1 for x in ok if x < m)
                    pct = 100.0 * rank / max(1, len(ok))
                    print(f"   pos {dp}: margin={m:.4f}  rank={rank}/{len(ok)} "
                          f"(smaller than {pct:.1f}% of positions) top1={margins[dp][2]} top2={margins[dp][3]}")
        # smallest 5 margins with their positions
        small = sorted([(m, i) for (i, m, _, _) in margins if m is not None])[:5]
        print(f"   smallest margins: {[(round(m,4), i) for m, i in small]}")


if __name__ == "__main__":
    main()
