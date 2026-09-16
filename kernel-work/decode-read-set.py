experts_total = 67.948e9
# per layer, read the top-10 of 512 experts; across all 48 layers (per token)
tok_experts = (experts_total / 48) * 10 / 512 * 48
tok_attn = 1.250e9
tok_head = 0.521e9
tok_hc = 0.367e9
tok_gdn = 0.330e9
tok_shared = 0.133e9
tok_indexer = 0.039e9
tok_norms = 0.252e9
total = tok_experts + tok_attn + tok_head + tok_hc + tok_gdn + tok_shared + tok_indexer + tok_norms
print("per-token decode read set:")
rows = [("routed experts (top10)", tok_experts), ("attention", tok_attn), ("output head", tok_head),
        ("hyper-connection", tok_hc), ("gdn", tok_gdn), ("shared expert", tok_shared),
        ("qsa indexer", tok_indexer), ("f32 norms", tok_norms)]
for n, v in rows:
    print(f"  {n:24s} {v/1e9:6.3f} GB  {100*v/total:5.1f}%")
print(f"  {'TOTAL':24s} {total/1e9:6.3f} GB")
bw = 235.7e9
ideal = total / bw * 1e3
print(f"ideal at 235.7 GB/s: {ideal:.1f} ms/token")
for meas, label in [(35.0, "serial decode"), (44.0, "target verify (n-max 2)")]:
    print(f"  {label:24s} {meas:5.1f} ms measured -> {100*ideal/meas:.0f}% of peak bandwidth")
# draft phase
draft_step = tok_head + (experts_total/48)*10/512  # borrows target head + own experts
print(f"draft step read ~= {draft_step/1e9:.3f} GB (target output head + own routed experts)")
print(f"  n_max2 -> 2 steps = {2*draft_step/1e9:.3f} GB in ~8.8 ms -> {100*2*draft_step/bw*1e3/8.8:.0f}% of peak")
