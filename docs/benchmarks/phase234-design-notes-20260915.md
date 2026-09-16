# Phase 2/3/4 design notes: drafters, vocab/SSD, NPU (2026-09-15)

## Phase 2 — sequential vs parallel drafters

**What the code actually does** (`common/speculative.cpp`): implementations are built in a fixed
**priority order** and each `draft()` call runs them in sequence over the same `dparams`; the first
implementation that returns a draft sets `dp.drafting = false`, so later ones are skipped for that
sequence on that step:

```
NGRAM_SIMPLE → NGRAM_MAP_K → NGRAM_MAP_K4V → NGRAM_MOD → NGRAM_CACHE
             → DRAFT_SIMPLE → EAGLE3 → MTP → DFLASH → DSPARK
```

So the existing design is **cascading, not parallel**: cheap table-based drafters get first refusal,
and the expensive model-based ones only run when the cheap ones find nothing. For our case that is the
right shape — an n-gram hit costs a table read and no weights at all.

**Can they be parallel?** Not meaningfully for one sequence, and for a good reason: each drafter's
output feeds the *same* verification, and speculative decoding's gain comes from one verify pass
accepting many tokens. Two drafters proposing independently would need two verify passes or a merge
step, and the merge would have to reconcile different token sequences. **The win is the cascade**, not
parallelism. What *is* parallelizable is what the NPU idea below targets: the n-gram lookup can run
concurrently with the MTP draft for the *next* step, hiding its latency rather than competing with it.

**Concrete Phase 2 experiment (cheap, no code):** today we pass only `--spec-type draft-mtp`. Adding a
lookup drafter ahead of it, e.g.

```
--spec-type ngram-simple --spec-type draft-mtp --spec-num-draft-max 4
```

makes `NGRAM_SIMPLE` try first. On repetitive text (code, tool output, JSON) that alone can carry most
of the draft at zero weight cost; on prose it falls through to MTP. This is a command-line change we can
measure immediately, and it is exactly the "several drafters" idea — the fork just orders them itself.

### MEASURED: the cascade makes it WORSE (and why)

Tested on the corrected 96 GB carve, PROJFIX, ub 2048, ctx 32768:

| config | decode @1k | @8k | @16k | acceptance @1k / @8k / @16k |
| --- | ---: | ---: | ---: | --- |
| `--spec-type draft-mtp` (n-max 2) | **35.1** | 30.3 | 33.0 | 62% / 51% / 60% |
| `--spec-type ngram-simple --spec-type draft-mtp` (n-max 4) | **28.5** | 18.2 | 24.9 | **42% / 26% / 36%** |

Enabling the lookup ahead of MTP **reduced both acceptance and throughput**. The mechanism is visible in
the numbers: acceptance fell from 62% to 42% while the draft rate rose (140 generated vs 228 at the same
token count). Because impls run in priority order and the first non-empty draft wins, the n-gram drafter
takes first refusal and **MTP never runs** — so the verify pass is fed lower-quality drafts than MTP would
have produced. The cascade only helps if the cheap stage is *more* accurate than the expensive one, which
for an MTP head on this model it is not.

**Conclusion: do not chain a lookup drafter ahead of MTP on this model.** The useful cascade direction
would be the reverse (MTP first, lookup only when MTP abstains), which is not how the priority list is
built — it would need a source change. That is a concrete, bounded patch if we want it, but the expected
gain is small: MTP already produces a draft nearly every step at 60% acceptance.

This also **weakens the NPU idea**: the lookup drafter is not a win even when it is free of weight cost,
so moving it to the NPU cannot help either.

## Phase 3 — vocab compression and SSD-backed lookup

Two separable ideas, and the numbers are different for each.

**(a) The n-gram/PLE table (26.8 GiB) — SSD-streaming is already what happens, and compressing it is not
free.** Measured facts: the table is `per_layer_token_embd`, IQ4_NL, 320M rows × 160 dim, and it is
**already paged from disk**, never resident (`--load-mode none` + `--lazy-mode on-direct`). Per decode
step the model reads only `ngram_size × heads_per_ngram` rows ≈ **a few KB**, and the QSA path keeps the
KV read at ~50 MB/token regardless of depth. So:
- Streaming is the status quo, not a new idea — and the cost is **latency**, not bandwidth (that was the
  measured 5.2 ms hostgap growth from p0 → 2k ctx).
- Halogen 0.6.3 fixed exactly this on their side by batching the row reads (32k first prompt: 46–52 s →
  1.3 s). Our equivalent is the `--lazy-mode on-direct` reader, and the open question is whether it
  batches. **The win here is a prefetch/cache, not a smaller table.**
- Could the table be compressed further? It is already 4.5 bpw of a 160-wide embedding; the rows are
  random-access, so re-quantizing to ~3 bpw would save ~8 GiB of disk and nothing of RAM (it is not
  resident) while risking quality on the model's knowledge injection. **Not worth it.**

**(b) The vocabularies (248,320 × 2560 output head = 0.49 GiB Q6_K; draft head 65k-vocab = 3.8× smaller
projection).** This one *is* worth attacking, and it is the FR-Spec idea: the draft only needs to score
a **subset** of the vocabulary, so its output projection shrinks 3.8×. That is real decode-side work
saved per draft step, and it is a *compute/bandwidth* saving on the draft, not on the target.
- A separate SSD-backed lookup for the head makes no sense: the head is read **in full every token**, so
  it must be resident; splitting it to disk would add a stall per token.
- Compressing the head (Q6_K → lower) trades quality for ~0.3 GiB of RAM. Irrelevant at 96 GB of pool.

**Verdict:** the FR-Spec-style trimmed draft vocab is the real Phase 3 lever; table compression and
SSD-splitting are not.

## Phase 4 — NPU

**Why it is plausible:** the NPU (XDNA2) shares the same LPDDR5X as the iGPU, so if it could read the
same buffers, offloading a *lookup* to it would add no bandwidth. The n-gram drafter in Phase 2 is the
best candidate: it is a table lookup with no floating-point math, which is exactly what an NPU is good
at, and it runs on the critical path of every decode step.

**Why it is hard, stated plainly:**
1. llama.cpp has no NPU backend; the NPU is driven through XRT/ONNX (Ryzen AI SW) or VitisAI, separate
   from HIP.
2. Sharing one allocation across a HIP context and an XRT context is not a supported path; each
   allocates from its own arena. "Same physical RAM" is true, "same address" is not, so a copy or a
   shared-memory import would be needed — and a per-step copy of the draft rows would eat the benefit.
3. The iGPU would have to wait on the NPU each step (or run ahead), and the synchronisation cost is
   likely larger than the ~0.1–1 ms a lookup costs today.

**Bounded Phase 4 experiment:** measure what the n-gram drafter actually costs, in isolation, before
writing any NPU code. If it is <1 ms/token, the NPU cannot pay for its own sync and the idea dies on
evidence rather than on opinion. If it is several ms, the NPU becomes worth a prototype.
