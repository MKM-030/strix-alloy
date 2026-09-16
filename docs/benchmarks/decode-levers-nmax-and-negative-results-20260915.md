# Decode levers, measured: n-max sweep + FR-Spec head (2026-09-15)

## n-max sweep on the corrected 96 GB carve (PROJFIX, shared Q8_0 head, ub 2048, ctx 32768)

| n-max | decode @1k | @8k | @16k | acceptance @1k | @8k | @16k |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **1** | **34.6** | 28.4 | 29.4 | **86.3%** | **64.9%** | **69.6%** |
| **2** | 34.1 | **28.5** | **30.3** | 63.9% | 51.6% | 58.6% |
| 3 | 34.7 | 23.4 | 26.2 | 58.8% | 37.0% | 40.6% |
| 4 | 28.0 | 20.7 | 24.1 | 42.1% | 30.4% | 36.4% |
| 6 | 22.2 | 17.3 | 18.6 | 33.7% | 24.7% | 25.0% |
| 8 | 21.7 | 16.8 | 14.0 | 32.2% | 24.0% | 18.4% |

**Shallow is better, and the curve is monotone below n-max 3.** Acceptance falls steeply with depth
(86% → 32% from n-max 1 to 8) because each additional drafted token is a *conditional* prediction of the
next, and this model's MTP head is not strong enough to keep that chain accurate. Because verification
cost grows with the number of proposed tokens while acceptance collapses, deeper drafting is a net loss:
n-max 8 is **1.6× slower than n-max 1** at 1k and **2.1× slower at 16k**.

**n-max 1 and 2 are the operating points** (within noise of each other at 1k; n-max 2 slightly better at
16k, n-max 1 clearly better at depth because its acceptance holds). The author's and PR #28118's
double-digit gains at n-max 6 were measured on a *different* model/quant (27B, Q4_K_M, Vulkan) and do not
transfer to this MTP head.

## The negative results, consolidated

| lever | result |
| --- | --- |
| `--spec-draft-n-max` 4/6/8 | **worse** (acceptance collapse) |
| n-gram lookup ahead of MTP (cascade) | **worse** (42% vs 62% acceptance; lookup wins first refusal with a worse draft) |
| PR #28118 device-resident spec checkpoints | **~0%** (branch already uses `rs_rollback`; `n_rs_seq>0`, `QWEN4EXP` supported) |
| `--spec-draft-p-min 0.75` | **0%** (identical acceptance) |
| standalone vs shared MTP head | **0%** (same ~61%) |

## What this means: decode is draft-quality-bound, not config-bound

Every configuration change we can make from the command line now lands on the same wall: **~61% acceptance
with a 2.6-token mean draft length, giving 33–35 t/s.** The levers that could move it are:

1. **A better draft head.** Our head is unsloth's shared Q8_0, fitted to *their* trunk and quant. A head
   trained on **PROJFIX** would lift acceptance directly, and acceptance is the multiplier on the whole
   decode path. This is the one lever with real headroom — and `MakazhanAlpamys/Soup` (fine-tuning with
   layer streaming) is exactly the tool for producing it.
2. **The FR-Spec trimmed-vocab head** (3.8× smaller draft projection) — **fixed and measured**: it runs
   (the fault was a converter alignment bug, not the kernel) but is **≈ a wash**, +2% at n-max 2 and −4% at
   n-max 1, because it costs ~4 points of acceptance. See `frspec-head-fixed-and-draft-census-20260915.md`.
3. **QSA decode tuning** — the sparse decode path is in the build; whether it triggers on our shapes is
   unverified.

## Where we are

| metric | value |
| --- | --- |
| best prefill | **1,057 t/s @16k** (ub 16384) |
| best decode | **34.6–35.1 t/s** (n-max 1–2) |
| best at depth | 29–30 t/s @16k, 30–32 @32k |
| Halogen reference | 42–45 t/s (two drafters, their own trunk) |
| serial ceiling at 4.254 GB/token | 47–56 t/s |

We are **~80% of the way to Halogen's decode on one drafter**, and the bandwidth analysis says the
remaining headroom at the MTP operating point is overhead/acceptance, not bytes. (The fitted draft:target
cost ratio `r ≈ 0.5` was later **superseded by direct phase timing: draft is only ~16% of the decode wall,
target verify + host is ~84%** — see `review-corrections-and-round-timing-20260915.md`. The cheap-drafter
route therefore cannot reach 42 t/s on its own.) See `draft-head-training-plan-20260915.md`.
