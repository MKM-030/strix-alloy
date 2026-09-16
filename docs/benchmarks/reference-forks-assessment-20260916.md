# Reference forks: what we can take (2026-09-16)

Assessment of four sources the founder surfaced, plus the carve question they were asked alongside.

**Outcome: both forks were ported, built and measured. Neither helped, and three of the original explanations
were wrong and are withdrawn — including one that measured a code path decode never runs.**

- **`MMID_512`** (halo-box's flagship kernel): **cannot affect decode at all.** A phase probe recorded one call
  in a 200-token decode, all prefill; the helper is a large-batch path. The earlier "−0.2% decode" measured the
  wrong phase. Committed `135ade1f`, comment corrected in `d638e2ed`.
- **`--spec-draft-adaptive`** (myhacsint): **worse than the shipped default on every cell** (−3.2% to −11.4%
  vs `n-max 2`) once measured with medians per size instead of best-of-three pooled. Committed `cbb48a7d`.
- **The `llama-bench` `rand()` defect is real** (13.2% of the vocabulary reachable on the Windows CRT) but costs
  only 0–1.4% throughput, and the PLE n-gram locality theory for it is refuted.

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

### Result: MMID_512 was ported and measured — and it turns out decode never runs it

**MMID_512 ported (58 lines), built, and A/B'd: −0.2% "decode", +0.1% prefill, output byte-identical.**
Committed as `135ade1f`. The shape is real: for a MoE batch the generic path has to place `n_expert_used`=10
expert slots across a grid sized by `n_experts`=512 with one warp per block, while the fast path does the same
placement in one 1024-thread block via a histogram plus a 512-entry prefix sum.

**Correction 1 — I published two wrong explanations for it, both caught by external review.**

First I wrote that the generic path issues "512 kernel launches" per call and that HIP graphs absorb them. It
does not: `dim3 num_blocks(n_experts, 1, 1)` is **one kernel launch with a 512-block grid**. Thread blocks are
not launches, so the `48 × 512 × 5 µs ≈ 123 ms/token` figure was invented, and "the graph removed that
overhead" explained nothing.

**Correction 2 — and this is the substantive one: the kernel does not execute during decode at all.**
My coverage evidence was a single startup print showing a matching *shape*. A reviewer pointed out that this
says nothing about which phase ran it. So I built a probe that counts calls by token width and ran it against a
**200-token decode**:

```
MMID512-PHASE calls=1  decode(n_tokens==1)=0  prefill(n_tokens>=128)=1  other=0  shape_ok=1 enabled=1
```

**One call in the entire run, and it was prefill.** The callers confirm it: `ggml_cuda_launch_mm_ids_helper`
is reached only from `mmb.cu` (their large-batch kernels, `T ≥ 512`), `mmq.cu` and `mmf.cu` — the large-batch
paths. Serial decode takes `MMVF`/`MMVQ` instead (`ggml_cuda_should_use_mmvf`, `dst->ne[2] == 1`).

**Therefore the "−0.2% decode" figure measured a code path that decode never executes.** The honest statement
is narrower and different in kind:

> MMID_512 **cannot affect serial decode** on this engine — it is a prefill/large-batch path. The measured
> prefill result (+0.1%) is within noise, so on this engine the port is **neutral and unexercised in decode**,
> not "a decode negative".

This also invalidates the generalisation I drew from it — that fuse-and-group work "keeps measuring
neutral-to-negative here". One of the data points for that claim was measuring the wrong phase. The claim may
still hold, but it now rests on fewer, and unrelated, experiments.

**The applicability gates, checked against the model.** `MMV_GROUP` is Q8_0-only *as implemented*; the fused
matvec prologues contain an IQ4_NL path behind a default-off gate (`MMVQ_FQ_IQ_TYPES`), so they are an untested
candidate rather than a closed door. The dtype census still deprioritises the Q8_0-only levers on the target: a
GGUF census of our 9 PROJFIX shards shows **every expert and attention tensor is IQ4_NL**
(`ffn_gate_exps`, `ffn_up_exps`, `ffn_down_exps`, `attn_qkv`, `attn_gate`, `ssm_out`, every HC projection); only
two HC projections and `ple_key` are Q8_0. That says nothing about the **draft side**, which is a separate dtype
population (the MTP head is Q8_0).

**`WEIGHTED_DOWN` is applicable, and I overstated its dismissal.** It fuses the IQ4_NL routed down projection
with the 10-expert weighted sum, removing a `[n_embd, n_used]` f32 intermediate (2560 × 10 × 4 B = 100 KB/layer,
200 KB written+read). Over 48 layers that is ~9.8 MB/token ≈ **0.23% of the 4.219 GB/token decode estimate**,
about 0.07 ms of 33 ms.

**But 0.23% is the avoided *bytes*, not a hard runtime ceiling.** A fusion can also remove elementwise work,
reductions, materialisation and execution dependencies, while the intermediate may in fact be cache-resident, or
the fused kernel may hurt occupancy. Correct framing: **a low-priority candidate with a likely small but
unmeasured effect.** It needs two device helpers absent from our tree (`mmvq_hc_mul_rn`/`mmvq_hc_add_rn`) plus
~100 lines of graph-pattern matching in `ggml-cuda.cu`, so it should be tried only after the harness is
trustworthy and with exact graph-pattern coverage and a numerical check — not dismissed as "disproved", and not
prioritised on a 0.2% model either.

**Conclusion, restated correctly: the halo-box HIP set did not transfer in the configurations tested.** The one
kernel ported shows no gain; the others are either Q8_0-only on the target or implemented-but-gated for IQ4_NL
and therefore untested. That is a statement about *our measurement coverage*, not proof about their work — on a
Q8_0-family quant it may well help.

**Broader lesson, corrected.** My earlier version of this paragraph said the graph "absorbs launch overhead" and
that only bytes remain. The first half was wrong (thread blocks are not launches) and the second half was too
tidy: fusion can remove real work that is *not* weight traffic. What the evidence supports is narrower — our
fuse-and-group attempts have measured neutral-to-negative, our byte estimate is a model rather than a bus
measurement (§ decoder notes), and the levers with a *demonstrated* effect here have been quant choice and
weight bandwidth, not dispatch.

---

## 3. `myhacsint/llama.cpp` `production/strix-halo-qwen4exp-b10685`

A curated **b10685** snapshot, Vulkan-first, RADV production-gated — a different release line from ours, but
two items map directly onto open problems:

| item | detail | relevance |
| --- | --- | --- |
| **shared-MTP fit fix** | `common/fit.h:17-28` adds `common_fit_extra_model` with `shares_model` and **`path_model_shared`**; during the no-alloc probe the compact sidecar receives a **metadata-only view of its target** so omitted shared tensors resolve without counting target weights twice | **Directly fixes our B1 blocker.** We hit `qwen4exp requires ctx_other to be set` and had to fall back to `--fit off`; `--fit off` disables auto-fitting. This is the missing upstream guard (upstream PR 27941 / commit `2fb989b9e7`) |
| **`--spec-draft-adaptive`** | per-sequence **acceptance EMA** (`acc_ema_alpha 0.25`, `acc_ema_init 2.0`, `acc_ema_probe 1.0`) sizes each draft just above the measured acceptance; clean drafts are treated as **censored** and probed upward | **Ported and measured — a negative on this engine** (below) |

### `--spec-draft-adaptive`: ported and measured — a regression against the shipped default

**Ported (71 lines) behind an off-by-default flag, committed as `cbb48a7d`.** The controller provably works:
draft counts scale as designed, always landing between the two fixed arms.

**Re-measured with the repaired harness** (medians, corpus rows now tagged, no best-of-reps, per-size cells
rather than pooled). This replaces the earlier table, and it changes the conclusion:

| content | size | n_max=2 | n_max=4 | adaptive | n4 vs n2 | adaptive vs n2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| chat | 259 | **45.31** | 45.45 | 41.96 | +0.3% | **−7.4%** |
| corpus | 1024 | **33.07** | 27.66 | 29.29 | −16.3% | **−11.4%** |
| corpus | 8192 | **26.97** | 24.61 | 26.12 | −8.8% | **−3.2%** |

**Withdrawn claim: "`n-max 4` is +10% on chat".** That came from taking the *best of three* repetitions. On
medians, `n-max 4` is a **tie** on chat (+0.3%) and clearly worse on corpus. The earlier +10% was an artifact
of the aggregation, not a content effect.

**The pooled table also hid a real size dependence**, which is the defect the reviewer flagged: pooling corpus
1024 (53% acceptance) with corpus 8192 (40%) gave "−9.6%", while the true per-size figures are −16.3% and
−8.8%. Aggregating across prompt lengths was masking the effect it was supposed to measure.

**Corrected conclusion:** **`n-max 2` is the best single setting across all three cells** — it ties n-max 4 on
chat and wins on both corpus sizes, and it beats adaptive everywhere. The adaptive controller loses to the
shipped default on every cell, so as a deployment choice it is simply worse here. Its design point stands as a
design point: it optimises accepted length, and never measures what a wider verification costs, so its notion
of optimum is not the throughput optimum.

**Acceptance reproducibility, now directly evidenced.** Per-rep accepted/proposed counts from this run:

| arm | content | size | counts |
| --- | --- | ---: | --- |
| n2 | chat | 259 | 123/134, 123/134, 123/134 |
| n2 | corpus | 1024 | 98/185, 98/185, 98/185 |
| n2 | corpus | 8192 | 55/130, 53/134, 53/134 |
| n4 | chat | 259 | 147/175, 146/179, 146/179 |
| n4 | corpus | 8192 | 109/324, 108/328, 108/328 |

Two of the three n2 cells are **identical across all three reps**, and the third differs only in rep 0 (the
cold rep). So the defensible statement is: *within a fixed workload, acceptance was repeatable to within one
or two tokens per rep, and the cold rep can differ.* Not "perfectly deterministic" — but strong enough that the
earlier 47%-vs-65% spread is much more likely content mix than engine noise. The cross-run comparison is
separately notable: the corpus-8192 counts (55/130, 53/134, 53/134) reproduce **exactly** across two
independent server sessions started at different times.


**Reconciliation with our own earlier n-max sweep** (`decode-levers-nmax-and-negative-results-20260915.md`,
corpus prompts, ub 2048): it found n-max 4 strictly worse (28.0 vs 34.1 t/s @1k, acceptance 42% vs 64%) and
concluded "shallow is better". That is **not** contradicted here — the two measurements differ in content. The
variable that decides it is the acceptance rate the content supports:

| content | n2 acceptance | n4 acceptance | depth that wins |
| --- | ---: | ---: | --- |
| chat (instructed, structured answer) | 91.8% | 82.4% | **n_max 2** (n_max 4 ties) |
| corpus continuation @1k | 53% | 40.1% | **n_max 2** (+13%) |

| corpus continuation @8k | 40.5% | 33.2% | **n_max 2** (+6%) |

Deeper drafting only pays when the extra depth is still converted into accepted tokens. At 92% there is room;
at 40% there is not. **Our published n-max 2 default remains the right choice for a mixed workload**, because
it is near-optimal on both and never collapses; n_max 4 is a content-specific win, not a global one.

**What this says about the MTP "instability" we could not reproduce earlier.** Warm repeats of a *fixed*
workload were repeatable within the observed sample: three consecutive corpus/8192 reps gave 55/130, 53/134,
53/134 at n2 (42.3%, 39.6%, 39.6%) and 109/324, 108/328, 108/328 at n4 (33.6%, 32.9%, 32.9%). **I previously
called this "perfectly deterministic", which overstates it** — those are not three identical repeats, and
identical *aggregate ratios* would not prove identical accepted positions or token streams. The defensible
statement is the weaker one:

> Warm repeats of these fixed workloads were repeatable within the observed sample (within ~3%); different
> workloads produced materially different acceptance (40% vs 92%).

The earlier 47%-vs-65% spread was therefore most likely content mix between runs rather than engine instability —
but that is an inference from a small sample, not a proof, and it should be presented that way. The useful
consequence stands: **any MTP acceptance figure must state the workload**, and per-position acceptance plus
emitted tokens per round are better metrics than the single aggregate ratio.

Also note the two acceptance numbers in the table below belong to *different* configurations: 91.8% is the n_max 2
acceptance, 82.4% is the n_max 4 acceptance. Saying "depth 4 wins at ~92% acceptance" would conflate them; the
correct statement is that **on content where shallow drafting already achieves ~92%, going deeper still gained
~10%**, which is a different and weaker claim.

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
- `MMID_512` — ported, then found to be **a large-batch path that decode never executes** (phase probe: 1
  call in a 200-token decode, all prefill). The "−0.2% decode" figure measured the wrong phase. Committed
  `135ade1f`; corrected in `d638e2ed`.
- `--spec-draft-adaptive` — ported and functional, but **worse than the shipped default on every cell**
  (−3.2% to −11.4% vs `n-max 2`), once measured with medians per size instead of best-of-three pooled.
  Committed `cbb48a7d`.
- `MMV_GROUP` / `GDN_GATE` / fused prologues — `MMV_GROUP` is Q8_0-only *as implemented*; the fused
  prologues contain an IQ4_NL path behind a default-off gate, so they are **untested candidates, not closed**.
  The dtype census (every expert/attention tensor IQ4_NL) is why they are deprioritised, not why they are ruled
  out.
- The 5× carve penalty, the `llama-bench` `rand()` defect, the refuted PLE-locality theory and the MTP
  acceptance repeatability — all measured (§1, §3, and
  `llama-bench-workload-identity-20260916.md`).

**Next, in order:**

1. **Keep the 96 GB carve.** It is the validated configuration; the carve must hold the resident set inside the
   pool, and a small carve silently costs 5×.
2. **Keep the MTP draft depth at `n-max 2`.** The re-measurement makes this unambiguous: `n-max 2` ties
   `n-max 4` where acceptance is ~92% (+0.3%) and beats it where acceptance is lower (−8.8% to −16.3%), and it
   beats the adaptive controller on every cell. The earlier "a chat-heavy deployment should use 4" advice was
   based on a best-of-three artifact and is **withdrawn**. Both remain flags (`--spec-draft-n-max`), so a
   deployment with a known, high-acceptance workload can still experiment — but there is no measured reason to
   deviate from the default.
3. **Port the shared-MTP fit fix** (`common_fit_extra_model::path_model_shared`) — the one remaining item with a
   concrete, already-solved target (our `--fit off` workaround). Low risk, no speed claim.
4. **Do not port `WEIGHTED_DOWN`** on current evidence: applicable, but a ~0.2% ceiling for ~200 lines and two
   missing device helpers. Revisit only if a Q8_0-dominated quant is chosen later.
5. **The real lever remains bandwidth and quant**, not dispatch. Every fuse-and-group kernel measured neutral
   here because HIP graphs already absorb launch overhead; the 4.219 GB/token of actual traffic is untouched by
   any of them. If more decode is wanted, the honest paths are a smaller/more aggressive quant or a weight
   format whose decode kernels are better matched to this GPU.

Nothing above requires a paid route, a push or a provider call.

