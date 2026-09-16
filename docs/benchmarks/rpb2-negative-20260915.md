# rpb 1→2 for verify widths on RDNA2 — first test (serial, INVALID) superseded (2026-09-15)

> **DECISION HAZARD — READ THE SUPERSEDING DOC FIRST.**
> This doc's "negative" is **invalid as a test of the patch**: the patch changes `ncols_dst` 2…8, but
> the A/B here used **serial decode (`ncols_dst = 1`)**, which the patch cannot touch. The valid test
> (MTP decode) is in **`rpb2-covered-negative-closed-20260916.md`**: covered, and still negative
> (+0.3%) — so `rpb` is closed, but for the right reason. Keep this doc only for the mechanism
> reasoning and the correctness evidence; ignore its performance verdict.

The shapebench lead, tested for real. Short version: **the change is output-equivalent and costs
nothing, but the test below did not exercise it.**

## Why this was worth testing

`shapebench` (Step 3) showed the same 4.219 GB read at **238 GB/s contiguous** but only **28–56%** when
issued as many kernels whose grids are sized for the whole buffer (short per-block loops). Our decode
issues ~150 such matvec kernels per step and runs at 53% of peak.

Reading `mmvq.cu` found a concrete mismatch: gfx1151 uses the **RDNA2** table, and on that table

```cpp
static constexpr __host__ __device__ int calc_rows_per_block(int ncols_dst, int table_id, ...) {
    if (table_id == GENERIC || GCN || TURING || GB10) { ... case 2..8: return 2; }
    return 1;                    // RDNA2 (us): 1 for every width
}
```

so a verify-width GEMV launches **one thread block per output row** (`nblocks = ceil(nrows_x/rpb)`,
`row0 = rpb*blockIdx.x`). Every other table uses 2 rows/block for the verify widths. Raising `rpb` to 2
halves the block count and doubles bytes in flight per block — exactly the shape shapebench said
mattered.

## The change

`calc_rows_per_block`: for `table_id == MMVQ_PARAMETERS_RDNA2` and `ncols_dst ∈ [2,8]`, return 2.
Gated on **`table_id`, not the `RDNA2` macro**, because the function is `__host__ __device__` and only
`table_id` is identical on both sides; the kernel's `rows_per_cuda_block` and `row0` mapping are
`constexpr` from this value, so a host-only override would desync the grid from the addressing and
corrupt output. (`getenv` cannot be used here for the same reason — a host-only change would desync.)

## Correctness: output-equivalent

`width-equivalence.ps1` on the patched build, same-prefix comparison against the known baseline:

| arm | 1k | 8k |
| --- | --- | --- |
| serial (patched) | `271,1076,220,16,21,18` — **matches pre-patch baseline** | sha `117f74302cf86bf8` — **matches pre-patch** |
| n-max 2 (patched) | DIVERGES @1 (same A0 near-tie as upstream) | IDENTICAL |

So the patched binary reproduces the **baseline token streams and the baseline A0 divergence pattern
exactly**. It is not broken.

## Speed: negative

Interleaved A/B (alternating base/patch arms, 2 rounds × 4 warm reps, `gen 256`, 8192-token prompt):

| arm | round 1 | round 2 | median |
| --- | ---: | ---: | ---: |
| base (rpb=1) | 28.953 | 29.073 | 28.95 |
| patch (rpb=2) | 28.844 | 28.978 | 28.84 |
| **delta** | | | **−0.4%** |

**No effect.** Within run-to-run noise, and if anything marginally negative.

## Why the prediction failed — and what that tells us

shapebench's B→D gap was the *stated* justification, but B and D also differ in **total block count per
launch**: B launched 4096 blocks for a 28 MB buffer, D only 256. Halving rows-per-block (our change) is
the *opposite* lever — it reduces blocks per kernel by 2×, but our kernels already launch only
`nrows_x/rpb` blocks (12,288 for `attn_q`), each with a ~5-iteration loop. Making that 2 rows/block
gives ~5 iterations per block still (the loop is over K, not rows), so the per-block loop depth is
**unchanged** — and shapebench says loop depth, not block count, is what matters.

**The correct reading of shapebench is therefore narrower than I first wrote:** it shows that short
per-block **K-loop** depth loses bandwidth. `rpb` changes *rows* per block, not K-loop depth, so it was
the wrong lever. The right lever is the K decomposition (split K across blocks, or a persistent kernel
that keeps looping over K), which is a larger change than a table tweak.

This is a useful negative: it retires the "grid shape = rows-per-block" hypothesis and points at
K-loop depth specifically.

## Reverted

`git checkout` in `~/strix-llama` (tree clean at `891a923a`); `ggml-hip.dll` restored from
`ggml-hip-base.dll` (86,770,688 bytes) and rebuilt. Experiment DLLs removed.

## Artifacts

`results/iab-base-r{1,2}.json`, `results/iab-patch-r{1,2}.json`, `results/interleaved-ab.json`;
`docs/shapebench-finding-20260915.md` (the in-vitro result, whose conclusion is now narrowed).
