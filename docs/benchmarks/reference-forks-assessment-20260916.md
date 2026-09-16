# Reference forks: what we can take (2026-09-16)

Assessment of four sources the founder surfaced, plus the carve question they were asked alongside.

**Outcome: both forks were ported, built and measured. Neither is a win on our engine, and the reasons are
measurable — but one actionable result came out of it: MTP draft depth is content-dependent (~92% acceptance
content wants `n-max 4`, +10%), and the MTP "instability" we could not reproduce was a content-mix artifact,
not noise.**

- **`MMID_512`** (halo-box's flagship kernel, our exact model shape): **−0.2%**. Ported and committed
  `135ade1f`, coverage-proven so the negative is real.
- **`--spec-draft-adaptive`** (myhacsint): **−4.7% to −9.6%** vs the better fixed depth. Ported and committed
  `cbb48a7d`.
- **`MMV_GROUP`, `GDN_GATE`, fused prologues**: **cannot apply** — gated to Q8_0/Q6_K, and our model is IQ4_NL
  for every expert and attention tensor.
- **The carve**: a smaller carve "works" only by silently running 5× slower — measured, not inferred.


---

## 1. The carve: host RAM is *not* the same speed, and a small carve silently costs 5×

The hypothesis was: the memory is unified LPDDR5X, so a layer resident in host RAM should be read at the
same speed as one in the device pool; freeing the carve to 0.5 GB should therefore be free.

**Measured: the premise is false, for a reason that only shows up under load.** The device pool and the
system-memory path are the same physical LPDDR5X, but the GPU reads them at very different speeds — roughly
**133 GB/s through the carve versus ~26 GB/s through the system-memory path**. This is not visible from any
allocation API; it only appears when the weights are actually read every token. §"Retested at a 16 GB carve"
below is the experiment that shows it.

Two measurements frame the problem. The advertised pool, and the largest single allocation that *succeeds*:

| carve | pool reported | largest *single* allocation that succeeds |
| ---: | ---: | ---: |
| **0.5 GB** | 60.07 GB (55.94 GiB) | **63.31 GiB** (67,982,327,808 B) |
| 16 GB | 67.82 GB (63.16 GiB) | (weights load — see below) |
| 96 GB (validated) | 107.87 GB (100.4 GiB) | — |

**All three allocation paths — `hipMalloc`, `hipMallocManaged`, `hipHostMalloc` — return the same ceiling**,
which sits ~13% above the reported pool. There is no second memory route: managed memory is quota'd against the
same cap, and pinning is not an escape hatch. Supporting code facts:

- **`ggml-cuda.cu:156`** — the allocator only honours **`GGML_CUDA_ENABLE_UNIFIED_MEMORY`**; `grep` finds no
  other name. *Every launch script we had written set `GGML_HIP_ENABLE_UNIFIED_MEMORY`, which is inert.*
- **`ggml-cuda.cu:5706`** — the UMA free-memory report is compiled out for our build:
  `#if defined(__linux__) && !defined(GGML_USE_HIP)`. On Windows HIP the device reports
  `prop.integrated=1` / `prop.managedMemory=0`, so allocation falls to plain `cudaMalloc`.
- **The gap between pool and ceiling is a trap, not capacity.** An allocation that succeeds because it is under
  the ceiling but over the pool is served from the slow path at a 5× penalty. `hipMalloc` returning success
  therefore tells you nothing about performance. **Size the carve to the pool, not the ceiling.**
- `GGML_CUDA_NO_PINNED` **disables** host buffers entirely (returns `nullptr`, falling back to a CPU buffer)
  rather than unpinning them. Not a lever.

### What the carve must hold — and the two different thresholds

Device memory has to hold the **weights (fixed) *and* a compute buffer (scales with the ubatch) *and* KV**:

| component | size | evidence |
| --- | ---: | --- |
| weight buffer | **66.01 GiB** (70,874,867,968 B) | `allocating 67591.54 MiB` |
| compute buffer @ `-c 32768 -ub 16384` | **5.94 GiB** (6,375,604,224 B) | `failed to allocate ROCm0 buffer of size 6375604224` |
| KV, f16 | not separately measured; grows with `-c` (production runs `-c 262144`) | — |
| **device total (production `-ngl 99`)** | **≈ 72 GiB at 32k, more at 251k** | sum |

*(An earlier draft of this document quoted a 32.30 GiB compute buffer. That number came from a `--fit on` run, which
silently reduces `-ngl` and therefore builds a larger compute graph; it is not the production figure. The
production figure is the 5.94 GiB above, which is what actually failed at the 16 GB carve.)*

**There are two different thresholds, and conflating them was the trap:**

| threshold | condition | consequence if violated |
| --- | --- | --- |
| **ceiling** (~1.13 × pool) | weights must be under it | **hard failure** — `cudaMalloc failed`, model will not load |
| **pool** | weights **+ compute + KV** must be under it | **silent 5× slowdown** — loads fine, runs on the slow path |

That model explains every measurement exactly:

| carve | pool | ceiling ≈ 1.13×pool | weights 66.01 GiB | observed |
| ---: | ---: | ---: | --- | --- |
| 0.5 GB | 55.94 GiB | 63.31 GiB | **over the ceiling** | fails to load |
| 16 GB | 63.16 GiB | ~71.4 GiB | under ceiling, **over the pool** | **loads, 5× slow** |
| 96 GB | 100.4 GiB | ~113.5 GiB | under both, with room for compute | **fast (validated)** |

So the weights load at a 16 GB carve only because the driver lets a single buffer run ~13% past the pool — and
everything past the pool is read at ~26 GB/s. **Size the carve to the pool, never to the ceiling.**

**Minimum carve for full speed:** pool ≥ 66.01 + ~6 (compute) + KV ≈ **72 GiB = 77.3 GB**, i.e. a carve of
roughly **35 GB** by the `pool_GB ≈ 59.8 + carve/2` model (which fits all three measured points: 0.5 → 60.05 vs
60.07; 16 → 67.80 vs 67.82; 96 → 107.80 vs 107.87). Round up for margin — the compute buffer grows with `-ub`
and the long-context KV with `-c` — so **48 GB is the sensible minimum and 96 GB the safe validated value.**


**The 0.5 GB carve fails on the weights, before batch size can matter.** Its ceiling is 63.31 GiB against a
66.01 GiB weight buffer — a 2.69 GiB shortfall — and the weight buffer is not batch-dependent, so no `-ub`,
`--fit` or `-ngl` setting can recover it.

**Practical recommendation: keep the 96 GB carve for the published configuration.** It is the only carve
confirmed at full speed, and on a UMA box the carve is the model's home, not waste. A carve near 48 GB should
also work by the model above, but that is an interpolation and would need its own measurement before any number
taken at it is quoted.

### Retested at a 16 GB carve: it *loads*, but runs 5× slower — so the large carve is required for speed, not just fit

After the above was written the carve was changed to ~16 GB (pool 67.82 GB = 63.16 GiB, host RAM 111.65 GB) and
the load retested. This is the most informative experiment in the whole investigation, because it **succeeds**
and is still useless:

| | 96 GB carve (production) | **16 GB carve (measured)** |
| --- | ---: | ---: |
| weight buffer allocates? | yes | **yes** — under the ~71 GiB ceiling, but **over** the 63.16 GiB pool |
| server reaches `listening on` | yes (~68 s) | **yes** (~59 s — load is disk-bound either way, so not a diagnostic) |
| prefill | **1,031 t/s** | **85.5 t/s** (66-token prompt) |
| decode | 34 t/s (MTP) / 28.3 serial | **6.25 t/s** |
| per-token decode | ~33 ms | **159.9 ms** |
| MTP head | works | **crashed the GPU** (`ROCm error: unspecified launch failure`) |

**The slowdown is structural, not a cold-cache artifact.** Four identical requests in one server session:
rep 1 = 6.26 t/s, rep 2 = 6.20 t/s — dead flat, and within rep 1 the running average held at 6.26/6.33/6.23.
A cache-warming explanation requires convergence toward ~30 t/s; there is none.

**How much memory is on the slow path — measured by inference, and it is not just the overflow.** Only 4.3% of
the weight buffer (66.01 vs 63.16 GiB) exceeds the pool, so if only that excess were slow the cost would be
~4 ms/token. The observed penalty is ~127 ms/token — **30× larger**:

| model | extra ms/token | observed |
| --- | ---: | ---: |
| only the 4.3% excess served slowly | 4.15 ms | **126.9 ms** |
| the **entire** 66.01 GiB served at system-memory speed | 127.8 ms | **126.9 ms** |

Working backwards, decode runs at an effective **26.4 GB/s** against the production **~133 GB/s** marginal
bandwidth — the observed 5× exactly. So the *whole* weight buffer is being served slowly, not the 4.3 % that
overflows. *Mechanism (hypothesis, not measured):* a single large allocation that cannot be placed
contiguously inside the pool is likely placed entirely in system memory, rather than being split with only the
excess spilling. I did not verify that directly — what is measured is the effect and its size.

**This is the direct answer to "it is the same unified RAM, so it should be the same speed": it is not.**
Weights inside the carve are read by the GPU at ~133 GB/s; the same weights served from the system-memory path
are read at ~26 GB/s. Same physical LPDDR5X, ~5× apart, because of how the GPU's aperture and caching treat the
two. The carve is not a bookkeeping partition that could be left implicit — it is the fast path.

**Conclusion: a carve below the model's footprint does not fail gracefully — it silently becomes 5× slower.**
It still loads, so nothing warns you; the MTP head then crashes the GPU outright. **The carve must hold the whole
resident set inside the pool; 96 GB does, 16 GB does not.**

| carve | pool | ceiling ≈ 1.13×pool | weights 66.01 GiB | verdict |
| ---: | ---: | ---: | --- | --- |
| 0.5 GB | 55.94 GiB | 63.31 GiB | over the ceiling | **fails to load** |
| 16 GB | 63.16 GiB | ~71.4 GiB | under ceiling, **over pool** | **loads, 5× slower; MTP crashes** |
| ~40–48 GB | 74–78 GiB | ~84–88 GiB | fits with room for compute | expected OK, **not tested** |
| **96 GB** | 100.4 GiB | ~113.5 GiB | fits comfortably | **validated; all published numbers** |

The model `pool_GB ≈ 59.8 + carve/2` fits all three measured points (0.5 → 60.05 vs 60.07; 16 → 67.80 vs
67.82; 96 → 107.80 vs 107.87), so the row for 32 GB is a reliable interpolation.

### Partial offload (`-ngl < full`) hangs in the driver


The device request *does* scale with `-ngl`, so partial offload was the obvious way to use host RAM:

| `-ngl` | device buffer requested |
| ---: | ---: |
| 8 | 115,146 MiB (112.4 GiB) |
| 16 | 92,727 MiB (90.6 GiB) |
| 32 | 43,811 MiB (**42.8 GiB** — under the cap) |

Every partial split hangs rather than failing cleanly. `-ngl 32`, `-ngl 20` and `-ngl 8 -dev ROCm0` all stalled
with the main thread in **`Wait` / `WaitReason=Unknown`** — a kernel-mode driver wait — with the working set
frozen (41.18 GB) and CPU frozen (0.7 s after minutes), while **76 GB of host RAM sat free**. That is a driver
deadlock, not exhaustion, and it means **`-ngl < full` is simply not usable on this stack**.

**This is also why an earlier result in this session was retracted.** A hung `llama-server` had been left
holding 57 GB, and a `ROCm_Host` allocation failure observed while it was alive was **contamination, not a
finding**. Re-run clean, the same configuration asks the device for 115 GiB and fails normally.


**If the 0.5 GB carve must be kept**, the only route is a smaller resident set, and the numbers do not
encourage it: production needs ≈72 GiB (weights 66.01 + compute 5.94) against a 63.31 GiB ceiling — roughly a
**12% reduction** — and it would then also have to stay inside the 55.94 GiB pool to avoid the 5× slow path,
which is a **22% reduction**. That means a smaller quant *and* a smaller `-ub`, invalidating every published
number. Stated as an option only; it is a product decision, not an engineering one, and I do not recommend it.

**Env-var bug worth fixing — and how *not* to fix it.** `kernel-work/*.ps1` set
`GGML_HIP_ENABLE_UNIFIED_MEMORY`; the code reads `GGML_CUDA_ENABLE_UNIFIED_MEMORY`, so the line was **inert in
78 tracked files**. This has been corrected across all of them by **deleting** the dead line (75 handled by
`fix-inert-unified-memory-var.py`, 3 repaired by hand), and the three `docs/benchmarks/*-20260913.md` recipes
now carry a correction note (README and `setup/` were already clean). Verified afterwards: `bash -n` clean on
every `.sh`, PowerShell parser clean on every `.ps1`, and zero remaining occurrences.

**Deleting, not renaming, was the point.** Every published number was measured with the line inert, i.e. with
plain `cudaMalloc` over the carve pool. Renaming would flip the weight allocation to `cudaMallocManaged` — a
different allocator with different performance and an untested correctness surface — silently invalidating the
baseline. `GGML_CUDA_ENABLE_UNIFIED_MEMORY` is now an unclaimed lever to be measured on its own if ever wanted;
it is not part of the validated recipe.

(It also would not have rescued the 0.5 GB carve: the managed path caps at the same 63.31 GiB.)

---

## 2. `halo-box/strix-llama.cpp` — the significant find

**It shares our exact lineage.** Its tip is a single merge, `0636c9ae "pwilkin/strix-halo official merge
(#63)"`, and its tree carries the same `RDNA3_5` block in `vendors/hip.h:223` and the same UMA gate at
`ggml-cuda.cu:6782`. It also shares the pwilkin Qwen4exp machinery we depend on — `qwen4exp_use_block_selection`,
`indexer_top_k`, `qwen4exp_score_key_limits`, `qsa_position_prefix`, `per_layer_tok_embd`. This is not a rival
design; it is our fork's sibling with a deeper HIP kernel set.

**Four HIP optimizations we do not have** (all absent from our tree, verified by grep):

| lever | what it does | in their tree |
| --- | --- | --- |
| `GGML_CUDA_DISABLE_MMID_512` | compact `MUL_MAT_ID` tiles gated on **RDNA3.5 + `n_experts==512` + `n_expert_used==10`** — *our model's exact shape* | `mmid.cu:207` |
| `GGML_CUDA_DISABLE_MMV_GROUP` | consecutive single-column matvecs sharing one activation (gate/up pairs, hyper-connection projections) in **one launch**; cap 4 segments | `ggml-cuda.cu:4219`, `mmvq.cuh:28` |
| `GGML_CUDA_DISABLE_WEIGHTED_DOWN` | one-token **IQ4_NL MoE down projection** with the selected-expert weighted sum in the epilogue | `ggml-cuda.cu:4682` |
| `GGML_CUDA_DISABLE_GDN_GATE` | whole GDN decode chain (conv → norm → gate → recurrence → state copy) as one kernel, plus DPP reductions | `ggml-cuda.cu:4332` |

They also carry fused-prologue matvecs we lack — `fq_prologue` (silu/sigmoid applied while activations are
quantized in-kernel) and `fq_gdn_gate` — and a `hyperconn.cu` (457 lines) that is **missing entirely** from our
tree.

**All four sit in one commit: `6130b7262` "hip: optimize RDNA3.5 MoE inference paths"** (Gaetan Puleo,
2026-09-04) — 26 files, +3141/−214. The bulk is `mmvq.cu` (+1456) and `ggml-cuda.cu` (+649).

### Result: ported and measured — MMID_512 is a true negative, and the rest cannot apply

**`MMID_512` ported (58 lines) and measured: −0.2% decode, +0.1% prefill, output byte-identical.** Committed as
`135ade1f`. For decode `n_tokens=1`, so the generic path launches `n_experts`=512 single-warp blocks to place 10
expert slots, 48 times per token; the fast path does it in one 1024-thread block. That sounds like an obvious
win, so before trusting the negative I proved the fast path **actually fires** with a temporary coverage probe:
`MMID512-COVERAGE hit: cc=16781649 n_experts=512 n_expert_used=10` — the RDNA3.5 ID, our exact shape. A guard
mismatch would have made this a false negative (the mistake I made earlier with the `rpb` patch).

**Why it cannot win here: HIP graphs already remove the launch overhead this kernel targets.** If 48 calls × 512
launches were exposed, at 5 µs each they would cost ~123 ms/token — we measured *zero*. Our HIP-graph build
(worth ~65 ms/token) has already amortized them. The kernel also adds a serial 512-iteration prefix sum in
thread 0. Kept behind `GGML_CUDA_DISABLE_MMID_512` so the negative stays reproducible.

**The other three levers are Q8_0/Q6_K-only, and our model is IQ4_NL.** This is not a preference, it is a hard
gate in their code:

| lever | gate | applies? |
| --- | --- | --- |
| `MMV_GROUP` | `ggml_cuda_mmv_group_seg_ok` returns true **only for `GGML_TYPE_Q8_0`** (`mmvq.cu:2212-2215`) | **no** |
| `GDN_GATE`, `fq_prologue` | `mmvq_fq_type_ok` accepts Q8_0/Q6_K; IQ4_NL returns `MMVQ_FQ_IQ_TYPES`, which **defaults to `false`** (`mmvq.cu:1553`) | **no** |
| `WEIGHTED_DOWN` | `experts->src[0]->type != IQ4_NL && != Q8_0` → rejects; **IQ4_NL explicitly supported** (`mmvq.cu:3171`) | yes |

I verified the gate against the model itself rather than assuming: a GGUF census of our 9 PROJFIX shards shows
**every expert and attention tensor is IQ4_NL** (`ffn_gate_exps`, `ffn_up_exps`, `ffn_down_exps`, `attn_qkv`,
`attn_gate`, `ssm_out`, all HC projections). Only two HC projections and `ple_key` are Q8_0. So the Q8_0-gated
levers would fire on a tiny fraction of tensors, not on the 32% expert share.

**`WEIGHTED_DOWN` is the one remaining applicable lever, and its ceiling is small.** It fuses the IQ4_NL routed
down projection with the 10-expert weighted sum, removing a `[n_embd, n_used]` f32 intermediate
(2560 × 10 × 4 B = 100 KB/layer, 200 KB written+read). Over 48 layers that is ~9.8 MB/token ≈ **0.23% of the
4.219 GB/token decode budget**, or ~0.07 ms of 33 ms. It also needs two device helpers absent from our tree
(`mmvq_hc_mul_rn`/`mmvq_hc_add_rn`), and the fusion matcher in `ggml-cuda.cu` is ~100 lines of graph-pattern
matching. Given a ~0.2% ceiling, it is a poor use of the next cycle.

**Conclusion: the halo-box HIP set does not transfer by porting.** Its kernel does not help (launch overhead
already gone), and its other three levers target weight formats we do not use. That is a negative about
*applicability*, not about the work's quality — on a Q8_0-family quant (which is what their own reference
deployment used, `UD-IQ4_XS` for the target with **Q8_0 experts** in the MTP head) it presumably does help.

**Broader lesson:** our closed-negative list and theirs were both attacking *launch and fusion* overhead. Our
engine already pays almost none of that, because the HIP graph absorbs it. The remaining decode cost is the
4.219 GB/token of *actual bytes moved*, which no amount of fusion removes. That is why fuse-and-group kernels
keep measuring neutral-to-negative here, and why the productive levers are quant choice and bandwidth, not
dispatch.


---

## 3. `myhacsint/llama.cpp` `production/strix-halo-qwen4exp-b10685`

A curated **b10685** snapshot, Vulkan-first, RADV production-gated — a different release line from ours, but
two items map directly onto open problems:

| item | detail | relevance |
| --- | --- | --- |
| **shared-MTP fit fix** | `common/fit.h:17-28` adds `common_fit_extra_model` with `shares_model` and **`path_model_shared`**; during the no-alloc probe the compact sidecar receives a **metadata-only view of its target** so omitted shared tensors resolve without counting target weights twice | **Directly fixes our B1 blocker.** We hit `qwen4exp requires ctx_other to be set` and had to fall back to `--fit off`; `--fit off` disables auto-fitting. This is the missing upstream guard (upstream PR 27941 / commit `2fb989b9e7`) |
| **`--spec-draft-adaptive`** | per-sequence **acceptance EMA** (`acc_ema_alpha 0.25`, `acc_ema_init 2.0`, `acc_ema_probe 1.0`) sizes each draft just above the measured acceptance; clean drafts are treated as **censored** and probed upward | **Ported and measured — a negative on this engine** (below) |

### `--spec-draft-adaptive`: ported and measured — a true negative, and it explains our MTP "instability"

**Ported (71 lines) behind an off-by-default flag, committed as `cbb48a7d`.** The controller provably works:
draft counts scale as designed (n_max=2 → 402/555/398 drafts across chat/corpus-1024/corpus-8192; n_max=4 →
533/880/980; adaptive → 504/621/631, always landing between the two fixed values).

It still loses to the better fixed value on **every** content class (shared MTP head, `p-min 0.0`, gen 192, best
of 3):

| content | n_max=2 | n_max=4 | adaptive | adaptive vs best fixed |
| --- | ---: | ---: | ---: | ---: |
| chat (prose) | 46.53 | **51.21** | 48.81 | **−4.7%** |
| corpus 1024 | **33.98** | 30.13 | 30.71 | **−9.6%** |
| corpus 8192 | **27.39** | 25.74 | 25.09 | **−8.4%** |

**Why, and this is the interesting part: the optimum draft depth is content-dependent here, which is exactly
the problem the controller was built for — but its control law assumes deeper always pays.** Chat prefers
n_max=4, corpus prefers n_max=2. The "full accept → probe deeper" rule walks the length up whenever drafts are
clean; on corpus that is precisely when deeper drafting is *most* wasteful (58–67% of drafted tokens are
discarded at n4), so the probe marches into a strictly slower region. A controller that **measured whether depth
pays**, rather than assuming it, would be needed. Left off by default.

**Reconciliation with our own earlier n-max sweep** (`decode-levers-nmax-and-negative-results-20260915.md`,
corpus prompts, ub 2048): it found n-max 4 strictly worse (28.0 vs 34.1 t/s @1k, acceptance 42% vs 64%) and
concluded "shallow is better". That is **not** contradicted here — the two measurements differ in content. The
variable that decides it is the acceptance rate the content supports:

| content | n2 acceptance | n4 acceptance | depth that wins |
| --- | ---: | ---: | --- |
| chat (instructed, structured answer) | 91.8% | 82.4% | **n_max 4** (+10%) |
| corpus continuation @1k | 53% | 40.1% | **n_max 2** (+13%) |
| corpus continuation @8k | 40.5% | 33.2% | **n_max 2** (+6%) |

Deeper drafting only pays when the extra depth is still converted into accepted tokens. At 92% there is room;
at 40% there is not. **Our published n-max 2 default remains the right choice for a mixed workload**, because
it is near-optimal on both and never collapses; n_max 4 is a content-specific win, not a global one.

**This also resolves the MTP "instability" we could not reproduce earlier.** Acceptance is not noisy within a
content class — it is *perfectly* deterministic: three consecutive corpus/8192 reps gave 55/130, 53/134, 53/134
at n2 and 109/324, 108/328, 108/328 at n4. The spread we measured before (47% vs 65%, and the 632-draft
outlier) was a difference in **content mix between runs**, not run-to-run variance. That is a real finding: it
means any MTP acceptance figure must state the content class, and it removes "unstable MTP" from our problem
list — the engine is stable, our probe was not controlled.

Their `QWEN38-FLASH-NEXT-MTP.md` also confirms our MTP packaging finding independently: the three-shard target
GGUFs carry **no integrated MTP block**, the head ships as a separate shared Q8_0 sidecar, and
`--spec-type draft-mtp` alone "still lacks a draft" without `--spec-draft-model`. Their gated sidecar SHA-256 is
`5ff54097406a905cf3a724c709124ceb0e3e10235ee862298969e91c96fa96e6` — worth comparing against our copy.

---

## 4. Reddit threads — not retrievable

Both shortlinks (`r/StrixHalo/s/cp4cjiytES`, `r/LocalLLM/s/dXh8BUehoV`) return only "Reddit" via every fetch
route tried (canonical, `.json`, `old.reddit`, HEAD-redirect). The repos they point at were identifiable and
are covered in §2–3, so the substance is captured. If the comment threads matter — they often carry the
dissenting measurements, which is where the real information is — they need a browser session, not a fetcher.

---

## Recommended order

Both forks have now been ported, built and measured. Here is what that leaves, in priority order.

**Done this session:**
- `MMID_512` — ported, coverage-proven, **−0.2%** → committed `135ade1f`.
- `--spec-draft-adaptive` — ported, functional, **−4.7% to −9.6%** → committed `cbb48a7d`.
- `MMV_GROUP` / `GDN_GATE` / fused prologues — **closed by a gate check**, not a port: Q8_0/Q6_K-only, and our
  model is IQ4_NL throughout (verified against the GGUF).
- The 5× carve penalty and the MTP "instability" — both explained and measured (§1, §3).

**Next, in order:**

1. **Keep the 96 GB carve.** It is the validated configuration; the carve must hold the resident set inside the
   pool, and a small carve silently costs 5×.
2. **Keep the MTP draft depth at `n-max 2` for mixed workloads, and make it configurable per deployment.** The
   adaptive study's actionable result is that the optimum tracks the acceptance rate the content supports: at
   ~92% acceptance (instructed, structured answers) `n-max 4` measures **+10%** (46.5 → 51.2 t/s); at ~40–53%
   (corpus continuation) `n-max 2` wins by 6–13%. Our published `n-max 2` default stays correct because it is
   near-optimal on both and never collapses — but a chat-heavy deployment should use 4. Both are already flags
   (`--spec-draft-n-max`), so this is configuration, not code.
3. **Port the shared-MTP fit fix** (`common_fit_extra_model::path_model_shared`) — the one remaining item with a
   concrete, already-solved target (our `--fit off` workaround). Low risk, no speed claim.
4. **Do not port `WEIGHTED_DOWN`** on current evidence: applicable, but a ~0.2% ceiling for ~200 lines and two
   missing device helpers. Revisit only if a Q8_0-dominated quant is chosen later.
5. **The real lever remains bandwidth and quant**, not dispatch. Every fuse-and-group kernel measured neutral
   here because HIP graphs already absorb launch overhead; the 4.219 GB/token of actual traffic is untouched by
   any of them. If more decode is wanted, the honest paths are a smaller/more aggressive quant or a weight
   format whose decode kernels are better matched to this GPU.

Nothing above requires a paid route, a push or a provider call.

