# A1/A2 — What the MTP acceptance metric actually is (frozen, from source)

Date: 2026-09-15. Source: `~/strix-llama` (branch `win-native`, base `40a9f4d0`).
Handover v2 priority: **P1/A1 "freeze and explain the acceptance metric"**, **P1/A2
"check the actual acceptance algorithm"**. Both are now answered by reading the code,
no runtime experiment needed.

## A2 — the acceptance rule is exact greedy token-equality

The decision lives in `common/sampling.cpp:678`, `common_sampler_sample_and_accept_n()`,
called from `tools/server/server-context.cpp:4002`:

```cpp
for (; i < draft.size(); i++) {
    const llama_token id = common_sampler_sample(gsmpl, ctx, idxs[i], grammar_first);
    common_sampler_accept(gsmpl, id, true);
    result.push_back(id);
    if (draft[i] != id) {
        break;                       // <-- acceptance == EXACT TOKEN MATCH
    }
}
if (i == draft.size()) { /* all drafts matched -> sample one more (the bonus token) */ }
```

So with our production settings (`temperature 0`, `top_k 1`) the target sampler returns the
**argmax**, and a draft token is accepted **iff it equals the target's argmax** at that
position. There is no probabilistic / rejection-sampling rule in this path.

The draft side is also argmax: the MTP impl builds its sampler as
`top_k = 10` and takes `cur_p->data[0].id` (`common/speculative.cpp:1360-1366`). Top-k
filtering then renormalising does not change which token is the argmax, so the proposed
token is the **draft head's argmax**.

Consequence: at temperature 0, MTP acceptance is *exactly* the agreement rate between the
1-layer MTP head's argmax and the 48-layer target's argmax, along an already-accepted
prefix. `--spec-draft-p-min` and the draft `top_k=10` only decide *whether to propose* and
*when to stop proposing*; they do **not** change whether a proposal is accepted.

This deliberately reframes P1: raising acceptance means either
(a) making the MTP head's argmax agree more often (model/training), or
(b) removing a **verify-path inconsistency** so the target's argmax under wide verification
equals its argmax under serial decode (kernel/numerics — this is the A0 test), or
(c) reducing how often we burn a verify row on a low-agreement draft position (scheduling).

## A1 — the reported numbers are per-position survival rates

Accounting is in `common/speculative.cpp:2894` (`common_speculative_accept`) and printed by
`common_speculative_print_stats()` (`:2966`):

```cpp
for (size_t i = 0; i < n_accepted; ++i) impl->n_acc_tokens_per_pos[i]++;   // prefix-style
if (n_accepted > 0) { impl->n_acc_drafts++; impl->n_acc_tokens += n_accepted; }
...
mean acc len = 1.0 + n_acc_tokens / n_call_accept
acc rate/pos[i] = n_acc_tokens_per_pos[i] / n_call_accept
```

Because the counter increments for **every** `i < n_accepted`, `acc rate/pos[i]` is the
fraction of rounds in which **at least** the first `i+1` draft tokens were accepted — i.e.
the **survival rate at draft position i**. So our reported
`acceptance 62.5% / 54.5% / 48.8%` at 1k/8k/16k is the position-0 survival (the first draft
token matches the target argmax), and my earlier instrumented `prefix survival per draft
position` line is the same quantity per position.

The server-side counter that feeds timings is separate and consistent
(`server-context.cpp:4050-4076`): `n_accepted = ids.size() - 1`, decremented by 1 when
`slot.spec_is_replay`, then `n_draft_accepted += n_accepted`, `n_draft_verif_steps++`.

## What this changes for P1

- **A1 is closed**: the metric is frozen and now fully explained — per-position argmax
  agreement, no hidden stochasticity, no sampler-dependent distortion.
- **A2 is closed**: the algorithm is hard exact-match; there is no approximate/probabilistic
  acceptance to tune, and therefore no "acceptance-ratio knob" to exploit.
- The only in-scope levers that do not touch the target model are:
  1. the A0 verify-path consistency question (wide verify vs serial argmax), and
  2. draft scheduling (which positions to spend verify rows on), and
  3. MTP head quality (training) — explicitly out of scope for "without changing the
     target model" only in the sense that the *target* is untouched; the head may change.

## Still-open sub-question recorded (not yet measured)

Whether the target's argmax is **identical** under 1-row serial decode vs 3-row verification.
That is exactly the A0 test now running. A difference is not automatically a bug: the QSA
indexer's flattened width is `4 x rows`, so serial (ne11=4) and n-max 2 (ne11=12) select
rows with **different kernel families** (`MMVF_MAX_BATCH_SIZE = 8`), and the indexer's
top-k selection is a **discrete** decision — near-tie indexer scores can flip which 2048
keys are attended, which amplifies float noise into a different argmax. That is the most
plausible concrete failure mode to look for, ahead of generic GEMM reduction-order noise.
