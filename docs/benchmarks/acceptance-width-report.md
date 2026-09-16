# acceptance-width-report.md — handover v2, Priority 1 / A0

**Question (handover):** does the target, evaluated in a wide verification pass, produce the same
token as one-row-at-a-time serial decode on the *same prefix*? Speculative decoding is defined to be
output-equivalent to serial greedy; if it is not, the divergence must be classified before spending
effort on the draft head.

**Verdict: serial and wide-verify are NOT token-identical at short context, but the divergence is
tied to the DENSE decode regime (handover case (c): floating-point reduction-order at near ties). It
vanishes once the model is in the sparse regime.** In the sparse regime the two paths matched for
all 120 tokens even at a top1–top2 margin of **0.018 nats**; in the dense regime they flipped at
margins of 0.068–0.163 nats. So margin alone does not explain it — the **dense/sparse regime at the
`indexer_top_k + ratio − 1` boundary does**, the same boundary already identified in
`mtp-indexer-cliff-resolved-20260915.md` (Bug B).

This is **not** a state/layout corruption, **not** causal leakage, and **not** a HIP-graph capture
defect. It is a numerically-unstable dense verify path. No "fix the correctness bug before touching
the head" branch applies; the live P1 levers remain draft quality and scheduling.

## Method

`kernel-work/width-equivalence.ps1` + `verify-width-equivalence.py`. Arms run **strictly serially**
(one 177B instance at a time), greedy (`temperature 0`, `top_k 1`), `cache_prompt false`, fixed seed,
byte-identical prompt verified per arm by SHA-256, generation forced full length (`ignore_eos`) so a
2-token EOS cannot make the test vacuous. Each arm writes its raw token stream; comparison is
**cross-arm** (never within one arm, which would be trivially identical).

Regime boundary from source (`src/models/qwen4exp.cpp`, `qwen4exp_use_block_selection`):
`n_kv > indexer_top_k + ratio − 1`. With defaults (`top_k 2048`, `ratio 4`) the boundary is **2051**:
prompts ≤ 2051 decode **dense**, > 2051 decode **sparse**. (The HIP flash-attention *sparse* kernel
path is NVIDIA-gated, but QSA block selection is a separate model-level mechanism and is what changes
here.)

## Results

| arm | config | 1k (dense) | 1.5k (dense) | 2.56k (sparse) | 4k (sparse) | 8k (sparse) |
| --- | --- | --- | --- | --- | --- | --- |
| `same` | serial, repeat | **IDENTICAL** | — | — | — | **IDENTICAL** |
| `n1` | n-max 1 (ne11=8) | DIVERGES @4 | — | — | — | IDENTICAL |
| `n2` | n-max 2 (ne11=12) | DIVERGES @1 | DIVERGES @17 | IDENTICAL | IDENTICAL | IDENTICAL |
| `n2-nograph` | n-max 2, graphs off | DIVERGES @1 | — | — | — | IDENTICAL |

Controls that make this trustworthy:

1. **`same` arm self-consistent and IDENTICAL to `serial` at both sizes** — the harness is
   deterministic; re-running does not create the divergence.
2. **`n2-nograph` byte-identical to `n2`** — HIP graphs disabled changes nothing, so this is **not**
   graph capture (relevant because production decode is dispatch-free).
3. **A second dense prompt (corpus offset +200000) also diverges, at a different position** — so the
   *position* is content-dependent, but *whether* it diverges is regime-dependent: both dense prompts
   diverged, every sparse prompt matched.

## Divergences are near-ties; the spec arm emits serial's runner-up

| site | div pos | serial pick (logprob) | spec emits | gap (nats) | spec token rank in serial |
| --- | --- | --- | --- | --- | --- |
| 1k (dense) | 1 | `...` 1076 (−1.870) | `<think>` 248068 | **0.163** | **#2** (−2.033) |
| 1k +200000 (dense) | 14 | 1141 (−1.757) | 5099 | **0.069** | **#2** (−1.826) |
| 1.5k (dense) | 17 | 3563 (−1.299) | 8807 | **0.092** | **#2** (−1.391) |
| 1k, n-max 1 (dense) | 4 | 21 (−1.754) | 22 | **0.054** | **#2** (−1.808) |
| 2.56k (sparse) | — | identical all 120 | — | min margin **0.018** | no flip |
| 4k (sparse) | — | identical all 120 | — | min margin 0.140 | no flip |

At every dense divergence the speculative arm emits **serial's second-ranked token**, separated by
< 0.17 nats (`check-flip.py`, `analyze-margins.py`, `dump-probs.py`). The sparse arms held through
margins smaller than that, which is what makes "margin alone" insufficient and points at the regime.

## Mechanism (why dense, not sparse)

`ggml/src/ggml-cuda/mmvf.cu` is **templated on `ncols_dst`** — the destination row count — with
`float sumf[ncols_dst]` and a thread split `if (tid >= ncols_dst)`. So the reduction layout changes
with the number of verified rows on every `mul_mat_vec`-family call. In the **dense** regime the
verify pass carries more rows through those kernels than serial decode does, the reduction order
differs, and a < 0.2-nat top1–top2 gap can flip. In the **sparse** regime the QSA decode path
(`d67d5883`) selects a block set that does not expose the same row-count-sensitive reduction at the
final argmax, so serial and verify agree. This is a plausible reading, not a kernel-audited proof —
what is *established* is the empirical dense-flip / sparse-stable split.

## Classification (handover's four cases)

- (a) different intended attention/state semantics or causal leakage — **no** (same ids, positions,
  lengths; only an adjacent-ranked token is substituted).
- (b) layout/stale-state corruption — **no** (graphs-off identical; `same`-arm deterministic; flips
  track the regime boundary, not an arbitrary kernel).
- (c) repeatable floating-point reduction-order differences at near ties — **yes**.
- (d) normal stochastic sampling differences — **no** (temperature 0, top_k 1, fixed seed).

## Consequence for P1

Speculative decode is **not** bit-identical to serial greedy on this stack; it is self-consistent
within the speculative path (a draft token is accepted iff it equals the wide-verify argmax,
`common_sampler_sample_and_accept_n`). The deviation is confined to the **dense** regime
(`n_kv ≤ indexer_top_k + ratio − 1` = first ~2051 tokens at default `top_k`). Past that, the paths
match. Two practical consequences:

1. Acceptance is agreement with the **wide-verify argmax**, and sub-0.2-nat positions are numerically
   unstable by construction — chasing them buys nothing.
2. Raising acceptance is not gated by a correctable verify bug → the draft-quality (training) or
   scheduling routes are the live P1 levers.

## Relation to prior work

`mtp-indexer-cliff-resolved-20260915.md` (Bug B) established that the **MTP acceptance cliff** sits at
exactly `n_kv > indexer_top_k + ratio − 1` and is fixed by `--override-kv qwen4exp.attention.indexer.top_k`.
That is about **draft-vs-target** agreement (collapses to 0% past the boundary). This report is about
**target serial-vs-verify** token identity (degrades at near-ties *below* the boundary, and is stable
above it). They are complementary and share the same threshold — further evidence that the dense/
sparse switch at that boundary is the behaviour-changing point. Note also that Halogen 0.9.1 is
reported byte-identical under speculative decode at every budget; this stack is not, in the dense regime.

## Artifacts

- `kernel-work/width-equivalence.ps1`, `verify-width-equivalence.py` (arms, prompts, cross-arm diff)
- `kernel-work/analyze-margins.py`, `check-flip.py`, `dump-probs.py` (margin + rank analysis)
- `kernel-work/results/vwe-*.json|log|err`, `vwe-summary.json`
- `docs/benchmarks/acceptance-metric-frozen-20260915.md` (A1/A2 — metric + algorithm)
