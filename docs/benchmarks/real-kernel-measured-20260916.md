# The real `mul_mat_vec_q`, measured: per-call overhead is a harness artifact; small-R ops are the real inefficiency (2026-09-16)

Codex's instruction was explicit: *"Benchmark the actual production operator unchanged, then locate the
difference before changing its decomposition."* Done — and it produced the first measurement of this
session that is **not** a surrogate.

## What was built

`kernel-work/mmvqbench.cpp` — drives ggml's **real** `MUL_MAT` path through the public backend API
(`ggml_backend_graph_compute` on an `IQ4_NL` weight). Nothing is reimplemented: activation quantization
(`quantize_row_q8_1_cuda`), the actual `mul_mat_vec_q` kernel, and the real epilogue all run as
production runs them. Per Codex: preparation is outside timing, output is checked for finiteness and
scale, and the working set is enlarged by **rotating independent replicas of the same shape** (not by
changing R/K), so kernel geometry is unchanged.

Two timing modes: **separate** `graph_compute` per op, and **`--1graph`** (all replicas' `MUL_MAT`s in
one graph — production-like, since production runs one hip graph per decode step).

## Finding 1 — the ~40 µs "per-op cost" is `graph_compute` overhead, NOT the kernel

Same kernel, same shape (K=10240, R=256), 64 ops:

| mode | ms/op | GB/s |
| --- | ---: | ---: |
| 64 separate `graph_compute` calls | 0.048 | 31 |
| **64 `MUL_MAT`s in ONE graph** | **0.016** | **94** |

**3× faster in one graph.** So the fixed ~32–40 µs is per-`graph_compute` (host/launch), and production
— which submits one graph per decode step — **pays it once per step, not once per op**. This kills the
"150 ops × 40 µs = 6 ms" hypothesis before it could be claimed. It also independently re-confirms why
HIP graphs matter so much here (35 vs 10.7 t/s measured earlier).

**Scope correction (Codex was right to insist):** my earlier numbers mixed per-call overhead into
"kernel cost". From here on, only `--1graph` numbers are used.

## Finding 2 — the real kernel is at 80–100% for large R, and ~41–50% for small R

`--1graph`, 32 replicas, at the actual production shapes:

| tensor | K | R | measured GB/s | % of 235.7 ceiling |
| --- | ---: | ---: | ---: | ---: |
| **lm_head / output** | 2560 | 248,320 | **234.7** | **100%** |
| attn_q | 2560 | 12,288 | 199.8 | 85% |
| attn_output | 2560 | 6,144 | 189.2 | 80% |
| hc_up | 320 | 10,240 | 117.9 | 50% |
| **shexp** (shared expert) | 2560 | 640 | 113.1 | 48% |
| hc_down | 10,240 | 320 | 110.2 | 47% |
| **router** (`ffn_gate_inp`) | 2560 | 512 | 96.8 | 41% |

**The inefficiency tracks R (output rows = parallel blocks), not K.** Holding K=10240 and varying R:
R=4, 128, 512 all take ~0.041–0.045 ms (a floor), while R=2560 → 0.115 ms and R=10240 → 0.318 ms. So
small-R shapes are **parallelism-starved**: a few hundred single-warp blocks on 40 CUs cannot saturate
the memory system, regardless of how much K they stream.

This is the opposite of my earlier (now-retracted) "short loops are bad" reading, and it matches what
Codex said about the two distinct deficiencies: insufficient parallelism vs inefficient execution of
abundant tasks.

## Finding 3 — what the inefficiency is worth (bounded, honestly)

Combining measured per-shape rates with the exact byte census:

| component | GB/token | GB/s | ms/token | share |
| --- | ---: | ---: | ---: | ---: |
| routed experts (MoE path, *estimated*) | 1.327 | ~150 | 8.85 | 33% |
| attn_q + attn_output | 1.250 | 190 | 6.58 | 24% |
| hyper-connection | 0.367 | 114 | 3.22 | 12% |
| norms (F32, *estimated*) | 0.252 | ~100 | 2.52 | 9% |
| output head | 0.521 | 235 | 2.22 | 8% |
| GDN/ssm (*estimated*) | 0.330 | ~150 | 2.20 | 8% |
| shared expert | 0.133 | 113 | 1.18 | 4% |
| qsa indexer (*estimated*) | 0.039 | ~100 | 0.39 | 1% |
| **total** | 4.219 | | **27.15** | |

Predicted **36.8 t/s** vs measured **29.9** → **6.3 ms/token unattributed**, and the weakest numbers are
the *estimated* rows (MoE and the unmeasured ops), not the measured ones.

**If the small-R tensors reached large-R efficiency (190 GB/s), the fix is worth ~1.8 ms/token ≈ 5% of
decode.** That is squarely inside Codex's "budget 0–5% from the first bounded implementation" — so it is
a real but modest target, **not** the 1.5× once hoped for.

## Finding 4 — cross-warp reduction is closed (per Codex §1)

My own coverage log shows `nwarps = 1` for every executed MMVQ specialisation on gfx1151, so there is no
cross-warp reduction to remove. Codex's three-way distinction is correct: the generic MMVQ has
`nwarps-1`-dependent accumulation (inactive at `nwarps=1`), the multi-token MoE kernel gives each token
its own warp with *no* shared reduction, and `mul_mat_vec_f` is a different family. **Hypothesis
closed.**

## What is now the justified change — CORRECTED: fewer/bigger ops, NOT K-split

> **Correction (same day, after two follow-up measurements).** The section below originally named
> "K-split for small-R" as the candidate. **That is wrong and I retract it.** Two measurements:
>
> **(a) T=1/2/3 does not change small-R efficiency.** At T=3 the same weights are read for 3 rows;
> small-R GB/s is unchanged (router 95.4 → 92.4, hc_down 108.0 → 101.0). So this is not a verify-width
> effect, and T=3 already amortizes weight reads for free (attn_output: 0.046 ms at T=1 vs 0.049 ms at
> T=3 for **3×** the output work).
>
> **(b) The cost is per-OP, not per-block.** Holding total bytes AND total blocks fixed at 3.32 MB /
> 4096 blocks:
>
> | decomposition | total ms | GB/s | recomputed from 3.32 MB |
> | --- | ---: | ---: | ---: |
> | 1 op, R=4096 | **0.034** | **172.5** | **97.6** |
> | 8 ops, R=512 | 0.064 | 51.9 | 51.9 ✓ |
> | 16 ops, R=256 | 0.112 | 29.6 | 29.6 ✓ |
>
> **Arithmetic correction, flagged by external review.** Rows 2 and 3 are exactly consistent with a fixed
> 3.32 MB total (3.32e6/0.064e-3 = 51.9 GB/s; /0.112e-3 = 29.6 GB/s). Row 1 is not: 3.32 MB over 0.034 ms is
> **97.6 GB/s, not 172.5**. Either that row's byte count, its time, or the printed rate is wrong, and I no
> longer hold the raw output to tell which — 172.5 GB/s over 0.034 ms implies 5.86 MB, and the harness computes
> `w_bytes = K*R*18/32` per op, so a per-op-vs-total mix-up in that single row is the likely cause. **Treat
> row 1's rate as unverified.**
>
> The conclusion is robust to the correction: even at 97.6 GB/s, one op of R=4096 still beats 8 ops of R=512
> (51.9) and 16 ops of R=256 (29.6), and that ordering is what the argument rests on — and rows 2 and 3, which
> carry the ordering, are internally consistent.
>
> Identical block count, 1.8× and 3.3× slowdown purely from splitting into more kernels. So each
> `MUL_MAT` pays a **~5 µs GPU-side ramp that amortizes only within its own kernel** — a linear fit over
> R=256…8192 gives **≈5.4 µs fixed + ~133 GB/s marginal**. **K-split adds kernels, so it would make this
> worse.** `rpb` (which cut block count within one kernel) was correctly negative for the same reason:
> it did not change the number of kernels.
>
> **The correct lever is fewer, larger `MUL_MAT` kernels** — i.e. batching independent projections that
> share a K dimension into one op (Codex §6, "grouped independent matrix execution"). The one such fusion
> that already exists in this fork, `pack_di` in `build_hc_mix` (which concatenates `w_down`+`w_inject`
> into one matmul), is gated `nt >= 128` — **prefill only** — and is off during decode, where the
> per-call `ggml_concat` would cost more than it saves unless the concatenated weights are prepared once
> at load.
>
> **Bounded estimate:** ~576 small-R ops/token × ~5 µs ≈ **2–3 ms/token**, against ~33.4 ms measured
> serial — so **~6%**, addressable only by graph-level batching, not by a kernel-parameter change.

### (original, now-superseded candidate list)

| candidate | targets | basis | status |
| --- | --- | --- | --- |
| K-split for R < ~1024, K ≥ 2560 | router, shexp, hc_down | measured 41–48% vs 80–100% at high R | **RETRACTED** — cause is per-op ramp; K-split adds ops |
| **Batch independent same-K projections into one `MUL_MAT`** | all small-R ops | matches the measured per-op cost; Codex §6 | **the candidate** |
| Remove the unconditional `__syncthreads()` in the `nwarps==1` epilogue | all MMVQ ops | dead code at `nwarps=1` per source | cheapest; must be verified in compiled code first |

The third is the cheapest and is pure dead-code removal at `nwarps == 1` (a compile-time constant), but
Codex is right that a visible barrier is not evidence of cost — it must be measured, and only if the
compiler actually emits it.

## Method notes retained

- Only `--1graph` numbers describe the kernel; separate-call numbers describe the runtime.
- Rotate replicas, never change R/K, to enlarge the working set.
- Check `ggml_backend_dev_type` against this fork's extra `IGPU` enum value (device reports `type=2`).

## Model-level result after this work (no kernel change shipped)

I did **not** ship a kernel change in this pass — the measurement identified a candidate but did not
justify shipping it blind, and Codex's sequence requires the change to be validated in the real
operator first. So the model numbers are a **regression check** that the clean build still behaves as
before (`results/lc-post-kernel.*`, prefill shape `-ub 16384`, `-c 262144`, warm reps):

| depth | prefill t/s (before kernel work) | **prefill t/s (after)** | Δ | decode t/s (after) |
| ---: | ---: | ---: | ---: | ---: |
| 16,384 | 1030 | **1031** | 0% | 28.3 |
| 65,536 | 990 | **993** | +0.3% | 27.8 |
| 131,072 | 924 | **925** | 0% | 26.9 |
| 196,608 | 856 | **859** | +0.4% | 26.0 |
| 251,904 | 811 | **812** | 0% | 25.1 |

**All within noise — unchanged, as expected.** Serial decode is 28.3 → 25.1 t/s across the range, and
prefill 1031 → 812 t/s. MTP decode is a separate ladder (previous run: 31.2/32.6/32.8/31.0 t/s) and is
unaffected by this pass, since no kernel change was shipped.

## Artifacts

`kernel-work/mmvqbench.cpp` (+ `.exe`), `kernel-work/k-split-budget.py`. Repro:
`mmvqbench.exe <K> <R> <T> <replicas> <iters> [--1graph]`.
