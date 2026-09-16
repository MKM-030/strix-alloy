#!/usr/bin/env python3
"""End-to-end request latency: does MTP pay for itself now that ub 16384 works with a draft?"""

def total(cin, cout, prefill, decode):
    return cin / prefill + cout / decode

print("Full-request latency, 32768-token input + 256 generated (seconds)")
print(f"{'config':38s} {'prefill':>8} {'decode':>7} {'total':>8}")
rows = [
    ("no draft, ub 16384 (prefill-best)", 32768, 256, 1035, 28.8),
    ("MTP ub 2048 (old, clang 21 era)",   32768, 256,  767, 32.5),
    ("MTP ub 16384 (new, clang 24)",      32768, 256,  964, 31.1),
]
for label, ci, co, pf, dc in rows:
    t = total(ci, co, pf, dc)
    print(f"{label:38s} {pf:8.0f} {dc:7.1f} {t:8.2f}")

t_nodraft = total(32768, 256, 1035, 28.8)
t_mtp_new = total(32768, 256, 964, 31.1)
print(f"\nMTP(ub16384) vs no-draft: {t_mtp_new:.2f}s vs {t_nodraft:.2f}s "
      f"-> {'BETTER by %.2fs' % (t_nodraft - t_mtp_new) if t_mtp_new < t_nodraft else 'worse'}")

print("\nCrossover (output tokens where MTP breaks even), at each prefill cost:")
for label, pf, dc, pf0, dc0 in (("ub 2048", 767, 32.5, 1035, 28.8), ("ub 16384", 964, 31.1, 1035, 28.8)):
    # C/prefill_mtp + N/decode_mtp = C/prefill0 + N/decode0
    # N (1/dc - 1/dc0) = C(1/pf0 - 1/pf)
    left = 1/dc - 1/dc0
    right = 32768 * (1/pf0 - 1/pf)
    N = right / left
    print(f"  {label}: prefill {pf} vs {pf0}, decode {dc} vs {dc0} -> crossover N = {N:,.0f} tokens"
          f" ({'always wins' if N <= 0 else 'wins for N > this'})")
