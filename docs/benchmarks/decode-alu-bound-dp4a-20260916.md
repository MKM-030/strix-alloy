# ~~Decode is ALU-issue-bound at the per-weight level~~ — RETRACTED (2026-09-16)

> **RETRACTED — DO NOT USE THE CONCLUSION.**
> A follow-up confound check (`shapebench-epilogue-confound-20260916.md`) found that this document's
> "80.8% dp4a ceiling" was caused by **the benchmark's own contended `atomicAdd` epilogue**, which
> production does not have. With a fair per-block epilogue, dp4a reaches **100.8–101.0% of contiguous
> bandwidth** at cache-proof size. So the dequant arithmetic is **not** the limiter, and the
> ~1.5×/45 t/s projection below is **withdrawn**.
>
> What survives: the 32-float-FMA formulation *is* ALU-limited at ~50% (epilogue-independent), but
> production's IQ4_NL dot uses dp4a, so that explains nothing about our measured 52%. See the retraction
> doc for the full scorecard.

**Status of the claims below, in short:** the variant tables A–K are valid measurements of *this
benchmark*; only the **interpretation** (and the 80.8%/45 t/s figures) are retracted.

---

## (retracted) original text follows

**This was the answer to the decode-efficiency question** — Codex's Step 3 variant C — subsequently
retracted as described above.

## Method

`kernel-work/shapebench.hip`, standalone HIP, same TheRock clang 24 / gfx1151 toolchain. 12 GB total
(cache-proof — the 4.2 GB runs gave inflated >100% numbers from L2), fragmented into 150 realistic
tensor sizes, one kernel per buffer, **big grid** (grid sized for the buffer, i.e. our shape). Variants
differ **only in the inner loop**; loads, launches, grid shape and addressing are identical.

| variant | inner loop per 16-byte block (32 weights) |
| --- | --- |
| **A** | contiguous control read |
| **G** | 1 derived FMA per block (minimal ALU; isolates "loads only") |
| **I** | 8 × `dp4a` int8 dot (4 MACs each = 32 MACs) — **the real algorithm** |
| **F** | 32 × float FMA + nibble arithmetic, no lookup table |
| **H** | F with 4 / 8 independent accumulators (ILP test) |
| **E** | F + dynamic 16-entry lookup table (IQ4_NL value LUT) |

## Results (12 GB, cache-proof; % of contiguous)

| variant | GB/s | % of A |
| --- | ---: | ---: |
| A contiguous | 236.4 | 100% |
| **G loads-only, minimal ALU** | **238.8** | **101.0%** |
| **I dp4a int8 (cheap dequant)** | **190.1** | **80.4%** |
| **K dp4a + the REAL v_perm LUT dequant** | **190.4** | **80.8%** |
| F 32 float FMAs | 116.5 | 49.3% |
| H 32 float FMAs, 8 accumulators | 126.0 | 53.3% |
| E 32 float FMAs + LUT | 108.5 | 45.9% |

J (18-byte IQ4_NL block stride, unaligned 4-byte loads, dp4a) reported 192% — **invalid**; its block
count `nu*16/18` under-reads the buffer, so it is not comparable. Alignment was instead ruled out by
the fact that K, which uses the true 16-byte-aligned `qs` layout and the real dequant, matches I
exactly. **A faithful replica of the real per-weight algorithm (K) reaches 80.8%.**

## What each comparison proves

1. **Not memory, not addresses, not launches, not grid shape.** G has identical loads/launches/grid to
   E/F/H and runs at **101%**. Everything memory-side is fine.
2. **The cost is the per-weight arithmetic.** Adding 32 float FMAs per 16-byte block drops 101% → 49%.
3. **It is not a dependency chain.** H (4 and 8 independent accumulators) only reaches 53% vs F's 49%.
4. **It is not the lookup table.** E (LUT) 45.9% vs F (no LUT) 49.3% (3 pts); and **K, which is the
   real `get_int_from_table_16` v_perm dequant plus dp4a, matches I (80.8% vs 80.4%)** — the LUT is
   essentially free on this encoding.
5. **It is not alignment.** Established indirectly: the real layout is 18-byte blocks; K handles it and
   still reaches 80.8%.
6. **The intended `dp4a` encoding recovers it.** 32 float FMAs → 8 `dp4a` ⇒ 80.8%.

## The quantified opportunity

Production **serial** decode is **29.4–29.9 t/s ≈ 52–53%** at shallow depth. Variant K — the closest
in-vitro replica of the production algorithm (real dp4a + real v_perm dequant, single row, same launch
grid) — reaches **80.8%**.

```
4.219 GB/token / 236.4 GB/s / 0.808 = 22.1 ms/token  ->  45 t/s serial
```

vs measured **29.9 t/s**. That is a **~1.5× decode uplift** available if production hit the kernel's own
achievable efficiency. Example: **~29.9 → ~45 t/s serial**, MTP ~31 → ~45 t/s.

## Where the remaining gap must live (ruled out, in order)

Because K replicates the real algorithm's per-weight work and still hits 80.8%, the production deficit
is **not** in the dequant math. The remaining structural suspects:

1. **The multi-warp K-reduction.** Real `mmvq` uses several warps per row with a shared-memory
   reduction and spin-lock syncs (`tmp_shared`, `buf_iw`). K used one warp per buffer with no
   cross-warp reduction. That fixed per-kernel reduction cost, on ~150 small kernels per step, is the
   leading candidate for 80% → 52%.
2. **The one-warp-per-row grid** (`nrows_x` blocks) launched 150 times per step — per-kernel ramp
   dominates when each block does only a few K iterations.
3. Something outside the GEMV entirely (norms, router, HC, attention) — but the byte census says those
   are a minority, so this is third.

**Concrete next test:** build the *real* `mul_mat_vec_q` kernel into a standalone bench (not a fresh
kernel) at production shapes and time it; then flip one structural knob at a time (warps-per-row,
K-split, persistent grid) against the same interleaved A/B harness.

## Caveats (stated honestly)

- shapebench's I/K are proxies: single row, synthetic x, no q8_1 activation quantization, and they read
  `n_uint4` per buffer rather than the true 18-byte block count. They establish the **ceiling of the
  encoding** (~80%), not production's achieved rate.
- The 4.2 GB runs read >100% for some variants because the per-buffer working set partially fits L2.
  All conclusions use the **12 GB** runs.
- "45 t/s" assumes the whole 4.219 GB read set behaves like variant K. Only the IQ4_NL majority does;
  Q6_K/Q8_0/F32 differ. Treat 45 as an upper bound — the ~1.5× **gap** is the claim, not the exact
  figure.

## Artifacts

`kernel-work/shapebench.hip` (variants A–K), `shapebench.exe`. Repro:
`shapebench.exe 12.0 150 realistic` (needs `amdhip64_7.dll` + `amd_comgr.dll` + `amdocl64.dll` beside it).
