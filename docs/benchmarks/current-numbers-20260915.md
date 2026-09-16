# Where we are now — measured numbers (2026-09-15)

Single sheet for the "give me some numbers where we are at now" ask. Every figure here is measured on
this box; where a number is a claim from someone else it says so.

## Box

AMD Ryzen AI Max+ 395, Radeon 8060S (gfx1151, RDNA3.5, wave32), 128 GB LPDDR5X,
**96 GB dedicated carve**, Windows 11 + WSL2 over `/dev/dxg` (no `/dev/kfd`, no PM4 replay).
Native Windows build: TheRock 10.2 SDK, **clang 24.0.0git**, `GGML_HIP=ON`.

## Best measured results (ours)

| configuration | prefill @1k | @8k | @16k | @32k | decode @1k | @8k | @16k | @32k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **PROJFIX, ub 16384** (prefill shape, no drafter) | 710 | 1021 | **1057 / 1029** | **1035 / 1019** | 30.1 | 28.9 | 29.2 | 28.8 |
| **PROJFIX, ub 2048 + MTP n-max 2** (decode shape) | 653 | 799 | 782 | — | **35.5** | 30.2 | **32.8** | — |
| **PROJFIX, ub 2048 + MTP n-max 1** (decode shape) | 658 | 797 | 786 | — | 34.9 | 30.3 | 31.4 | — |
| PROJFIX, no MTP (baseline) | 700 | 846 | — | — | 29.9 | 28.6 | — | — |

The two prefill columns show **before / after the ilintar rebase** (same within noise). The **@16k MTP
decode cell is 32.8 t/s**, taken from the raw `ab-shared-n2.json` rep-1 row (139/230 accepted) — an earlier
draft of this sheet mis-transcribed it as 30.2, which is the *8k* figure. Decode at 16k is **higher** than at
8k because acceptance recovers (70% at 16k vs 63% at 8k); this is a real, reproducible shape, not noise.
| UD-IQ4_XS ub 8192 (reference quant) | 695 | — | 1000 | — | 24.3 | — | 23.2 |

Head used for MTP rows: `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf`. All values are rep-1 (page-cache
warm); rep-0 is contaminated by lazy-mmap paging and is not reported. `r-sweep.ps1` / `ab-heads.ps1`
raw JSON in `kernel-work/results/`.

## The decode cost model (measured, not inferred)

Fit from the no-MTP / n-max-1 / n-max-2 triple at high repeat:

```
S(k) = (1 + A_k) / (k·r + 1)     r = 0.47  (0.45–0.54 across n-max and depth)
```

- **r ≈ 0.47**: one draft step costs **half a target step in time**, but only ~0.15 in bytes
  (draft step ~660 MB vs target step ~4.25 GB). The draft step is **~70% fixed per-step overhead**.
- Active weight payload: **4.254 GB/token** (dense/other 2.927 + routed experts 1.327) → serial ceiling
  **47–56 t/s**. Serial decode runs at 55–66% of the ceiling (bandwidth-bound); the MTP point runs at
  only **24–29%** (overhead/acceptance-bound).

## Head-to-head with the public references

| stack | prefill | decode | notes |
| --- | ---: | ---: | --- |
| **ours** (PROJFIX + MTP, Windows clang 24) | **1057** @16k | **35.5** @1k | this session |
| ilintar `strix-halo` (published) | **1204** @0, 1086 @40k | 26.3 @0, 16.6 @40k | ub 16384 one batch, **no MTP**, retained-PM4 runtime |
| olliehm Windows port (published) | 964–1045 | ~35 (device-ckpt MTP) | confirms our numbers; HC16=0 recipe |
| Halogen (peonist-ai, commenter) | — | 41.65 @105k ctx | commits 1.65/round; closed source |
| Halogen target (author) | — | "at the hardware wall" | says only 5–10% prefill left |
| EngramHalo (advertised) | 192 @131k (2×) | 39.3 with MTP | QSA sparse gather |

**Reading:** our **decode beats ilintar's published decode** (35.5 vs 26.3) because we run MTP and they
run a plain decode; our **prefill trails theirs** (1057 vs 1204) because they batch the whole prompt as
one 16384 ubatch and use the retained-PM4 runtime. Both gaps have a named cause.

## Frontier/reference decode numbers we have NOT reached

| reference | decode | caveat |
| --- | ---: | --- |
| Halogen @105k ctx | 41.65 | their trunk + closed engine |
| EngramHalo with MTP | 39.3 | advertised, not independently reproduced |
| ROCmFPX ROCmFP4_FAST + MTP | 30.6–36.0 | FP4 quant; needs FP4 kernels we do not have |
| Halogen at depth | 25.4 (serial) | their low-depth serial figure |

## Instruction throughput on the box

| | value |
| --- | ---: |
| best prefill | **1057 t/s @16k** (ub 16384) |
| best decode | **35.5 t/s @1k** (MTP n-max 2, ub 2048) |
| best decode at depth | **32.8 t/s @16k**, 30.2 @8k |
| serial ceiling (bytes) | 47–56 t/s |
| measured fraction of ceiling (serial) | 55–66% |
| measured fraction of ceiling (MTP) | 24–29% |

## What is exhausted vs open

**Exhausted (measured, all ≤ noise):** n-max 3–8 (monotonically worse), n-gram cascade ahead of MTP
(worse), PR #28118 device checkpoints (~0%, branch already uses `rs_rollback`), `--spec-draft-p-min 0.75`
(0%), standalone vs shared head (0%), `--lazy-mode on-direct` (0% on decode), **FR-Spec 65k head**
(+2%/-4%, a wash — and its fault was my converter's alignment bug, now fixed).

**Open, with named mechanisms:**
1. **Rebase onto pwilkin `40a9f4d01`** — drops 53 env gates, fuses the F32 PLE cast, carries a
   QSA-determinism fix. `ac1ebb4e0` measured pp16384 1223 t/s with no env vars.
2. **Vulkan `SHMEM_STRIDE_PAD` 4→6** (PR #28941) — one constant, +4.5–18.5% prefill on Strix Halo.
3. **Halogen BYO-GGUF (0.7.0+)** — same PROJFIX weights, direct comparison; native Linux only (no WSL2).
4. **Draft head** — the only decode lever with real headroom; harness now built (see
   `draft-head-harness-20260915.md`).
5. **Retained-PM4 command lists** — where ilintar's decode lives; we do not have it.
6. **IOMMU off** — +1.8–31.6% prefill but disables the NPU (founder decision).
