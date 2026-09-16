# QSA indexer top-k: set-deterministic, order-nondeterministic (2026-09-15)

This closes the "QSA top-k nondeterminism (ggml-org issue #28497)" item and places it next to the A0
result.

## What the code does

The indexer's selection is `ggml_top_k` over the compressed-block scores. On HIP the op
(`ggml/src/ggml-cuda/top-k.cu`, `ggml_cuda_op_top_k`) dispatches three ways:

- `ncols <= 1024` → `top_k_small_cuda`
- `ncols > 1024` → **`top_k_parallel_radix_cuda`** (our decode: 8k context / ratio 4 ≈ 2048 blocks)
- otherwise → bitonic argsort + copy

The radix path (`top_k_parallel_radix_cuda`, ~line 955) is:

1. `top_k_parallel_radix_histogram` — per-block 256-bin histograms of the ordered float keys.
2. `top_k_parallel_radix_select` — thread 0 per row walks the histogram accumulating `rank` to find
   the threshold bin/prefix, masking one radix digit at a time from the top.
3. `top_k_parallel_radix_gather` — every column with `key > prefix` is emitted at a slot from
   **`atomicAdd(&state->greater_count, 1)`**.
4. `top_k_parallel_radix_gather_equal` — the columns exactly equal to `prefix` (which fill the
   remainder of the k budget) are placed by ballot/popcount **in column order**.

## The finding

- **The selected SET is deterministic.** Steps 1–2 compute each row's threshold from the value
  histogram alone, so for a given score vector the chosen k elements are the same every run. Distinct
  values cannot flip.
- **The ORDER of the strictly-greater part is NOT deterministic.** Step 3 assigns output slots with a
  global `atomicAdd`, and atomics across a grid complete in arbitrary order, so the first
  `greater_count` output slots hold the same tokens in a run-dependent permutation. (The equal-tie
  tail from step 4 *is* ordered.) This is the mechanism behind issue #28497.
- **For QSA this is benign for the result.** The indices feed a gather of keys/values and then a
  weighted sum (attention over the selected set). A sum is invariant to the permutation of its terms
  up to floating-point non-associativity, so reordering moves the output by rounding noise, not by
  content. There is no code path here that requires a sorted index list.

## Relation to A0

This is the **same class of effect A0 measured**, one level up: a small floating-point difference
changes a *discrete* indexer decision. In A0 the width-dependent reduction order changed the dense
argmax at <0.2-nat ties; here a permutation changes the order (and, at exact float ties between the
k-th and k+1-th scores, potentially the *membership*) of the selected block set. Both are "float noise
mapped through a discrete choice". Neither is a state/layout corruption.

Practical consequences, stated plainly:

1. **Do not assert bit-identical indexer output across runs or across verify widths.** Only the
   selected set is stable; the emitted order is not. Any test that compares indexer indices
   element-wise will flake.
2. **Do not expect speculative correctness to hinge on indexer determinism.** Attention over a set is
   order-insensitive, so this is not a path to the A0 divergence; it is an independent, benign
   nondeterminism.
3. If a future change ever needs deterministic indexer output (e.g. a strict reproducibility mode),
   the fix is to replace the `atomicAdd` slot assignment in `top_k_parallel_radix_gather` with a
   deterministic prefix-sum over column index — the same pattern `top_k_gather_equal` already uses.

## Artifacts

Source: `ggml/src/ggml-cuda/top-k.cu` (read-only inspection; no change made).
Related: `acceptance-width-report.md` (A0), `acceptance-metric-frozen-20260915.md` (A1/A2).
