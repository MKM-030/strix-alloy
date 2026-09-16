# Draft-head training plan (lever "b"), grounded in the measured MTP cost model (2026-09-15)

Companion to `frspec-head-fixed-and-draft-census-20260915.md`. This is the plan the founder asked for
after pointing at `MakazhanAlpamys/Soup` ("for finetuning once we have a plan… please have a look").

## 1. What the A/B just told us about where draft time actually goes

From the measured points (PROJFIX, ub 2048, 1k prompt) we can fit the draft/target cost ratio `r`:

| config | decode t/s | tokens/round | model `S = (1+A)/(k·r+1)` | implied `r` |
| --- | ---: | ---: | --- | ---: |
| no MTP | 30.1 | 1.00 | 1.00 | — |
| MTP n-max 1 (α=0.747) | 34.16 | 1.75 | 1.135 | **0.54** |
| MTP n-max 2 (A=1.24) | 35.45 | 2.24 | 1.178 | **0.45** |

**Fitted `r ≈ 0.47 (0.45–0.54)` — SUPERSEDED, see the correction below.** `r = ((1+A_k)/S_k − 1)/k` with
`S_k = decode_tps(k)/decode_tps(0)`:

| prompt | from n-max 1 | from n-max 2 |
| ---: | ---: | ---: |
| 1,024 | 0.499 | 0.445 |
| 8,192 | 0.538 | 0.452 |

> **CORRECTION (2026-09-15 evening, verified).** This `r` was **fitted from throughput, not measured**, and
> it is **wrong on the magnitude**. The fork already accumulates the real phase timers (`t_draft_us` etc.),
> printed at trace verbosity; a direct measurement gives **draft = 16.1% of the decode wall, accept = 0.01%,
> residual (target verify + host) = 83.9%** — i.e. **draft : residual ≈ 0.19, not 0.47**. A constant-cost fit
> absorbed the width-dependent verify cost into the apparent draft cost, exactly as the frontier review
> predicted. Full numbers and consequences: `review-corrections-and-round-timing-20260915.md`. The
> *qualitative* conclusion below still holds (bytes are not the draft bottleneck), but the **16% draft share
> means a cheaper drafter cannot reach 42 t/s** — acceptance and verification are the larger levers.

This is the key result, and it explains the FR-Spec A/B: cutting the draft head 521→178 MB (−40% of
draft-step *bytes*) bought only **+2%** decode. **Bytes are not the draft bottleneck; per-step overhead
and acceptance are.**

The speedup law we now optimize:

```
S(k, α) = (1 + A(k,α)) / (k·r + 1),     r ≈ 0.5
```

## 2. The two levers, quantified

**Lever A — raise acceptance (train a head fitted to PROJFIX).**
- Current: α₁=0.747 (n1), A=1.24 (n2). Head is unsloth's, fitted to *their* trunk/quant.
- **Corrected arithmetic** (the review is right; my earlier "+21%" was wrong). At n-max 2 with equal
  conditional acceptance: `(1+0.9+0.81)/(1+0.75+0.5625) = 1.172` → **+17.2%**; at n-max 1, `1.9/1.75` →
  **+8.6%**. Not 21%.
- The fork now reports **per-position acceptance** (measured: pos-1 0.55, pos-2 0.24), so this lever has a
  direct instrument, not just an aggregate.

**Lever B — cut the draft step.**
- **Corrected:** the fitted `r=0.5` is superseded by direct timing — **draft is only ~16% of the decode
  wall**. So even making the drafter *free* caps out near **31 t/s**, not 43. Halving a fixed component
  worth 70% of a 16% share is worth only **+5.5%**.
- Therefore B is **not** the bigger lever. My earlier ranking (`B > A`) was based on the bad `r`.

**Corrected ranking: A (acceptance) > B (draft cost) ≫ the byte tricks already tried.** And per the review,
the largest single bucket is neither — it is the **~84% target-verify + host residual**, which needs its own
attribution before either training lever is funded. See `review-corrections-and-round-timing-20260915.md`.

## 3. Plan

### Phase 0 — decide the target (0.5 day, no GPU)
Confirm against the founder which we pursue first. Recommendation: **B, with A as a cheap byproduct** —
training a new head is required for either, and a head-only harness can emit both a
higher-acceptance full-vocab head (A) and a shrunk-expert head (B) from the same run.

### Phase 1 — build the training-data harness (1–2 days, the real work)
`llama.cpp` has **no MTP-head training path**; Soup is a *general* SFT/DPO trainer, not an MTP trainer.
The bulk of the effort is a harness, and it must reproduce the head's exact I/O contract, which the fork
already documents in `qwen4exp.cpp`:

- Inputs to the head per position: the token embedding and the trunk's **last-layer hidden** (the head
  concatenates them via `eh_proj` after `hc_head_*` mixing).
- Output: logits over the (draft or full) vocab for the **next** token.
- So we need teacher-forced `(embed_t, hidden_t) → token_{t+1}` triples from the PROJFIX trunk.

Two ways to get them, in preference order:
1. **Small patch to `llama-server`** to dump per-position last-layer hidden states for a corpus
   (`llama_batch` already carries them; add a `--dump-hidden FILE` path). Lowest risk, exact contract.
2. Teacher-forcing through the existing MTP graph and capturing its `cur` before the head. More fragile.

Data: a natural-language corpus from the repo + a public instruct set (documentation, code, chat), long
enough to cover the context depths we care about. Size: ~10–50 M tokens is a reasonable first target for a
3 GB head.

### Phase 2 — train (1–2 days + GPU time)
**Design changes from the frontier review (accepted):**

1. **Start with a small adaptation of the existing head, not a retrain.** Train the input/hidden fusion and
   selected normalization/projection adapters first; add FFN adapters only if needed. Do **not** initially
   retrain the whole MoE or change its expert count. Objective: higher accepted-prefix yield at unchanged
   inference cost.
2. **Train against the deployed quantized trunk.** Keep the trunk, its borrowed input embedding and its
   full 248,320-vocab output projection **frozen** (we confirmed the shared head borrows the trunk
   projection, so that projection is not ours to retrain cheaply).
3. **Loss**: next-token CE against quantized-teacher outputs, optionally plus teacher-distribution
   distillation. **Evaluate the exported/quantized head, not the training-precision version.**
4. **Include rollout-conditioned training.** Teacher-forced features alone do not represent later drafting
   steps where the head consumes its own predictions — train/evaluate short rollouts through the real
   inference transition (EAGLE-3's training-time-test is the relevant precedent; its speedups are not
   transferable to us).
5. **Split evaluation by document/repo/task**, and include the code/tool-call/prose/multilingual mix we
   actually serve. A head that only gains acceptance on training-style prose is not useful.
6. **Data pipeline: chunked and streamed.** A 160 MiB dump is 8192 rows; a million rows of *features* is
   **20.5 GB**, and full fp16 *logits* for a million tokens would be **497 GB**. Store features chunked and
   compute the full-vocab loss streamed — never materialise a dense logit dataset.
7. Before *any* architecture change (lever B), **benchmark a shape-faithful candidate with the unchanged
   full projection** and apply the break-even rule: a head that cuts round time 10% must retain >90% of
   emitted-token yield to win; one that saves 3% cannot tolerate an acceptance drop.

- **Init** from the shared Q8_0 head we already run, so we adapt rather than train from scratch.
- **Soup** is usable for its PEFT/QLoRA + **layer-streaming** (keep the frozen trunk out of VRAM) — that
  matters because a head fine-tune plus activations must fit the 96 GB carve alongside the trunk.
- Reuse `convert-frspec-head.py`'s GGUF writer (now alignment-correct) to emit the trained head back to
  the fork's tensor names.

### Phase 3 — evaluate with the harness we already have (0.5 day)
`ab-heads.ps1` + `fnbench.py` already produce the exact acceptance + decode/prefill table. Acceptance is
the primary metric; decode t/s is the payoff. Because the fork now reports **per-position acceptance**, use
that too — position 2 (24%) is where the depth yield is lost, and it is the number a better head must move.
Re-run the same A/B so results are directly comparable.

### Phase 4 — if B is pursued: architecture shrink
Reduce the head's `ffn_*_exps` (fewer experts, wider top-k, or a dense low-rank FFN) and retrain. **Note
this is now the lower-priority lever** — with the draft at ~16% of the wall, the win cap is ~+5.5% for
halving the fixed component, so demonstrate the latency advantage with a shape-faithful candidate before
any serious training.

## 4. Risks and honest bounds

- **Harness correctness is the project, and tensor shapes are not enough.** A stateless row-wise harness
  can reproduce dimensions while failing to reproduce the computation: the MTP block has its own
  attention/KV path, position inputs, and per-stream hyper-connection processing. The gate is therefore
  **sequence-level**: first-step logits, top-token agreement, positional alignment, chunk boundaries, and
  short autoregressive rollouts of the *untouched* head against the live inference path — plus rejection
  and catch-up behaviour in the deployed runtime. **No training until that agrees.**
- **The box is shared.** One heavy job at a time; a training run and a benchmark server must not overlap.
- **No train→quant→load loop exists yet** for this head; Phase 1+2 build it. Budget accordingly.
- **Lever B needs loader work** (a head with a different expert count is not a tensor swap).
- **Acceptance gains are not guaranteed** to transfer to decode 1:1; the corrected model (+8.6% at depth 1,
  +17.2% at depth 2 for 0.75→0.90) predicts direction, and Phase 3 measures truth.

## 5. Immediate next actions

1. **Attribute the 84% verify+host residual first** (`review-corrections-and-round-timing-20260915.md`) —
   the review's #1, and the only way to know whether a head or a kernel is the right investment.
2. **Prove sequence-level parity of the untouched head** through the harness before any training.
3. Then a small adapter adaptation (Phase 2 item 1), evaluated exported+quantized.
4. The *cheap* decode levers stay exhausted: n-max 1–2, FR-Spec head, n-gram cascade, p-min, PR #28118,
   standalone-vs-shared — all measured, all ≤ noise. Do not re-run them.
