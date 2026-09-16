# Where a decode step's bytes actually go — and why the loss is uniform (2026-09-15)

This is the build-out of the "explain the ~23 ms/round not covered by expert bytes" item. It replaces
the earlier rough payload estimate with an exact GGUF byte census, and it **redirects kernel work**:
the shortfall is not in experts, attention or hyper-connections — it is a uniform quantized-matvec
efficiency loss.

## Method

`kernel-work/byte-accounting.py` sums exact per-tensor bytes from the GGUF type block layout across all
nine PROJFIX shards. `dump-non-expert-tensors.py` lists the non-expert tensors individually.

## The read set of one decode token

| component | bytes/token | share |
| --- | ---: | ---: |
| routed experts (top-10 of 512, ×48 layers) | 1.327 GB | 31.5% |
| attention (qkv / q / k / v / output / gate) | 1.250 GB | 29.6% |
| output head (`output.weight` Q6_K) | 0.521 GB | 12.3% |
| hyper-connection (down/up ×4, norm, inject) | 0.367 GB | 8.7% |
| GDN / linear-attention (ssm_out, alpha, beta, conv) | 0.330 GB | 7.8% |
| shared expert (gate/up/down) | 0.133 GB | 3.2% |
| F32 norms (incl. the MoE router `ffn_gate_inp`) | 0.252 GB | 6.0% |
| QSA indexer (q_proj, k_proj, norms) | 0.039 GB | 0.9% |
| **total** | **4.219 GB** | 100% |

(`token_embd.weight`, 358 MB, is *not* in the read set: at decode it is a single-row gather, not a
matmul. `per_layer_token_embd` — the 28.8 GB PLE table — is disk-backed and only the used rows are read.)

## What the numbers mean

- **Ideal** at our measured sequential-read ceiling (235.7 GB/s): `4.219 GB / 235.7 = 17.9 ms/token`
  → **~56 t/s**. That is the hard ceiling for serial decode on this box.
- **Measured** serial decode is **35 t/s (28.6 ms)** → **63% of the ceiling**.
- Earlier work measured byte efficiency as **flat 53–59% across every decode width** and found round
  cost **flat (54–59 ms) across a 16× context span**. Those two facts plus this census say the same
  thing from three directions: **the loss is uniform, not concentrated in any one component.**

This is consistent with the expert ablation (`target_ms/round = 35.4 + 3.56 × expert_GB`; experts
≤ 28% of the round). The census independently puts experts at 31.5% of bytes, so the ablation's
"~23 ms not explained by expert bytes" is exactly the dense 68% of the read set — attention, head, HC,
GDN, norms — and it is bandwidth-bound at the same ~60% efficiency as everything else.

## Consequence for kernel work (this is the actionable part)

1. **Do not chase experts, attention depth, or the QSA indexer for decode throughput.** They are at
   most ~1/3 of bytes each and the per-byte cost is the same as everywhere else. The earlier closures
   (indexer depth line, PLE staging) are confirmed from the byte side.
2. **The lever is the quantized matvec kernel efficiency itself** (the fork's MMB IQ4_NL fast path and
   `mmvq`), which covers the whole 4.22 GB read set. A 63% → 80% efficiency move would be worth ~25%
   decode; that is the single biggest available win and it is a *kernel* problem, not a routing or
   scheduling one.
3. **The one genuinely MMVF-eligible hot tensor is the MoE router** `blk.*.ffn_gate_inp.weight`
   (F32 [2560,512], 251 MB/token, 6% of bytes) — read every token, and exactly the "512-row router"
   shape the halo-box `mmvf.cu` prefetch targets. But at 6% of bytes its ceiling is small; treat it as
   a cheap test of the prefetch idea, not a throughput fix.
4. **Two tensors are Q6_K** (`output.weight` 521 MB, `blk.*.attn_output.weight` 155 MB). Q6_K matmul
   in this fork historically needed a **bf16 shadow** (commit `f5daaa3c`). If any shadow is re-read or
   re-materialised per token, that is real *extra* traffic on 676 MB/token — worth a targeted check
   before writing new kernels, because it would be a correctness/traffic bug rather than a tuning miss.

## Caveat

The 235.7 GB/s ceiling is a HIP streaming microbenchmark (`bwtest.hip`), not a matvec. A GEMV reading a
matrix and a vector should approach it, but the achieved-vs-ceiling ratio mixes kernel efficiency with
memory-controller behaviour under the mixed access pattern of ~150 small matvecs per layer. The claim
here is the *distribution* of bytes and the *uniformity* of the loss; the exact ceiling is not the point.

## Artifacts

`kernel-work/byte-accounting.py`, `dump-non-expert-tensors.py`, `decode-read-set.py`;
raw census output in this doc.
