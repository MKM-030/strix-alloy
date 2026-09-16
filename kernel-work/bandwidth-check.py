#!/usr/bin/env python3
"""Are we near the memory-bandwidth ceiling? Compute the effective bandwidth at each operating point.

Active weight bytes/token for PROJFIX at k=10 (from the GGUF inventory): 4.61 GB.
Serial decode: weights read once per token.
MTP decode:  weights read once per verify round; the round emits ~1 + accepted tokens,
             so bytes per EMITTED token fall roughly proportionally.
LPDDR5X practical ceiling on this box: 200-240 GB/s (256 theoretical).
"""
ACTIVE = 4.61  # GB per token, PROJFIX, k=10
CEIL_LO, CEIL_HI = 200.0, 240.0

def show(label, tps, bytes_per_emitted):
    bw = tps * bytes_per_emitted
    print(f"{label:34s} decode {tps:5.1f} t/s  x {bytes_per_emitted:4.2f} GB/tok = {bw:6.1f} GB/s "
          f"= {bw/CEIL_LO*100:4.0f}-{bw/CEIL_HI*100:3.0f}% of ceiling")

print("=== serial decode (no speculation) ===")
show("PROJFIX serial @32k", 28.8, ACTIVE)
print(f"    -> implied headroom if we reached the ceiling: {CEIL_LO/ACTIVE:.1f}-{CEIL_HI/ACTIVE:.1f} t/s\n")

print("=== with MTP (n-max 2, ~60% acceptance) ===")
# round: verify ~1+n_max tokens, emit ~1+accepted. weights read once per round.
# per emitted token the share of one full weight sweep is round_tokens/emitted.
draft_tokens, accepted = 3.0, 1.6
emitted = 1.0 + accepted
share = 1.0 / emitted        # one weight sweep per round, spread over emitted tokens
print(f"    verify rows {draft_tokens:.1f}, emitted/round {emitted:.1f} -> weight sweeps per emitted token {share:.2f}")
show("PROJFIX + MTP @32k", 32.9, ACTIVE * share)
print()
print("=== reference: dense attention KV read at depth (is KV a factor?) ===")
kv_bytes_per_tok = 24 * 1024                      # f16, 12 full-attn layers
qs_topk = 2048
print(f"    dense KV would be {kv_bytes_per_tok/1e9*262144:.2f} GB/token at 262k ctx")
print(f"    with QSA top_k={qs_topk} the read is ~{kv_bytes_per_tok*qs_topk/1e9:.4f} GB/token (constant with depth)")
print(f"    -> KV is {kv_bytes_per_tok*qs_topk/(ACTIVE*1e9)*100:.2f}% of the expert weight traffic; not the limiter")
