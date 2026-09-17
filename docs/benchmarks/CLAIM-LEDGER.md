# Claim ledger

Every figure and verdict this repository currently endorses, with its evidence and the conditions under
which it holds — plus what has been withdrawn and why. External review asked for this so a reader can tell an
archived hypothesis from a live result without reading 110 dated files.

Convention: **Endorsed** = we would defend it today. **Conditional** = true only under the stated protocol.
**Withdrawn** = published, then falsified or retracted; do not cite. **Open** = not established.

---

## 1. Endorsed — benchmark figures

| Claim | Value | Evidence | Conditions / limits |
| --- | --- | --- | --- |
| `llama-bench` prefill, default shape | **pp512 761.30 ± 38.24 t/s** | `canonical-llama-bench-20260916.md` | Synthetic prompt (pseudorandom IDs). `±` is a sample SD, not a CI. UCRT `rand()` reaches 13.2% of vocab — see §4 |
| `llama-bench` serial decode | **tg128 31.49 ± 0.17 t/s** | same | Synthetic: a fresh random token after each step, not autoregressive. No drafter, by design |
| `llama-bench` long-prompt | **pp16384 892.59 ± 22.50 t/s** | same | `-b/-ub 16384`, ilintar's protocol |
| Served prefill | 1,031 @16k → 812 @251k | README benchmark table | `llama-server`, `-ub 16384`, no drafter, rep ≥ 3, `-c 262144`. Not comparable to the `llama-bench` row |
| Served decode, MTP | **31–47 t/s**, content-dependent | README decode table + `adaptive-draft-ab.ps1` | `n-max 2`, shared Q8_0 head. The range is the *workload*, not noise |
| Served decode, serial | 28.3 @16k | README decode table | no drafter |
| Context | **251,904 tokens** works end to end | longctx reports | no OOM, no corruption check beyond completion |
| `n-max 2` is the best single draft depth | ties `n-max 4` at ~92% acceptance, beats it below | `adaptive-draft-ab.ps1` re-run, per-size medians | three prompt cells; one corpus prompt family |

## 2. Endorsed — analysis and negatives

| Claim | Evidence | Conditions / limits |
| --- | --- | --- |
| `MMID_512` **cannot affect serial decode** | `mmid-phase-probe.ps1`: 1 call in a 200-token decode, all prefill; callers are `mmb.cu`/`mmq.cu`/`mmf.cu` | Only establishes it is a large-batch path. Its *prefill* worth is +0.1%, within noise |
| `llama-bench` `rand()` reaches only 13.2% of vocab on our CRT | `rand-check.c`, same `vcvars64` as the engine | Throughput impact separately measured at 0–1.4% (§4) — a workload-identity defect, not a speed cause |
| PLE n-gram locality is **not** why random tokens are slower | `ple-locality-ab.ps1`: the most-unique-n-gram stream was **fastest** (+5.3%) | Refutes the hypothesis; does not explain the residual |
| Carve must hold the resident set inside the pool | `reference-forks-assessment`: 0.5 GB fails to load, 96 GB validated | A small carve "works" but ~5× slower — mechanism unresolved (§5) |
| `hipMalloc` / `hipMallocManaged` / `hipHostMalloc` share one ceiling ≈1.13× the pool | `hip-ceiling.cpp` | An **allocation-acceptance boundary for one process state**, not residency or usable bandwidth (§5) |
| Decode costs a **per-operator** fixed amount, not a per-block one | `real-kernel-measured-20260916.md`: fitted ≈5.4 µs + bytes/133 GB/s | A fit of the tested operator family; intercept ≠ proven host overhead, slope ≠ proven DRAM bandwidth. One row's printed rate is unverified (§5) |
| `stew675/rdna-boosts` not yet audited | README future plan | still open |

## 3. Withdrawn — do not cite

| Withdrawn claim | Why | Replaced by |
| --- | --- | --- |
| "**177B parameters**" | Counted the PLE table as transformer parameters | **~125B** transformer + separate ~51B PLE table (byte census matches 120.8B experts × 4.5 bpw) |
| "**the only Windows-native stack**" | olliehm's shipped first | Two stacks; we claim no exclusivity |
| "**uniform 37% bandwidth shortfall / ALU-bound**" | The benchmark's own contended `atomicAdd` epilogue | With a fair epilogue the same kernel reaches ~100% of bandwidth |
| "**K-split for small-R ops**" | Cost is per-**op**, not per-block; K-split adds ops | Per-operator fixed cost is the lever |
| "**MTP acceptance is not reproducible** (47% vs 65%)" | Content mix between runs | Acceptance tracks the workload; repeatable within a fixed one |
| "**acceptance is perfectly deterministic per content class**" | The cited repeats were not identical | "Repeatable within the observed sample, ≤1–2 tokens per rep" |
| "**`MMID_512` = −0.2% decode**" | Measured a path decode never executes | `MMID_512` is a large-batch path; decode takes MMVF/MMVQ |
| "**HIP graphs absorb the 512 launches**" | A 512-block grid is **one** launch, not 512 | Explanation removed; the port measured neutral |
| "**`n-max 4` is +10% on chat**" | Best-of-three artifact | On medians it **ties** `n-max 2` (+0.3%) |
| "**retained-PM4 explains the prefill gap**" | Contradicts ilintar's own page: PM4 does not engage on prefill | Cause **unresolved** |
| "**a 16 GB carve would fit**" | Extrapolated from weights only, omitted the compute buffer | See the carve table |
| "**`rpb` 1→2 is negative**" (first version) | Invalid test: used `ncols_dst=1`, which the patch cannot touch | Re-tested at covered widths; still negative (+0.3%), correctly closed |
| "**serial vs wide-verify divergence is benign**" | Near-tie magnitude bounds size, not cause | Deterministic and sub-0.2-nat; **cause unproven**, gates 3–4 open |
| "**decode loss is uniform**" | Superseded by the per-operator fixed-cost result | See `decode-byte-accounting-20260915.md` header |

## 4. Open / unverified

| Item | Status |
| --- | --- |
| Engine independently rebuilt from `engine-patches/` by a third party | **Open** — delta published with hashes, nobody else has compiled and re-measured |
| Why `llama-bench` and the server differ | **Open, not separable from server spread** (same construction: 876 vs 952 t/s in two sessions) |
| Cause of the 26% prefill gap vs ilintar | **Open** — and not PM4 |
| Whole-buffer demotion mechanism in the small-carve case | **Open** — slowdown real and reproduced; mechanism inferred, not observed |
| Correctness gates 3 (state after 0/1/N accepts) and 4 (multi-turn, depth, retrieval, tool output) | **Not done** |
| `WEIGHTED_DOWN`; IQ-gated fused prologues | **Unmeasured** — gate/type assessment plus a byte model, not a measured negative |
| Weight byte-accounting as *DRAM traffic* | **Model only** — nominal active payload; dtype drift noted (a Q6_K head, F32 routers; `pf-census.json` ≈4.254 GB) |
| Windows stability: device-loss recovery, long-session growth, concurrent clients, cancellation, stripped-env deployment | **Not tested** |

---

## How to add a row

When a new result lands, add its **evidence path** and its **conditions** at the same time. When a claim is
falsified, move it to §3 with the replacement rather than deleting it — the retraction history is part of what
makes the remaining numbers credible. Dated documents under `docs/benchmarks/` that carry superseded content
get a `CORRECTION` or `STATUS` header pointing here.
