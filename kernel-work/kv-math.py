#!/usr/bin/env python3
"""KV / state arithmetic for Qwen3.8-Flash-Next (12 full-attn layers of 48; QSA sparse)."""
L_ATTN = 12          # full-attention layers (every 4th of 48)
KV_HEADS = 2
HEAD_DIM = 256
BYTES_F16 = 2
per_tok = L_ATTN * 2 * KV_HEADS * HEAD_DIM * BYTES_F16
print(f"KV f16 bytes/token = {per_tok} = {per_tok/1024:.1f} KiB")
for ctx in (8192, 49152, 131072, 262144):
    gib = per_tok * ctx / 2**30
    print(f"  ctx {ctx:>7}: KV total = {gib:6.2f} GiB")
print()
# QSA sparse: only top_k=2048 positions selected out of ctx -> read fraction
for ctx in (49152, 131072, 262144):
    frac = 2048 / ctx
    gib = per_tok * ctx / 2**30
    print(f"  ctx {ctx:>7}: QSA reads ~{frac*100:5.2f}% of KV = {gib*frac*1000:7.1f} MiB/token")
print()
# handoff cost: moving KV+state between backends at 200 GB/s
for ctx in (32768, 131072):
    gib = per_tok * ctx / 2**30 + 0.106   # + GDN state
    print(f"handoff @ctx {ctx:>7}: {gib:5.2f} GiB -> {gib/200*1000:5.1f} ms at 200 GB/s")
print()
# two concurrent engines: resident weights
print("two concurrent engines (same UD file), resident each:")
for name, res in (("UD-IQ4_XS", 60.4), ("PROJFIX", 66.34)):
    print(f"  {name}: {res} GiB each -> {2*res:.1f} GiB for two")
print("  (128 GB total; pool at 32 GB carve = 79.8 GiB, at 96 GB carve ~ 112 GiB)")
print()
# TurboQuant benefit for OUR model (KV is small because only 12/48 layers are full-attn)
kv262 = per_tok * 262144 / 2**30
print(f"TurboQuant on our model: KV@262k {kv262:.2f} GiB -> ~{kv262*0.33:.2f} GiB (saves ~{kv262*0.67:.2f} GiB)")
print("  (q38rocm's 61.4->20.08 GB figure is for a DENSE 27B with full attention on every layer)")
