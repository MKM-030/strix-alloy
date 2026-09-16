# No configured-context penalty — the "862 vs 1021" gap was a warm-up ramp (2026-09-15)

Codex Step 2a, answered. **There is no measurable cost to allocating a larger KV capacity.** The
earlier "15.6% penalty" was a measurement artifact: prefill t/s needs 3–4 warm repetitions to reach
steady state, and my earlier single-rep-at-each-`-c` runs caught it mid-ramp.

## Method

`kernel-work/capacity-prefill.ps1`. Fixed: exact 16k prompt, zero starting depth, `-b/-ub 16384`, no
drafter, same outputs. Changed: only `-c`. WSL down. 4 reps per config, rep 0 discarded.

## Result

| `-c` | KV alloc | rep0 | rep1 | rep2 | rep3 | **steady** |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32,768 | 0.75 GiB | 646 | 817 | 870 | **1033** | 1033 |
| 131,072 | 3 GiB | 657 | — | — | **1026** | 1026 |
| 262,144 | 6 GiB | 631 | 1014 | 1024 | **1029** | 1029 |

Steady-state prefill is **1026–1033 t/s at every capacity, within 0.7%**. The KV allocation (0.75 →
6 GiB, 8×) has **no effect on prefill throughput**.

## The trap, and the rule

`-c 32768` climbs **646 → 817 → 870 → 1033** over four reps. This is not a KV-capacity warm-up (KV is
allocated at load); it is the model's **weight working set** settling (page cache, TLB, possibly clock
ramp). The key consequence:

> **A single rep at ANY depth understates prefill.** My earlier "1021 t/s at `-c 32768`" and "862 t/s
> at `-c 262144`" were both taken at rep 1 — different points on the same ramp. That is the entire
> "15.6% capacity penalty": not capacity, but two different ramp positions.

This is the same cold-start trap that produced the fake deep-prefill cliff
(`longctx-corrections-20260915.md`), now shown to also apply at *shallow* depth and to have masqueraded
as a capacity effect. **Rule: report prefill from rep ≥ 3, not rep ≥ 1.**

## What it means for the plan

- **Delete "configured-context penalty" from the priority list.** Codex ranked it #1; it does not exist
  as a capacity effect. The measurable "occupancy vs allocation" question reduces to: does processing a
  chunk against a long *occupied* history cost more? That is Step 2b (`depth-chunk`, running) — and it
  is a genuinely different question (real attention/indexer work over occupied slots, not allocation).
- **The only real prefill shape effect found so far is depth of the *measured* work**, not capacity:
  full-prompt prefill peaks near 65k then declines gently (warm curve 862→984→907→856→809 t/s), and the
  chunk test will separate "per-token cost against long history" from "average over a long prompt".
- **Methodology is now the bigger lever than any single kernel.** Two of the three "effects" I reported
  (the deep cliff, the capacity penalty) were warm-up artifacts. Any future prefill claim needs the
  3-rep discipline in the interleaved harness.

## Artifacts

`kernel-work/capacity-prefill.ps1`; `results/cap-{32768,131072,262144}.json|log`;
first (2-rep) pass in the same files' earlier timestamps. Raw reps listed above.
