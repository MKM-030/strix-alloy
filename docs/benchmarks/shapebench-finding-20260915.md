# The decode bandwidth loss is not the scattered access pattern (2026-09-15)

> **SUPERSEDED for the conclusion, not the data.** This doc's pure-read variants (A–D) are correct and
> still useful — scattered addresses reach ~100% of bandwidth. But the *interpretation* below ("loss is
> per-block K-loop depth") was overtaken the same day by the **quantized-GEMV** variants (E–K), which
> show the loss is the **per-weight arithmetic**, and that a faithful replica of the real algorithm
> reaches **80.8%** where production sits at 52%. **Read `decode-alu-bound-dp4a-20260916.md` for the
> current answer.** Everything in this doc about A–D remains valid; the "Consequence" section below is
> kept only to show the (corrected) reasoning path.

Codex Step 3, answered directly and with a surprising result. **The "many scattered buffers" access
pattern is not the limitation — scattered addresses reach ~full bandwidth.**

## Method

`kernel-work/shapebench.hip` (standalone HIP, compiled with the same TheRock clang 24 / gfx1151
toolchain as the server). 4.219 GB total, read four ways, all consuming the data so nothing is
optimised out. Warm iterations, event-timed, one core per variant:

| variant | what it does |
| --- | --- |
| **A** contiguous | one 4.219 GB buffer, one grid-stride kernel |
| **B** fragmented, N launches, big grid | one kernel **per buffer**, grid sized for the whole buffer (`min(ceil(n/256), 4096)` blocks) |
| **C** fragmented, **1 launch** | one kernel covering all buffers (block → buffer mapping, 256 blocks/buffer) |
| **D** fragmented, N launches, small grid | one kernel **per buffer**, but only 256 blocks each — same per-buffer grid as C |

B vs D isolates **grid shape**; D vs C isolates **launch count**.

## Results (GB/s, % of A)

| config | A contig | B (N launch, big grid) | D (N launch, small grid) | C (1 launch) |
| --- | ---: | ---: | ---: | ---: |
| uniform, 48 buffers | 238.3 | 171.2 (72%) | 234.4 (98%) | 238.0 (100%) |
| uniform, 150 buffers | 238.5 | **66.9 (28%)** | 205.0 (86%) | **241.2 (101%)** |
| realistic, 48 buffers | 236.9 | 197.0 (83%) | 230.7 (97%) | 236.1 (100%) |
| realistic, 150 buffers | 238.3 | **134.4 (56%)** | 213.8 (90%) | **226.4 (95%)** |
| realistic, 150 buffers, **12 GB** | 236.9 | 203.6 (86%) | 230.3 (97%) | 235.9 (100%) |
| uniform, 512 buffers* | 236.7 | *artifact* | 138.4 (58%) | 215.7 (91%) |

\* at 512 uniform buffers each is only 8.2 MB, and B's per-buffer grid (4096 blocks) exceeds the work
(→ tiny loop → the 1760 GB/s inflation). B is only valid where the grid is not oversized. D and C stay
sane there and are the meaningful columns.

## What this means

1. **Scattered addresses are fine.** C reads the *same* 150 physically separate buffers as B and
   reaches **95–101% of contiguous**. So the memory subsystem handles ~150 disjoint regions at full
   rate. The address pattern is **not** the explanation for the 53% decode efficiency.
2. **The loss is per-launch/grid, and it is large.** B (many launches, oversized grid) collapses to
   **28–56%**, matching our production decode efficiency (53.5%) almost exactly. The magnitude and the
   shape both fit.
3. **It is not "launch overhead" in the usual sense, and not simply over-subscription either — it is
   per-block work too small.** B sizes each buffer's grid up to 4096 blocks; for a 28 MB buffer that is
   ~1.7 grid-stride iterations per thread, i.e. very short loops, and it collapses to 28%. D caps each
   buffer's grid at 256 blocks → ~27 iterations per thread → 86%. C caps at 256 *and* merges into one
   launch → 101%. So the cost scales with **how few loop iterations each resident block gets**: short
   loops cannot keep the memory pipeline full across their own ramp-up and drain. Total launch latency
   (~150 × 5 µs ≈ 0.7 ms over a 17.7 ms step, ~4%) is far too small to explain a 12–46 ms loss; the
   loss is inside the kernels, in their loop depth.

## Consequence for the decode plan — and a correction after testing it

- **Retire "access pattern" as the suspect.** The bytes are reachable at full rate.
- **The real target is per-block K-loop depth of the quantized-matvec kernels**, not block count.
  ⚠️ **Correction (2026-09-15, after the follow-up experiment):** I first read this as "grid shape =
  rows per block" and implemented `calc_rows_per_block` 1→2 for the verify widths on RDNA2. It was
  **output-equivalent but −0.4% (no effect)** — see `rpb2-negative-20260915.md`. The reason is that
  `rpb` changes **rows** per block, while the matvec's inner loop is over **K**; halving block count
  does not lengthen the K loop. shapebench's B→D gap came with a *total block count* difference too, so
  the correct, narrower reading is: **short per-block K-loop depth loses bandwidth.** The live
  candidate is therefore a **K-decomposition change** — split K across blocks, or a persistent kernel
  that keeps each block looping over K — which is a larger change than a table tweak.
- The measured 53% decode efficiency is consistent with each of ~150 kernels paying a ramp/drain cost
  because its resident blocks have only a few K iterations each.
- **This also explains why the parameter-table experiments failed.** Small-K/nwarps swaps changed the
  reduction, and `rpb` changes rows-per-block, but neither lengthens the per-block K loop, so none
  could recover a K-loop-depth-dominated loss.

## Caveats

- shapebench's kernels are pure reads, whereas the real kernels also dequantize and reduce. It isolates
  the *memory-side* behaviour, which is the point — but it does not prove the real kernels are
  ramp-bound; it removes the alternative explanation (bad addresses) and points at the kernel structure.
- The 512-uniform B point is an artifact; D/C are the valid columns there.
- L2 effects: C's blocks from different buffers share the L2 during the run. At 4.2 GB over ~10 MB L2
  the reuse is negligible, so this does not explain C's speed.

## Artifacts

`kernel-work/shapebench.hip`, `shapebench.exe`. Raw output in this doc. Run:
`shapebench.exe <totalGB> <nBuffers> <uniform|realistic>`.
