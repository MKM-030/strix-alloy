# Measured bandwidth ceiling: 225–238 GB/s — the ~55% efficiency is real (2026-09-15)

Every efficiency claim in this project rested on an **assumed** 200–240 GB/s ceiling that had never been
measured on this box. I wrote a HIP microbenchmark (`bwtest.hip`) and measured it. **The assumption holds.**

## Measured

```
device: AMD Radeon(TM) 8060S Graphics
memBusWidth: 512 bit   memoryClockRate: 800 MHz
theoretical (prop-derived): 102.4 GB/s      <- the driver's own clock field is wrong/unused
```

| pattern | measured | note |
| --- | ---: | --- |
| **sequential read (fully coalesced)** | **235.7 / 238.5 GB/s** | two runs; the real usable ceiling |
| copy (read + write) | 208.2 GB/s combined | **104.1 GB/s each way** |

Note the driver reports `memoryClockRate = 800 MHz` and `memoryBusWidth = 512 bit`, which multiplies to a
nonsensical **102.4 GB/s** — *below* what we measure. The driver's clock field does not describe LPDDR5X
(800 MHz ≈ the 6400 MT/s per-pin rate misinterpreted). **Do not compute a ceiling from
`hipGetDeviceProperties`** — it is off by ~2.3×. Our 200–240 GB/s range was empirically right.

## What this validates

| claim | verdict |
| --- | --- |
| achievable read bandwidth ≈ 220 GB/s | **CONFIRMED** (235.7–238.5 measured) |
| serial decode at ~129 GB/s effective = ~55% of ceiling | **CONFIRMED** — the ~45% loss is **real**, not an artifact of an unreachable ceiling |
| efficiency flat 53–59% across verification width | **CONFIRMED** — same conclusion now on a measured denominator |

This was the single largest unverified assumption behind the last several analyses. It survived testing, so
the "uniform ~55% efficiency" finding stands and the search for the missing 45% is justified.

## Two clues about where the 45% goes

### 1. Per-row cost falls with width → fixed per-round cost, not a per-row inefficiency

From the width fit (`target_ms/round = 20.93 + 12.05 × rows`):

| rows | measured ms/round | **ms per row** |
| ---: | ---: | ---: |
| 2 | 46.16 | 23.1 |
| 3 | 54.80 | 18.3 |
| 4 | 70.15 | 17.5 |

**Per-row cost drops 23.1 → 17.5 ms and flattens.** That is the signature of cost that is **fixed per
round** (paid regardless of rows) amortising over more rows — not of a per-row inefficiency. Consistent
with the two-term fit: dense weights are read once per round, so they are paid by the *first* row.

### 2. Writes cost ~2.3× reads, and prefill is in a completely different regime

- **Copy achieves 104 GB/s each way vs 235 GB/s read-only.** Any read→write→read chain in the pipeline pays
  a real penalty, and `CPY`/`CONT`-style ops are therefore more expensive per useful byte than a pure read.
- **Prefill is compute-bound, not memory-bound.** At 1034 t/s with ub 16384, one weight sweep (4.25 GB)
  serves the whole 16384-token batch over ~15.9 s → only **~0.27 GB/s** of weight traffic. Prefill sits
  nowhere near memory bandwidth; it is GEMM-throughput-bound. This is why the compiler mattered so much
  (clang 21→24 = +60–71% prefill) and why memory-side work has not moved prefill.
  **Decode and prefill need different optimisations: decode is memory-bound GEMV, prefill is compute-bound GEMM.**

### 3. Stride sensitivity (context for scattered access)

| threads `step` uint4 apart | useful GB/s |
| ---: | ---: |
| 1 (coalesced) | 225.9 |
| 4 | 59.1 |
| 16 | 28.7 |
| 64+ | ≤7.0 |

Useful bandwidth collapses once consecutive threads stop sharing cache lines. **Caveat: this does not
implicate the expert path**, because expert matrices are ~900 KB contiguous blocks per expert — not
scattered micro-reads. It is relevant to any component that does touch small scattered rows (the 90-byte
PLE rows are the known example, and we measured their host cost at 0.05%).

## Honest limits

- Microbenchmark traffic is not decode traffic: real kernels mix reads, writes, dequant ALU and attention.
  **235 GB/s is the ceiling for a pure streaming read; it is not a claim that a GEMV must hit it.**
- Single grid/block config (1024×256) and one size (4 GB). A tuning sweep could shift the absolute number
  somewhat, though 235 GB/s is already well above the empirical 200–240 range quoted.
- The stride sweep's "useful GB/s" is a cache-line-utilisation artifact as much as a bandwidth one.

## What this changes

- **The 45% is real and worth hunting.** Confirmed against a measured ceiling.
- **The search should target fixed per-round cost and the expert path**, not "wide verify is expensive"
  (already shown proportional) and not scattered-access tuning (experts are contiguous).
- **Prefill and decode are separate problems** with separate bounds — a genuinely useful clarification for
  where to spend effort.
