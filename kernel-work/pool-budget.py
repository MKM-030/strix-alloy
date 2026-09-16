#!/usr/bin/env python3
"""Device-pool budget model for PROJFIX on the current 32 GB carve."""
POOL = 81739 / 1024.0          # MiB -> GiB visible pool
WEIGHTS = 93.16 - 26.82        # PROJFIX minus non-resident PLE table
print(f"pool          {POOL:8.2f} GiB")
print(f"weights(res)  {WEIGHTS:8.2f} GiB")
print(f"left for KV+compute+buffers: {POOL - WEIGHTS:8.2f} GiB\n")

def kv_gib(ctx):
    # 12 full-attn layers, 2 KV heads, head_dim 256, f16, k+v
    return 12 * 2 * 256 * 2 * 2 * ctx / 2**30

def gdn_gib():
    # 36 layers, state 128 x inner 6144 f32 + conv cache
    return (36 * 6144 * 128 * 4) / 2**30

for ctx in (32768, 49152, 65536, 131072):
    rem = POOL - WEIGHTS - kv_gib(ctx) - gdn_gib()
    print(f"ctx={ctx:>7}: KV {kv_gib(ctx):5.2f} + GDN {gdn_gib():4.2f} -> compute budget {rem:6.2f} GiB")
    # measured: ub16384 needed 14.05 GiB
    for ub in (4096, 8192, 12288, 16384):
        need = 14.05 * ub / 16384
        print(f"     ub={ub:>6}: ~{need:5.2f} GiB  {'OK' if need < rem else 'FAIL'}")
