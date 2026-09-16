# rpb 1→2 at verify widths: covered AND negative — closed (2026-09-16)

Codex's stop condition for `rpb` was: *"Covered and negative: close it."* Both halves are now
established. **Closed.**

## Why the earlier negative did not count

The patch changes `calc_rows_per_block` for `ncols_dst` = 2…8. My first A/B used **serial decode**, and

```cpp
const int64_t ncols_dst = ids ? ne2 : ne1;   // dense MUL_MAT: ncols_dst = token columns
```

so serial decode is `ncols_dst = 1` — the patch **could not execute**. The coverage probe
(`rpb-coverage-audit-20260916.md`) confirmed it: serial decode logs only `ncols_dst = 1`.

## Coverage (established)

Under **MTP n-max 2** the probe shows `ncols_dst` = 1, 2, 3, 4 and 8 all execute, for `iq4_nl`, `q6_K`
and `q8_0` — and the patched build reports `rpb = 2` for every one of those (2/3/4/8) while leaving
`ncols_dst = 1` at `rpb = 1`. So the intended verification shapes **are** exercised by MTP decode.

## The correct test: MTP decode A/B

Same binary, `GGML_MMVQ_RD2_ROWS2` toggled, interleaved arms (base, rows2, base, rows2), 4 warm reps
each, `gen 256`, 8192-token prompt, `-c 32768 -b/-ub 2048`, MTP n-max 2.

| arm | round 1 | round 2 | median | acceptance |
| --- | ---: | ---: | ---: | ---: |
| base (`rpb=1`) | 27.376 | 27.18 | **27.376** | 39.6% |
| patched (`rpb=2`) | 27.467 | 27.14 | **27.467** | 39.6% |
| **delta** | | | **+0.3%** | identical |

**No effect.** Acceptance is identical to the decimal (39.6%, and the same draft-token counts), so the
patched build is output-equivalent at the verify widths too — it is simply not faster.

## Verdict

`rpb` 1→2 for verify widths on RDNA2: **correct, covered, and negative. CLOSED.** Do not tune this
table further, as Codex advised.

Combined with the in-vitro work, the reason is now clear and consistent: `rpb` changes **rows per
block**, while the matvec inner loop is over **K**. Halving the block count does not lengthen any
block's K loop, so it cannot recover a loss that shapebench attributes to per-weight arithmetic /
short per-block work. The candidate that matches that diagnosis is a **scheduling** change — bounded
blocks each processing multiple complete output rows — not a table value.

## Where this leaves the decode plan

Per Codex's ordered list, the next three items now stand:

1. ~~Audit `rpb` coverage~~ — **done, closed** (this doc).
2. Check `shapebench` for per-block epilogue / checksum confounds (Codex's caution: B's grid may be
   paying an avoidable per-block cost that production does not have).
3. **Persistent-row scheduling** on one real IQ4_NL dense GEMV (`T=1`), preserving the inner
   arithmetic, with a small grid screen (160/320/640/1280 blocks).

Codex's explicit guidance for (3) is worth keeping verbatim in the plan: do not mechanically wrap the
kernel in a loop — the kernel has row-dependent pointers, accumulator initialisation and an early
return for non-leading warps after shared reduction, so a persistent form must reset accumulators per
tile, keep all threads participating in every tile, handle the tail, and preserve `grid.y/z` meanings
(experts/samples).

## Reverted / state

The `rpb` experiment is reverted in `~/strix-llama` (tree clean at `891a923a`); `ggml-hip.dll` is
rebuilt from clean source. The coverage probe is **removed** from the tree but retained as a technique
in `rpb-coverage-audit-20260916.md` — it should be re-added for any future dispatch-level A/B.

## Artifacts

`results/mab-{base,rows2}-r{1,2}.json`, `results/mtp-rows2-ab.json`;
`kernel-work/mtp-rows2-ab.ps1`; coverage: `results/cov-mtp.err`, `results/cov2.err`.
