# Applying olliehm's recommendations to our engine — measured (2026-09-16)

Following `engine-comparison-vs-olliehm-20260916.md`, we took the three concrete adjustments his repo
suggests and measured each on **our** engine, at the same depth, same prompt, same model, full server
restart per arm. Baseline is our current production config.

## The arms

| arm | MTP | batch | checkpoints |
| --- | --- | --- | --- |
| **A** ours (baseline) | `n-max 2, p-min 0.0` | `-b/-ub 8192` | default |
| **B** his MTP point | `n-max 4, p-min 0.75` | `-b/-ub 2048` | default |
| **C** his MTP point + his checkpointing | `n-max 4, p-min 0.75` | `-b/-ub 2048` | `--ctx-checkpoints 8 --cache-ram 3072` |
| **D** our MTP point + checkpointing | `n-max 2, p-min 0.0` | `-b/-ub 8192` | `--ctx-checkpoints 8 --cache-ram 3072` |

## Results (65536-token prompt, gen 256, median of warm reps)

| arm | prefill t/s | decode t/s | acceptance |
| --- | ---: | ---: | ---: |
| A-ours | 897.8 | 29.25 | 47% |
| B-his-mtp | 733.0 | 27.14 | **88%** |
| C-his-mtp+ckpt | 732.4 | 27.22 | **88%** |
| **D-ours+ckpt** | **903.6** | **33.01** | 65% |

## Findings

**1. His MTP operating point reproduces his acceptance, and costs us throughput.** B lands at **88%**
acceptance (his published range is 85–100%) — so his config is genuine and our engine reproduces it.
But decode is **27.14 t/s vs our 29.25**, and prefill drops to 733 (the `-b/-ub 2048` batch shape).
Raising `n-max` to 4 buys acceptance we did not need at the cost of a 5-row verify every round. We keep
our default and note his point as an option.

**2. Checkpointing changed nothing for his config** (B 27.14 → C 27.22, acceptance identical at 88%).
Our fork already carries the recurrent-state mechanism, so his "mandatory" warning is satisfied by
construction — consistent with the PR26 fix we verified earlier (`need_n_rs_seq()` includes
`DRAFT_MTP`).

**3. The surprising one — arm D — was an artifact. RETRACTED by the paired re-run.**

Arm D (our config + `--ctx-checkpoints 8`) first measured 33.01 t/s at 65% against arm A's 29.25 t/s at
47%, which looked like a +13% checkpointing win. The interleaved confirmation destroyed it:

| run (identical config: `n-max 2, p-min 0.0, -b/-ub 8192`) | prefill | decode | acceptance | drafts |
| --- | ---: | ---: | ---: | ---: |
| omp-ours-n2-p000 | 911 | 33.46 | 65% | 444 |
| **hcb-A-ours** | 898 | **29.25** | **47%** | **632** |
| ckc-plain-r1 | 862 | **32.84** | **65%** | 222 |
| ckc-ckpt-r1 | 860 | **32.94** | **65%** | 222 |
| hcb-D-ours+ckpt | 904 | 33.01 | 65% | 444 |

**Checkpointing changes nothing**: interleaved plain 32.84 vs ckpt 32.94 t/s, with *identical* draft
counts (144/222 both). Four of five runs of the same config sit at 65% acceptance; the 47% reading was
the outlier.

## The real finding: our MTP acceptance is not reproducible run-to-run

Same binary, same model, same flags, same prompt, same depth — acceptance has been measured at both
**47%** and **65%**, i.e. **29.25 vs 33.46 t/s**, a 14% swing. The outlier is distinguishable by its
draft count (**632** vs 222/444), which means it took structurally more verification rounds for the same
generated output. So this is not measurement noise on t/s: the *draft path itself* behaved differently.

This is exactly the hazard olliehm documents (*"MTP on HIP is the risky path… can still show 2× tok/s"*),
and it is the **most important thing we learned from his repo**, because it invalidates the way we have
been reporting decode: a single arm can look like a 14% win and be nothing but an unlucky run.

**Consequences we are adopting:**

1. **No MTP number is quoted from fewer than 3 runs, and acceptance is always reported alongside t/s.**
2. **Before any future MTP claim, log the draft path's own state** (rounds, per-position survival,
   draft count) — the coverage-probe discipline we already use for kernels.
3. **Investigate the instability directly** as the next MTP task, ahead of further tuning: find what
   makes a run degenerate to ~47%. Candidates: draft-state carry-over between requests, the
   prefill/draft KV interaction, or the recurrent rollback path. This is a correctness-adjacent bug, not
   a tuning opportunity.

## What we adopted from his repo

| item | verdict |
| --- | --- |
| `n-max 4, p-min 0.75` MTP point | his acceptance reproduces (88% here, 85–100% his); costs us throughput. Keep as an option, not the default. |
| `--ctx-checkpoints` + `--cache-ram` | **no measurable effect on our fork**; harmless, kept in the launch line |
| `-b/-ub 2048` batch shape | costs prefill (733 vs 898); we keep 8192 |
| **sequence-level correctness gates** | **adopted as required practice** — see finding above |
| his component-level footprint table | adopted as the way to report fit |
| `stew675/rdna-boosts` patch set | still the highest-value unmined external source |

## Artifacts

`kernel-work/his-config-bench.ps1`, `kernel-work/ckpt-confirm.ps1`;
`results/hcb-*.{json,log,err}`, `results/his-config-bench.json`, `results/ckpt-confirm.json`,
`results/omp-compare.json` (the earlier conflicting measurement).
