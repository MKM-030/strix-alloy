# Measured decode phase breakdown + verification economics (2026-09-15)

Direct, instrumented measurement (no fitted model). PROJFIX, ub 2048, 8192-token prompt, generation-gated
counters, target verify = wall clock of `llama_decode(ctx_tgt) + llama_synchronize` at the sampling
boundary (the sync is inside the batch that carries outputs, so this *is* the forward pass plus its wait).

## Phase breakdown of the decode wall

| phase | share of decode wall | source |
| --- | ---: | --- |
| **target verify** (`tgt_decode`) | **~80%** | server phase timer, consistent across 3 runs |
| **draft** (`t_draft_us`) | **~16%** | fork's own spec statistics (738.0 ms / 4591 ms at n-max 2) |
| accept (`t_accept_us`) | 0.01% | fork's own spec statistics (0.354 ms) |
| begin (refresh) | ~0% | fork's own spec statistics (0.004 ms) |
| spec catch-up + host misc | remainder | see caveat |

**The residual I earlier called "target verify + host" is essentially all target verify.** There is no large
mysterious host-wait bucket: the GPU forward pass for the verification batch is simply ~80% of the time.

*Caveat (honest):* the `spec_catchup` counter over-counts — 46 calls for 41 rounds — because some
prefill-phase calls still slip past the gate. Its per-call figure (~5 ms) is therefore an upper bound and
likely mostly the 5 prefill calls. The **target-verify and draft shares are solid**; the catch-up share is
"small, exact split pending one more gate fix".

## The economics — corrected, from ONE clean dataset

> **Correction.** An earlier version of this table mixed a `-lv 4` instrumented run's ms/round with a clean
> run's serial baseline and reported +14.8% / +11.3%. That was wrong. Phase **ratios** (verify ~80%, draft
> ~16%) come from the instrumented run and are robust; **throughput** must come from the clean runs, because
> `-lv 4` logging perturbs both speed and acceptance. Redone entirely from `r-sweep.json` (reps 1–3):

| prompt | config | t/s | ms/token | tokens/round | gain vs serial |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1k | serial | 29.93 | 33.41 | 1.00 | — |
| 1k | MTP n-max 1 | 34.87 | 28.68 | 1.75 | **+16.5%** |
| 1k | MTP n-max 2 | 35.47 | 28.20 | 2.26 | **+18.5%** |
| 8k | serial | 28.60 | 34.96 | 1.00 | — |
| 8k | MTP n-max 1 | 30.27 | 33.03 | 1.64 | **+5.8%** |
| 8k | MTP n-max 2 | 30.21 | 33.10 | 2.02 | **+5.6%** |

**So MTP's value is strongly depth-dependent: ~+17% at 1k, only ~+6% at 8k, and n-max 2 stops beating
n-max 1 once acceptance is ~50%.** That matches the n-max sweep (shallow optimal, deeper monotone worse) and
is the same phenomenon as the marginal-row analysis below.

### Why, given the phase split

At 8k, a n-max-1 round costs ~54 ms (33.03 ms/token × 1.64 tokens) of which ~16% is draft and ~80% verify.
The 2-row verify is ~45 ms against a 35 ms single-row serial pass — i.e. **the second row costs only ~10 ms
because it shares expert work (2 rows for 1.29× the cost of 1)**. But the *draft* is what eats the benefit:
it is 16% of the round and produces no accepted token on its own. The net is +5.8%, not the +30% the row
amortization alone would suggest.

**Marginal row, n-max 1 → n-max 2 at 8k:** +0.38 tokens for +0.07 ms/token — a wash. At 1k it is clearly
positive because acceptance is high (75%), so the second row is cheap relative to the tokens it adds.

This is the quantitative form of the Halogen author's line:

> "The sparsity that makes decode cheap is what makes a wide verify expensive; that is the architectural
> fact, not a tuning gap."

And it is **also** why our n-max sweep was monotone: each extra row is a break-even-to-negative purchase at
these acceptances, and at n-max 4+ the acceptance collapse (86% → 32%) makes it firmly negative.

## What this means for the levers — corrected again, and this time measured

1. **The draft head is not the lever.** Draft is 16% of the wall, and even a *free* drafter cannot exceed
   ~+19% (1 / 0.84). My earlier `r≈0.47` made it look like half — the direct measurement says it is not.
   A cheaper/smaller head cannot move decode meaningfully. **This retires lever B.**
2. **The target forward pass is the #1 lever — and it is the same work as prefill.** Verification is ~80%
   of the decode wall and is literally the forward pass the prefill path runs. A faster target forward pass
   improves *both*, which is why the boot experiment (testing whether hypervisor/IOMMU overhead is real) is
   the right next test, and why the retained-PM4 runtime is the biggest single item.
3. **Acceptance is #2** — it is what raises tokens/round, which is what makes the row amortization pay.
   Compare 1k (+18.5%) with 8k (+5.6%): same kernels, the difference is acceptance. The fork exposes
   per-position acceptance (pos-1 55%, pos-2 24%), so pos-2 is the target.
4. **A cheaper verification batch is a real but bounded lever** — the 2-row-for-1.29× amortization is
   already happening; grouping rows by expert could extend it, but the ceiling is small.

## Ranked recommendation (measured, replacing the earlier fitted-model ranking)

| rank | investment | why |
| --- | --- | --- |
| **1** | **Target forward-pass cost** (retained-PM4 runtime; HIP kernel work) | ~80% of the decode wall *and* all of prefill. One mechanism, two wins. |
| **2** | **Acceptance** (adapt the existing head; keep full vocab; rollout-conditioned) | the only thing that cuts rounds/token; pos-2 at 24% is the target |
| 3 | Verification-batch kernels (group rows by expert) | bounded — 2 rows already cost only 1.29× |
| ~~4~~ | ~~cheaper draft architecture~~ | **retired** — draft is 16% of the wall |
| ~~—~~ | ~~deeper n-max, n-gram cascade, FR-Spec, checkpoint retry~~ | measured, ≤ noise or worse |

**42–45 t/s is not reachable from the decode side alone at these acceptances.** At 8k we are at 33 ms/token
and would need ~23 ms. Removing the entire draft gets ~28 ms/token — close, but only reachable through a
forward-pass speedup, not a head change. This matches the review's "42–45 remains a target, not an
established near-term outcome."
