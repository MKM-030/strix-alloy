"""k-split-budget.py — combine the measured real-kernel per-shape rates with the byte census to see
where a decode token's time actually goes, and what a small-R fix would be worth.

Rates are from mmvqbench --1graph (one graph, 32 replicas) at the production shapes.
"""
ceiling = 235.7  # GB/s measured sequential-read ceiling

# shape -> (GB/token, measured GB/s).  GB/token from byte-accounting census; GB/s measured in-vitro.
rows = [
    # name,            bytes/token(GB), measured GB/s, note
    ("attn_q+output",     1.250, 190.0, "R=12288/6144, ~80-85%"),
    ("output head",       0.521, 234.7, "R=248320, 100%"),
    ("hyper-connection",  0.367, 114.0, "R=320/10240, ~47-50%  <-- small-R"),
    ("shared expert",     0.133, 113.1, "R=640, 48%  <-- small-R"),
    ("routed experts",    1.327, 150.0, "MoE path, estimate"),
    ("GDN / ssm",         0.330, 150.0, "estimate"),
    ("norms (F32)",       0.252, 100.0, "mmvf, estimate"),
    ("qsa indexer",       0.039, 100.0, "estimate"),
]

total_gb = sum(r[1] for r in rows)
total_ms = 0.0
print(f"{'component':18s} {'GB':>7s} {'GB/s':>7s} {'ms':>8s}  {'%time':>6s}  note")
for name, gb, rate, note in rows:
    ms = gb / rate * 1000.0
    total_ms += ms
    print(f"{name:18s} {gb:7.3f} {rate:7.1f} {ms:8.2f}  {0:6.1f}  {note}")
print(f"{'TOTAL':18s} {total_gb:7.3f} {'':7s} {total_ms:8.2f}")

# reprint % after total known
print()
per = [(n, gb, rate, gb/rate*1000.0) for n, gb, rate, _ in rows]
for n, gb, rate, ms in per:
    print(f"  {n:18s} {ms:6.2f} ms  {100*ms/total_ms:5.1f}%   at {rate:.0f} GB/s")

meas = 1000.0/29.9
print(f"\npredicted total {total_ms:.2f} ms/token -> {1000/total_ms:.1f} t/s")
print(f"measured serial {meas:.2f} ms/token -> 29.9 t/s")
print(f"unattributed {meas-total_ms:+.2f} ms")

# what if small-R ops (hc, shexp) reached 190 GB/s instead of ~114?
fix_ms = 0.0
print("\n--- if small-R tensors could reach large-R efficiency (190 GB/s) ---")
for n, gb, rate, ms in per:
    if 'small-R' in dict((x[0], x[3]) for x in rows)[n]:
        new = gb/190.0*1000
        fix_ms += (ms - new)
        print(f"  {n:18s} {ms:5.2f} -> {new:5.2f} ms  (saves {ms-new:.2f} ms)")
new_total = total_ms - fix_ms
print(f"  new total {new_total:.2f} ms -> {1000/new_total:.1f} t/s (from {1000/total_ms:.1f})")
