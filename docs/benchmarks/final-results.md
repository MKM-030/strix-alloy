# final-results.md — handover v2 progress (2026-09-15)

Scope: this session executed the v2 handover's **Priority 1 (A0–A2)** and **Priority 2 (B1–B2)**, plus
the cheap read-only Triage (D/KVA) and the required artifact set. It did **not** start the product
Cloud/FiveM, did not push, did not change boot/firmware, and did not run two 177B instances at once.

## Headline results

1. **A0 — serial vs wide-verify is NOT token-identical, and the cause is the dense decode regime.**
   At short context (`n_kv ≤ indexer_top_k + ratio − 1` = 2051, dense) the speculative path diverges
   from serial greedy; at long context (sparse) it matches for all 120 tokens **even at a 0.018-nat
   top1–top2 margin**. Every divergence is a near-tie where the spec arm emits **serial's #2 token**
   (gap 0.054–0.163 nats). Controls: serial-vs-serial is IDENTICAL (harness deterministic);
   graph-off is byte-identical (not graph capture); a second dense prompt diverges at a different
   position (content-dependent position, regime-dependent outcome). → `acceptance-width-report.md`.

2. **A1/A2 — the acceptance metric is frozen and explained.** Acceptance is **exact greedy
   token-equality**: a draft token is accepted iff it equals the target's argmax at that position
   (`common/sampler_sample_and_accept_n`). The reported number is **per-position survival**
   (`n_acc_tokens_per_pos[i]` increments for every `i < n_accepted`). No stochastic or approximate
   acceptance rule exists to tune. → `acceptance-metric-frozen-20260915.md`.

3. **B1 — the shared-MTP "large-ubatch load failure" is a `--fit on` preflight defect, reproduced.**
   With the shared head, `--fit on` cannot measure the sidecar standalone: it throws
   `qwen4exp requires ctx_other to be set`, fit logs *"fitting without it"*, and the draft context is
   **never counted** — at every ubatch (2048/8192/16384), so it is not ubatch-specific. Root cause is
   fork-specific (we borrow shared tensors via `ctx_other`, not upstream's `model_shared`). The older
   **Bug A does not reproduce** on the current binary. → `shared-mtp-fit-report.md`.

4. **B2 — candidate queue built; the top item is already in our tree.** `halo-box` PR26 (give MTP
   targets their recurrent rollback slots back) removes a second target forward pass on partial
   accepts; our fork **already contains it** (`common/common.h:394`) and it must be preserved.
   Ranked HIP candidates (PR28875 tiny-N MMVF, halo-box PR18 mmvf prefetch/wave, hyperconn fusion)
   are catalogued with mechanisms and applicability. → `source-manifest.md`, `patch-applicability.csv`.

5. **D (KVA) — not applicable and out of scope at the current priority.** Different architecture
   (27B/64-layer dense vs our 48-layer MoE) and a **prefill-only** technique; our decode is
   weight-bandwidth-bound. → `kva-relevance.md`.

6. **P3 (virtualization) — the lever is closed; no parameter changed.** Arm D is overridden by VBS;
   arm C breaks HIP device access entirely; WSL's IOMMU is virtual so a guest test proves nothing
   about the host. Read-only audit only. → `virtualization-audit.json`.

## What this changes for the plan

- **P1's "fix a verify bug first" branch does not apply.** Acceptance is measured against the
  wide-verify argmax and is self-consistent; the deviation from serial is confined to the dense regime
  at sub-0.2-nat positions, which are numerically unstable by construction. The live levers are draft
  quality and scheduling — not a correctness repair.
- **Keep `--fit off --load-mode none`** until the fit probe can pass the target context.
- **Protect PR26** across any future upstream merge — it is worth more than any single kernel micro-opt
  in our hot path.
- **Next decode work** should evaluate the smallest, most on-point matvec changes first
  (PR28875 tiny-N, halo-box PR18 `mmvf.cu`), and **audit** whether our HC blocks are already fused
  before porting `hyperconn.cu`.

## Open items carried forward

- **B3:** prefill vs depth — see the continuation section below; the gap is largely a depth artifact.
- **Is the LM head read 1× or 3× per round?** — resolved in the continuation section (1×).
- **Hyper-connection cost + activation/attention accounting** — resolved in the continuation section.
- **QSA top-k nondeterminism** (ggml-org issue #28497) — resolved in the continuation section.
- **Cleanup:** delete the two `Strix bench` BCD test entries (`windows-boot-ab.ps1 -RemoveAll`) —
  requires owner approval for the maintenance action.

## Continuation (autonomous): kernel work, byte accounting, prefill shape

After the artifacts above, work continued through the remaining plan items. Full detail in the linked
docs; results summarised here.

**Resolved questions.**

- **LM head is read 1× per forward.** `build_lora_mm(model.output, cur, ...)` runs once at the end of
  the graph (`src/models/qwen4exp.cpp:565`) over the last selected rows (`inp_out_ids`), and in the MTP
  head the `shared_head_head` path falls back to `model.output` once. The "1× or 3×" question is closed:
  1×. The draft-vocab trim (`d2t`/`t2d`) that shrinks that head was already tried — available, ~neutral.
- **Decode byte budget (`decode-byte-accounting-20260915.md`).** Exact GGUF census: a decode token reads
  **4.219 GB** — routed experts 31.5%, attention 29.6%, output head 12.3%, hyper-connection 8.7%, GDN
  7.8%, norms 6.0%, shared expert 3.2%, indexer 0.9%. Ideal at our 235.7 GB/s ceiling is 17.9 ms/token
  (~56 t/s); we run 35 t/s serial = **63% of the ceiling**. Combined with the earlier flat 53–59%
  byte-efficiency and flat round-cost-across-depth results, the loss is **uniform**, not concentrated —
  so no single component is the culprit. Hyper-connection weights are ~672 MB/token and irreducible.
- **QSA top-k (`qsa-topk-determinism-20260915.md`).** The selected **set** is deterministic; the
  **order** is not, because `top_k_parallel_radix_gather` assigns slots with `atomicAdd`. Benign for
  QSA (attention sums the set), but it means indexer output cannot be asserted bit-identical across
  runs — the same float-noise→discrete-choice class as the A0 finding.

**Kernel experiments — four run, four negatives (all reverted).**

| experiment | result | verdict |
| --- | ---: | --- |
| small-K MMVQ on RDNA3.5 (SixVolts class) | 28.73 vs 28.83 t/s | inert — gfx1151's RDNA2 table gives `nwarps=1`, so it can never trigger |
| RDNA3.0 parameter table on gfx1151 (`nwarps=8`) | **22.81 vs 28.75 t/s (−21%)** | strongly negative — the RDNA2 table is genuinely best for this part |
| `mmb_min_t` 512→128 for short prefills | ~0% change at every size | negative — short-prompt slowness is per-request overhead, not the MMB threshold |
| MMVF 4-deep prefetch (F32 router, `ncols_dst==1`) | single run +1.9%, **interleaved −0.9%** | negative — no effect at the ~2% scale; and it would not touch the 3-row verify anyway |

→ `mmvq-candidates-negative-20260915.md`, `mmb-min-t-short-prefill-20260915.md`,
`mmvf-prefetch-and-shadow-20260915.md`. Method: serial decode (no drafter) so kernel effect is separated
from acceptance. The MMVF case is the reason there is now an **interleaved A/B harness**
(`kernel-work/interleaved-ab.ps1`, alternating base/patch arms): a single 5-rep run has ±1% spread, the
same size as the effect being chased, and the single run falsely read +1.9% where the interleaved test
read −0.9%. Every experiment was reverted; the restored binary reproduced the baseline (29.39 vs 28.75
t/s, both inside the ±1% band).

Also closed without a build: the **Q6_K MMB bf16 shadow** does not add decode traffic — `output.weight`
is not shadow-eligible (`ne[1] > 32768`) and the shadow is only read inside the MMB path (`T >= 512`),
which decode never runs.

**Prefill (`prefill-vs-depth-20260915.md`).**

- **Prefill is strongly depth-dependent: 407 t/s @256 → 1021 @16k** (WSL down, which is mandatory — its
  absence corrupted three prior runs). So the "1035–1057 vs ilintar 1204" comparison was depth-mismatched;
  at matched 16k the gap is ~6% (vs their 1086 @40k), not 14–16%. Their residual edge is most likely the
  retained-PM4 runtime we cannot use.
- **MTP at large ubatch (`mtp-large-ubatch-bugA-stale-20260915.md`).** The old "-ub 2048 required with a
  draft" (Bug A) **does not reproduce**: ub 8192/16384 load *and* generate with MTP, identical
  acceptance, and prefill recovers **+18–25%** (778 → 970 t/s @16k). The `-ub 2048` restriction is lifted.

**Net state of the decode lever.** Every decode path examined this session — MMVQ tuning (two ways),
the indexer depth line, PLE staging (prior), hyper-connection launch fusion, the LM head, expert count —
is either already optimal or a minority of bytes, and the loss is uniform. **Decode is at its practical
limit for the current kernels**; further gains need a new quantized-matvec kernel that beats the
RDNA2-tuned one, which is a research project, not a tuning pass. The concrete, usable win this session
is the **MTP + large-ubatch prefill recovery**.

## Artifacts (docs/benchmarks/)

`acceptance-width-report.md`, `acceptance-metric-frozen-20260915.md`, `shared-mtp-fit-report.md`,
`source-manifest.md`, `patch-applicability.csv`, `kva-relevance.md`, `virtualization-audit.json`,
`measured-baseline.json`, `final-results.md`, `decode-byte-accounting-20260915.md`,
`mtp-large-ubatch-bugA-stale-20260915.md`, `mmvq-candidates-negative-20260915.md`,
`prefill-vs-depth-20260915.md`, `mmb-min-t-short-prefill-20260915.md`,
`qsa-topk-determinism-20260915.md`, `mmvf-prefetch-and-shadow-20260915.md`.

Scripts (kernel-work/): `width-equivalence.ps1`, `verify-width-equivalence.py`, `analyze-margins.py`,
`check-flip.py`, `dump-probs.py`, `gguf-census.py`, `gguf-vocab-lookup.py`,
`reproduce-b1-shared-mtp-fit.ps1`, `reproduce-b1-bugA.ps1`, `ub-mtp-sweep.ps1`, `decode-baseline.ps1`,
`prefill-shape-sweep.ps1`, `interleaved-ab.ps1`, `build-target.bat`, `byte-accounting.py`,
`dump-non-expert-tensors.py`, `decode-read-set.py`.

