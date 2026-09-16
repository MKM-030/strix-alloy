# Coverage audit: my `rpb` negative tested the wrong workload (2026-09-16)

Codex flagged a test-coverage gap in the `rpb` result and was **right**. This documents the audit.

## The problem

The `rpb` patch changes `calc_rows_per_block` for **`ncols_dst` = 2…8**. I validated it with **serial
decode** (an A/B of 28.95 vs 28.84 t/s). But `ncols_dst` is:

```cpp
// ggml/src/ggml-cuda/mmvq.cu, ggml_cuda_mul_mat_vec_q
const int64_t ncols_dst = ids ? ne2 : ne1;
```

For a dense `MUL_MAT`, `ncols_dst = ne1` = the number of **token columns**. Serial decode is one token →
`ne1 = 1` → **the patch could not have executed at all.** My "negative" was a measurement of a code
path the patch never touched.

## The audit (done, env-gated)

Added a one-time coverage probe in `calc_launch_params` (called from graph construction, so it reports
the kernels actually selected into the graph — not host wrapper calls during replay):

```
[mmvq-coverage] type=… ncols_dst=… rpb=… nwarps=… nrows_x=… table=…
```

Run under **MTP n-max 2** (`-md <head> --spec-draft-n-max 2`), which is where verify widths occur:

| type | ncols_dst values observed | rpb baseline | rpb patched |
| --- | --- | ---: | ---: |
| iq4_nl | 1, 2, 3, 4 | 1 | **2** (except dst=1) |
| q6_K | 1, 2, 3, 4 | 1 | **2** (except dst=1) |
| q8_0 | 1, 2, 3, 4, **8** | 1 | **2** (except dst=1) |

Three conclusions:

1. **`ncols_dst` = 2, 3, 4 and 8 really do execute in this model** under MTP n-max 2 — so the patch is
   *reachable* and the intended verify shapes do occur.
2. **They do not execute in serial decode** (only `ncols_dst = 1`), so **the earlier serial A/B was a
   control, not a test of the patch** — exactly as Codex said.
3. `nwarps = 1` everywhere on RDNA2, confirming one warp per block, so the patch doubles rows per block
   (1 → 2) at those widths and nothing else.

Also verified: the patched build produces **identical acceptance** (31/62 draft tokens at 1k, 50%) and
the same token streams, so output equivalence holds at the verify widths too.

## What this changes

- The earlier `rpb` doc (`rpb2-negative-20260915.md`) is **not a valid negative** — it should be read as
  "no effect at `ncols_dst = 1`, where the change does not apply."
- The intended test is **MTP decode** (which runs width 2/3/4/8), now running.

## Method note for the record

This is the second time a measurement didn't exercise its target (the first was the deep-prefill cold
rep). **Rule added: before trusting any A/B, log which specialisations the graph actually selected.**
The probe is env-gated (`GGML_MMVQ_COVERAGE=1`) and costs nothing when unset.

## Artifacts

`results/cov-mtp.err` (baseline coverage), `results/cov2.err` (patched coverage). Probe source:
`ggml/src/ggml-cuda/mmvq.cu`, `calc_launch_params`.
