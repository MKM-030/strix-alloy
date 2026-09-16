# Codex prompt #2 — results of your plan, plus a new lead (2026-09-16)

**UPDATE (later the same day): I then ran your Step-3 variant C (the real quantized GEMV) and it
changed the answer.** Skip to §9 for the headline: production decode is ~52% while a faithful replica
of the real per-weight algorithm reaches **80.8%** → a **~1.5× decode gap**. Everything before §9 is
still valid context, but §9 is the finding.

Paste everything below the line into Codex. It reports what happened when I ran your sequence, and
carries one **new, measured, actionable** finding. As before: numbers are measured on one machine;
negative results are listed so you do not re-propose them.

---

You previously reviewed my Strix Halo inference record and gave a 5-step plan. I ran it. Here is what
each step produced — **three of my earlier "effects" were measurement artifacts and are now retracted,
one of your own suggested priorities turned out not to exist, and one genuinely new lead emerged.**

## Step 1 — accounting corrected (your correction, accepted)

You were right that I conflated MTP with serial. Corrected:

- 35.5 t/s is **MTP**; serial is **29.9 t/s**. The "we run 35 t/s serial = 63% of ceiling" line was wrong.
- Corrected serial weight-payload throughput (4.219 GB/token ÷ measured ms/token):
  1k **53.5%**, 8k 51.2%, 65k 51.0%, 131k 48.2%, 251k **46.4%** of the 235.7 GB/s ceiling.
- Two of my numbers you used were themselves wrong: **251k serial is 25.9 t/s, not 23.4** (23.4 was a
  cold single rep), and at depth the denominator is incomplete (KV + indexer bytes also grow). So the
  depth decline is **−13%, not −22%**, and the true efficiency at depth is *higher* than 46.4%.
- I have **retired "uniform 37%"** and relabeled it "substantial unexplained effective-bandwidth loss
  (~53% of peak shallow)". The expert ablation identifies k-independent work, not its composition —
  dropping that inference, as you said.

## Step 2 — the configured-context penalty DOES NOT EXIST (your #1 priority)

I ran your capacity test (same 16k prompt, zero start depth, only `-c` varies; no drafter; warm).

| `-c` | KV | rep0 | rep1 | rep2 | rep3 | **steady** |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32,768 | 0.75 GiB | 646 | 817 | 870 | **1033** | 1033 |
| 131,072 | 3 GiB | 657 | — | — | **1026** | 1026 |
| 262,144 | 6 GiB | 631 | 1014 | 1024 | **1029** | 1029 |

**Steady-state prefill is 1026–1033 t/s at every capacity (within 0.7%).** The eightfold KV allocation
has no throughput cost. What *does* happen: prefill needs **3–4 warm reps** to reach steady state
(646→817→870→1033). My earlier "1021 @ `-c 32768` vs 862 @ `-c 262144`" were two different points on
that same ramp. **The 15.6% "penalty" was a warm-up artifact, not capacity.**

That also retires the deep-prefill "cliff" from the previous report: warm, the curve is
**862 (16k) → 984 (65k) → 907 (131k) → 856 (196k) → 809 (251k)**, a gentle decline, not a fall to 650.

**Rule now enforced: prefill is reported from rep ≥ 3, never rep 1.**

**Occupied depth (your capacity-vs-occupied split, second half), done properly** — prime KV to depth D,
append a fixed 8192-token chunk, measure only that chunk (verified `processed_tokens == 8192`,
`cache_n == D`):

| occupied depth | chunk prefill |
| ---: | ---: |
| 0 | **642.8** t/s |
| 32,768 | **586.4** t/s (−9%) |
| 131,072 | **598.4** t/s (flat) |

So: capacity **free**, occupied depth **−9% then saturating** (consistent with the QSA indexer's
`top_k = 2048` cap). Prefill-at-depth is closed as a lever.

## Step 3 — shape-matched benchmark: your discriminator produced a strong result

I built a standalone HIP read benchmark (`shapebench`) that reads 4.219 GB four ways. It is not an
in-graph timer; it is a separate binary with its own event timing, same toolchain.

| variant | uniform 150 bufs | realistic 150 bufs |
| --- | ---: | ---: |
| **A** contiguous, 1 launch | 238.5 GB/s | 238.3 GB/s |
| **B** one kernel per buffer, grid sized for the whole buffer | **66.9 (28%)** | **134.4 (56%)** |
| **D** one kernel per buffer, grid capped small (256 blocks) | 205.0 (86%) | 213.8 (90%) |
| **C** one kernel for ALL buffers (1 launch) | **241.2 (101%)** | **226.4 (95%)** |

**The scattered access pattern is NOT the problem.** C reads the same 150 physically separate buffers
and reaches 95–101% of contiguous bandwidth. The loss appears only in B — many launches each with a
**grid far larger than its work** (short loops). D, which keeps per-buffer grids small, recovers most
of it even across 150 launches.

Interpretation: the cost is **per-block loop depth / pipeline ramp**, not addresses and not (mainly)
launch count. 150 launches × ~5 µs = 0.7 ms of a 17.7 ms step, but B loses 12–46 ms, so it is
inside the kernels.

**This matches our production decode:** ~150 separate matvec kernels per step, measured 53% of peak.
Same number, same mechanism candidate.

## Where our kernels actually stand (the new actionable lead)

I read the local `mmvq.cu` dispatch. On gfx1151 the table is **RDNA2**, and:

```cpp
static constexpr __host__ __device__ int calc_rows_per_block(int ncols_dst, int table_id, ...) {
    if (table_id == GENERIC || GCN || TURING || GB10) {
        case 1: return small_k ? nwarps : 1;
        case 2..8: return 2;          // <-- every other table
    }
    return 1;                          // <-- RDNA2 (us): 1 for EVERY width
}
```

and the grid is `nblocks = ceil(nrows_x / rpb)` with `row0 = rows_per_cuda_block * blockIdx.x`.

So on gfx1151, a decode/verify GEMV launches **one thread block per output row**. For
`attn_q [2560, 12288]` that is 12,288 blocks, each with a K-loop of only `K/(vdr*warp) ≈ 5`
iterations — i.e. shapebench variant **B**. Other AMD/NVIDIA tables use 2 rows/block for the verify
widths (2–8), halving the block count and doubling bytes in flight per block.

**Candidate (experiment now running):** set `rpb = 2` for `ncols_dst` 2–8 when `table_id == RDNA2`,
gated on `table_id` (not the `RDNA2` macro) because `calc_rows_per_block` is `__host__ __device__` and
only `table_id` is identical on both sides — the kernel's `rows_per_cuda_block` and `row0` mapping are
`constexpr` from it, so a host-only override would desync.

I am A/B-ing this now: correctness first (same-prefix token equivalence between builds), then median
serial decode in the interleaved harness.

**RESULT — you were right, and the corrected test is also negative (so `rpb` is now properly closed):**

- **You caught a real coverage error.** I added an env-gated coverage probe at graph construction and
  it confirms your point exactly. `ncols_dst = ids ? ne2 : ne1`, so serial decode is `ncols_dst = 1` —
  which my patch (widths 2–8) cannot touch. Serial decode logs only `ncols_dst = 1`; **the first A/B
  measured a code path the patch never entered.**
- **Coverage now established.** Under MTP n-max 2 the probe shows `ncols_dst` = **1, 2, 3, 4, 8** all
  execute (for `iq4_nl`, `q6_K`, `q8_0`), and the patched build reports `rpb = 2` at every one of
  2/3/4/8 while leaving `ncols_dst = 1` at `rpb = 1`. Also: `nwarps = 1` everywhere on RDNA2.
- **The correct test (MTP decode, which runs width 3) is also negative.** Same binary, env gate toggled,
  interleaved 2 rounds × 4 warm reps, `gen 256`, 8k prompt: base **27.376** vs patched **27.467** t/s =
  **+0.3%**, acceptance identical (39.6%, same draft counts → output-equivalent).

**Per your stop condition (covered AND negative), `rpb` is CLOSED** — and I will not tune the table
further. I agree with your mechanism: `rpb` changes *rows per block*, not the K loop, so it cannot fix
a per-weight-arithmetic/short-work-per-block loss. Your **persistent-row scheduling** proposal is the
next item, and I have noted your implementation cautions (reset accumulators per tile, all threads must
participate in every tile, tail handling, preserve `grid.y/z` meanings, capture the candidate kernel
intentionally).

**One consequence for your step 2 (shapebench confound check):** the probe technique is now part of the
toolkit — any dispatch-level A/B gets a coverage log first, so "no effect" can never again be an
artifact of testing an untouched path.

---

Note this is *different* from the already-negative small-K/nwarps/table-swap experiments: those changed
the reduction. This changes only the **grid shape** (blocks per row-batch), which is what shapebench
identified.

## Step 5 — q8 KV: audited, hard-blocked, and now pointless

Source + binary confirm: `build_layer_attn` has
`GGML_ASSERT(q->ne[0] == 256 && k->type == GGML_TYPE_F16 && v->type == GGML_TYPE_F16)` on the
`direct_indices` (production `-fa on`) path, and it is **not** gated on cache dtype. Launching with
`-ctk q8_0 -ctv q8_0 -fa on` fails at **model load**:

```
qwen4exp.cpp:1411: GGML_ASSERT(... k->type == GGML_TYPE_F16 ...) failed
```

So: not a slow fallback — an immediate hard failure; needs a new q8-capable qsa3 kernel. And since
capacity is now shown to be free, the ~2.8 GiB saving buys nothing on this box. **Closed as
`BLOCKED_ON_KERNEL`, not worth pursuing.**

## Step 4 / 6 — not done, and why

- **Kernel candidate (your #4):** superseded by the shapebench lead above, which is a better-aimed
  single change. I did not spend a slot on a blind Q6_K/LM-head specialisation first.
- **Hyper-connections:** your correction that `W_up·SiLU(W_down·x) ≠ (W_up·W_down)x` is right; not
  pursuing pre-multiplication. The `pack_di` path exists locally; I have not yet verified whether our
  dtype/shape uses it.
- **Acceptance/training (your #6):** agreed it is not yet justified. Note the `gen 256` re-run gives
  **0.56 / 0.65 / 0.70 / 0.64 / 0.73** across 16k→251k (tight, not the noisy 50–74%), and MTP decode is
  **flat 30.2–32.8 t/s** over that range. So the "depth collapse" is not there; acceptance *rises* with
  depth.

## What I want from you now

1. **Was `rpb` the wrong lever, and is K-splitting the right one?** My read: `rpb` changes rows/block,
   not the K loop, so it was inert (measured). The candidate that matches shapebench is a **K
   decomposition** — split K across blocks so each block does more independent loads, or a persistent
   block that streams many K-tiles. For a decode GEMV with K ~2560–6144 and 1–3 rows, what is the
   right form: multiple K-splits per output row with a second reduction pass, or a persistent kernel
   over (row, K-tile)? Which is expressible in ggml without a custom op, and which do you expect to
   actually recover bandwidth?
2. **The general-form question.** shapebench says "short per-block loops lose ~half the bandwidth".
   For single-token MoE decode on a wide unified-memory part, is there a known-good decomposition that
   keeps every block's loop long — persistent blocks over multiple weight tensors, a fused multi-tensor
   GEMV within a layer, or K-splitting? What does the literature/other fork work say for this shape?
3. **Is C-shape (one launch, block→tensor mapping) the real target?** C hit 101% with one launch over
   150 scattered tensors. Could a layer's decode GEMV be restructured as one launch over that layer's
   tensors, and is that expressible in ggml's graph without a custom op?
4. **Reading the shapebench numbers.** B at 28% (uniform) vs 56% (realistic) — I attribute this to B's
   grid being sized for the buffer, so uniform 28 MB buffers are the *worst* case. Does that imply our
   worst tensors are the uniform-sized ones (e.g. the 48 router matrices or the HC projections)?
5. Given capacity is free and depth is −9%-then-flat, **is there any remaining prefill lever at all**,
   or should all effort go to the decode kernel shape?

## 9. THE HEADLINE: I ran your variant C (the real GEMV), and it changes the answer

You (correctly) told me to benchmark the **full production operator**, not just reads. I had skipped
that. I built it: same 150 realistic buffers, same launches, same grid — only the inner loop varies.
Cache-proof size (12 GB; the 4.2 GB runs gave >100% artifacts from L2).

| variant (inner loop per 16-byte block = 32 weights) | GB/s | % of contiguous |
| --- | ---: | ---: |
| A contiguous control | 236.4 | 100% |
| **G** loads only, 1 FMA/block | 238.8 | **101.0%** |
| **I** dp4a int8, 8 dots (cheap dequant) | 190.1 | **80.4%** |
| **K** dp4a + the REAL `get_int_from_table_16` v_perm LUT dequant | 190.4 | **80.8%** |
| F 32 float FMAs, no LUT | 116.5 | 49.3% |
| H 32 float FMAs, 8 independent accumulators | 126.0 | 53.3% |
| E 32 float FMAs + LUT | 108.5 | 45.9% |

**What is ruled out, by direct measurement (all at identical loads/launches/grid):**

- **Memory / addresses / launch count / grid shape** — G runs at **101%**. All of it is fine.
- **The dequant LUT** — K uses the *real* AMD v_perm table lookup and gets **80.8%**, same as I's cheap
  arithmetic. The LUT is free.
- **Alignment** — the real block layout is 18 bytes; K handles it and still hits 80.8%.
- **Dependency chains** — H (4/8 accumulators) only reaches 53% vs F's 49%, so it is throughput, not
  latency.
- **Multi-row verify** — production *serial* (1 row) already measures 29.4 t/s = **52.6%**, so the gap
  is not the 3-row verify.

**The quantified gap:** production serial decode = **52–53%**; the real algorithm's own in-vitro
ceiling = **~81%**.

```
4.219 GB / 236.4 GB/s / 0.808 = 22.1 ms/token  ->  45 t/s
```

vs measured **29.9 t/s** → **~1.5× available**. Every earlier "loss" (flat across widths, flat across
depth, uniform) is consistent with this.

**The remaining question — where does 81% become 52%?** Since K replicates the per-weight math and the
loads and still hits 81%, the deficit must be **kernel structure around the matvec**, and my leading
candidate is the **multi-warp K-reduction**: real `mmvq` uses several warps per output row with a
shared-memory reduction (`tmp_shared`, `buf_iw`) and spin-lock syncs, whereas K used one warp with no
cross-warp reduction. On ~150 small kernels per step, that fixed per-kernel cost is the obvious
suspect.

**What I want from you on this:**

1. Is the **cross-warp reduction** the right suspect for 81% → 52%, or would you rank something else
   (e.g. per-kernel ramp on ~150 launches, or work outside the GEMV) first? How would you test it
   cheaply?
2. If it is the reduction: is there a decomposition that avoids it — **one warp per row with K
   entirely in registers** (K up to 6144 at 4 bits = 768 uint4, too many), **K-split across blocks with
   a small second reduction pass**, or **persistent blocks that keep one warp per row looping over K**
   so the reduction happens once per block instead of once per kernel?
3. Given K reaches 81% single-warp-no-reduction, is the cleanest experiment simply to **build the real
   `mul_mat_vec_q` into this standalone bench** and flip warps-per-row / K-split one at a time? Or is
   there a better in-vitro construction first?
4. Does the `ne11`=1..3 verify width interact here — i.e. should the multi-row path use a different
   decomposition than the single-row path, given dp4a per-thread throughput is fixed but the weight is
   reused across rows?
