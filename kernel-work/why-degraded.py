#!/usr/bin/env python3
"""Why PROJFIX decode collapses at the 64 GB carve but UD does not.

Measured facts (native Windows, clang 24 build, same flags):
  64 GB carve (pool 95.8 GiB, 93.2 free):
    UD-IQ4_XS (60.4 GiB resident) -> prefill 982-1000 t/s, decode 23.0 t/s   OK
    PROJFIX   (66.3 GiB resident) -> prefill  875-894 t/s, decode  6.1 t/s   DEGRADED
  96 GB carve (pool 111.8 GiB):
    PROJFIX                        -> prefill 998-1035 t/s, decode 28.8 t/s  OK
"""
POOL = {"64GB carve": 95.8, "96GB carve": 111.8}
W = {"UD-IQ4_XS": 60.4, "PROJFIX": 66.3}
KV = 1.13   # ctx 49152, f16
print(f"{'carve':>12} {'pool':>7} {'weights':>9} {'KV':>5} {'free':>7}  result")
for carve, pool in POOL.items():
    for q, w in W.items():
        free = pool - w - KV
        measured = {
            ("64GB carve", "UD-IQ4_XS"): "decode 23.0 OK",
            ("64GB carve", "PROJFIX"):   "decode  6.1 DEGRADED",
            ("96GB carve", "PROJFIX"):   "decode 28.8 OK",
        }.get((carve, q), "-")
        print(f"{carve:>12} {pool:>7.1f} {w:>9.1f} {KV:>5.2f} {free:>7.1f}  {q}: {measured}")
print()
print("Observations that narrow the cause:")
print(" * 64GB + PROJFIX: 95.8 - 66.3 - 1.13 = 28.4 GiB free  -> DEGRADED")
print(" * 64GB + UD     : 95.8 - 60.4 - 1.13 = 34.3 GiB free  -> OK")
print(" * 96GB + PROJFIX: 111.8 - 66.3 - 1.13 = 44.4 GiB free -> OK")
print()
print("So the failure correlates with ~28 GiB free, not with PROJFIX per se.")
print("The model still LOADS (prefill is 90% of its 96GB-carve speed); only the DECODE path")
print("collapses 4.7x. That is the signature of per-step memory traffic falling off the")
print("fast path - consistent with the decode-time weight streaming not being fully resident,")
print("so every generated token re-reads weights the pool could not hold.")
print()
print("Working configurations (measured):")
print("  prefill-best : 96 GB carve + PROJFIX + ub16384      -> 1035-1057 t/s")
print("  decode-best  : 96 GB carve + PROJFIX + MTP          -> 33.7 t/s")
print("  at 64 GB     : UD-IQ4_XS                            -> 1000 prefill / 23 decode")
