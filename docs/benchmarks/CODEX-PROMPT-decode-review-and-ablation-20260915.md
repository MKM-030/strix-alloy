# Codex prompt — decode bottleneck review + ablation plan (2026-09-15)

Paste everything below the line into Codex. It is self-contained: all numbers are measured on one
machine, and every claim that was **retracted** is marked as such so you do not build on it.

---

You are a GPU-kernel and LLM-inference performance engineer. Review the measurement record below and
produce a concrete plan. I will tell you explicitly which numbers are trustworthy and which I have
withdrawn — **do not re-derive conclusions from the withdrawn ones.**

## 1. Hardware and stack (fixed)

- **AMD Ryzen AI Max+ 395**, Radeon 8060S iGPU (gfx1151, RDNA3.5, **wave32**, 40 CU), 128 GB LPDDR5X
  **unified** memory (~200–240 GB/s measured range), **96 GB dedicated carve**.
- Windows 11 + WSL2 over `/dev/dxg` — **no `/dev/kfd`, no PM4 replay**. Our fast path is **native
  Windows**.
- Native build: **TheRock 10.2 SDK, clang 24.0.0git, `GGML_HIP=ON`**. The SDK ships **no profiler**
  (no `rocprof`, `rocprofv2`, `rocprofv3`, `rocprofiler-sdk`).
- Model: **Qwen3.8-Flash-Next**, 177 B MoE, ~6 B active: 48 layers, 512 routed experts (top-k=10) +
  1 shared expert, expert FFN width 640, `n_embd` 2560, **hyper-connections** (4 streams, low-rank 320),
  hybrid **GatedDeltaNet** + full attention every 4th layer, **QSA sparse lightning-indexer**
  (top_k 2048), and a **~27 GiB PLE n-gram embedding table that is paged from disk, not resident**.
- Quant: "PROJFIX" = IQ4_NL where quality holds, 93 GiB on disk. MTP draft head = shared Q8_0 sidecar
  that **borrows the trunk's 248,320-row LM head** (it has no `output.weight` of its own).
- All runs: single instance on the box, WSL shut down, page cache warmed (rep ≥ 1).

## 2. Measured production results (TRUSTWORTHY)

Prefill and decode, PROJFIX, MTP `--spec-draft-n-max 2`, ub 2048 for decode / ub 16384 for prefill:

| prompt | prefill (t/s) | decode (t/s) | MTP acceptance |
| ---: | ---: | ---: | ---: |
| 1,024 | 698–700 | **34.44** | 62.5% (70/112) |
| 8,192 | 984–991 | 29.4–29.6 | 54.5% (66/121) |
| 16,384 | **1,031–1,034** | 28.1–28.8 | 48.8% (62/127) |

Best observed: **1,034 t/s prefill @16k**, **34.4 t/s decode @1k**.

## 3. Phase budget (TRUSTWORTHY)

Direct wall-clock measurement around boundaries that already synchronize (target `llama_decode` +
`llama_synchronize` at the sampling point; the fork's own spec timers for draft/accept):

| phase | share of decode wall |
| --- | ---: |
| **target verify (the forward pass)** | **~80%** |
| **draft (the MTP head)** | **~16%** |
| accept | ~0.01% |

**Graphs A/B, same binary/model/session:** graphs **ON** = 35 t/s (28.6 ms/token); graphs **OFF** =
10.7 t/s (93.5 ms/token). So **graphs are worth ~65 ms/token (~70%)** and the production path is
**already dispatch-free**. Consequence: the ~80% above is **real GPU work, not launch overhead.**

## 4. MTP economics (TRUSTWORTHY, from one clean dataset)

| prompt | serial | n-max 1 | n-max 2 |
| ---: | ---: | ---: | ---: |
| 1,024 | 29.93 | 34.87 (+16.5%) | **35.47 (+18.5%)** |
| 8,192 | 28.60 | **30.27 (+5.8%)** | 30.21 (+5.6%) |

**MTP's value is strongly depth-dependent** — ~+18% at 1k, ~+6% at 8k — and n-max 2 stops beating
n-max 1 once acceptance falls to ~50%. Consistent with the depth sweep: n-max 3→8 monotonically worse
(acceptance 86% → 32%).

A third-party statement we independently reproduce in direction: the Halogen author says *"the
sparsity that makes decode cheap is what makes a wide verify expensive; that is the architectural
fact, not a tuning gap."*

## 5. RETRACTED — do not use these

I am listing these so you do not reason from them. Each was withdrawn after an independent check.

1. **"Draft/target step cost ratio r ≈ 0.47."** Fitted from throughput, not measured. Direct timing
   shows draft is **16%** of the wall, not ~half. Withdrawn.
2. **"CPY 20.3% + CONT 16.6% = 37% of GPU time is data movement; MUL_MAT_ID only 4.2%."** Withdrawn.
   (See §6 for why the instrumentation cannot support any composition claim here.)
3. **A later composition run reported as valid:** MUL_MAT 56.1%, SCALE 11.5%, RMS_NORM 10.2%,
   GET_ROWS 8.8%, CONT 6.1%, CPY 4.4%. **Also withdrawn.** Its own numbers disqualify it: the timer
   accounted for only **0.06× of measured decode wall** (i.e. 6% of the time), and `graphs reused`
   was non-zero despite `GGML_CUDA_DISABLE_GRAPHS=1`, so the execution mode is not determinable.
4. An earlier transcription of "30.2 t/s decode @16k" — the correct figure is **32.8 t/s** (that was
   the 8k number). Corrected.

## 6. Per-op composition is currently UNMEASURABLE on this stack — proven, three ways

Do not propose re-running these; they are closed with evidence.

| method | why it fails |
| --- | --- |
| **in-graph GPU events** (`LLAMA_OP_TIMING=2`) | `hipEventElapsedTime()` returns **400 / `hipErrorInvalidResourceHandle`** for captured events — reproduced even when the events are created **outside** the capture region from a pre-capture pool. |
| **capture-time CPU wall-clock** | during stream capture the GPU **does not execute**; `cudaStreamBeginCapture` only records. Measuring there gives enqueue/record cost, not GPU time. |
| **eager (non-graph) warmup evals** | graphs are warmed up **at model load**, so by inference time every eval is a pure replay and the eager path never runs again. |
| **vendor profiler** | not shipped in the TheRock Windows SDK (verified). |

The instrument that *would* answer this (`rocprofv3` / `rocprofiler-sdk` on Linux) requires a
bare-metal Linux host, which we do not have.

**Therefore: the honest state is that the target forward pass is ~80% of decode and all of prefill,
but what is inside that 80% is unmeasured.**

## 7. Negative results (all measured — do not re-propose)

| lever | result |
| --- | --- |
| `--spec-draft-n-max` 3–8 | monotonically **worse**; acceptance collapse 86% → 32% |
| n-gram lookup *ahead* of MTP | **worse** (42% vs 62% acceptance) |
| device-resident spec checkpoints (PR #28118) | **~0%** (branch already uses `rs_rollback`) |
| `--spec-draft-p-min 0.75` | **0%** |
| standalone vs shared MTP head | **0%** |
| FR-Spec trimmed 65k-vocab head (own smaller LM head) | **a wash**: +2% (n-max 2), −4% (n-max 1); costs ~4 pts acceptance |
| Vulkan `SHMEM_STRIDE_PAD` 4→6 (llama.cpp PR #28941) | **CLOSED by its author as a dead end** (value not 16-byte aligned; `{0,4,8,12}` gave no gain) — and Vulkan-only, so it could not have addressed our HIP gap |
| `amd_iommu=off` | **Linux-only**; source's own MoE-on-ROCm figure was **1.8–3.2%**. Windows has no equivalent. |
| Windows "no hypervisor" boot | **blocked by VBS** — the test entry booted with `hypervisorlaunchtype Off` and `vsmlaunchtype Off`, yet `HypervisorPresent = True` because `RequiredSecurityProperties` includes base virtualization. VBS cannot run without the hypervisor. |
| rebasing onto ilintar's latest (`40a9f4d0`) | **neutral on speed**; its value was removing 68 env gates (tuned defaults now compiled in) |

## 8. External references (third-party, not ours)

- **ilintar** (published): **1204 t/s prefill @0 depth**, 1086 @40k, **26.3 t/s decode** — ub 16384 as
  one batch, **retained-PM4 runtime**, **no MTP**.
- **Halogen** (closed engine): ~**42 t/s** decode; author states decode is at the hardware wall.
- **olliehm** Windows port: 964–1045 prefill, ~35 t/s decode with device-checkpoint MTP.

So: our decode (34.4) beats ilintar's published decode (26.3) because we run MTP and they do not; our
prefill (1,034) trails theirs (1,204) — plausibly the retained-PM4 runtime and their single-batch shape.

## 9. My current hypothesis and the idea I want you to develop

**Hypothesis:** since the production path is dispatch-free (graphs) and ~80% of decode is the target
forward pass, the only remaining decode levers are (a) *how much work the forward pass does per token*
and (b) *acceptance* (which reduces how many forward passes per emitted token). Everything at the CLI
level is exhausted.

**Idea to develop — structured ablation instead of profiling:**
Since per-op timers are unavailable, attribute cost by **size, on the production graphs-on build**.
Form a decision rule: *if disabling component X changes throughput by less than some threshold, X is
not the problem.* Concretely, I want an ablation matrix over components that plausibly dominate the
forward pass:

- the **PLE gather path** (27 GiB table, `get_rows`, per-layer embedding),
- the **QSA lightning-indexer** (top_k 2048 scoring/selection),
- the **GQA/attention path** (12 full-attention layers),
- the **GatedDeltaNet recurrence** (36 layers),
- the **MoE routing + expert GEMV** (`mul_mat_id`, top-k 10 of 512),
- the **MTP block itself** (16% by direct measurement — the calibration point),
- and **context depth** as a factor (QSA overhead should grow with depth; weights should not).

For each: how do I disable/shrink it *without invalidating the run*, what is the smallest faithful
change, and what throughput delta would be attributable? Note we must not corrupt output — a
measurement is only usable if the model still generates coherently, or if we accept a deliberately
degraded variant and say so.

## 10. What I want from you

1. **Challenge §3 and §4.** Is "80% is the target forward pass" actually informative, or is it
   tautological (of course the target dominates when the drafter is small)? What *would* be a
   falsifiable decomposition given no profiler?
2. **Design the ablation matrix concretely.** For each component in §9: the exact mechanism to
   disable/shrink it in a llama.cpp-family HIP build, the expected direction and rough magnitude, and
   which confounds could fake the result. Rank by (information gained / effort). Flag any ablation that
   would be invalid rather than merely noisy.
3. **Sanity-check the ceiling arithmetic.** Active weight payload is **4.254 GB/token** (dense/other
   2.927 + routed experts 1.327, from a tensor census); 200–240 GB/s gives a **serial ceiling of
   47–56 t/s**. We decode at 34.4 t/s with MTP. Does the remaining gap look like acceptance, the
   forward pass, or something else — and what measurement distinguishes them?
4. **Attack the prefill gap.** We are at 1,034 vs ilintar's 1,204 (a 14% gap). We already run their
   kernels. Is retained-PM4 command lists the whole story, or is there a batch/ubatch, memory-placement
   or attention-path cause we can test more cheaply?
5. **Tell me what I am wrong about.** Specifically: is "wide verify is fundamentally expensive on a
   512-expert MoE with top-10 routing" correct, or is there a verification scheme that avoids the
   sparsity cost (expert grouping, block/tree proposals, shared-dense reuse)?

Constraints: repository-only work on a single shared Windows box; no paid APIs, no cloud, no product
lifecycle changes; a second session may also be using the machine, so one heavy job at a time.
Give concrete next experiments ranked by information-per-hour, with the discriminating measurement for
each, and state your uncertainty explicitly.
