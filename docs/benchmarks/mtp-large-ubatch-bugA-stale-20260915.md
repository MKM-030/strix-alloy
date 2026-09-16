# MTP with a large ubatch: Bug A is stale, and prefill recovers (2026-09-15)

## Question

Prior work forced `-b/-ub 2048` **whenever the MTP draft head is attached** ("Bug A": `-b/-ub 8192`
allegedly made the draft load die with `invalid vector subscript`). That is a real cost: the fast
prefill shape is `ub 16384` (~1057 t/s @16k), but it was believed unusable together with MTP, so MTP
runs were stuck at ~778 t/s prefill. B1's load-only repro already showed ub 8192 *loads* with a draft;
this sweep goes further and **actually generates**, which is where Bug A's error would fire if it were
still live (at first graph build).

## Result: all three ubatch sizes load AND generate with MTP

`kernel-work/ub-mtp-sweep.ps1`, PROJFIX + shared MTP head, n-max 2, `-c 32768`, 3 reps, gen 128.
rep-0 is cold (first prefill unmapped) and is excluded from the summary columns below.

| ub | prefill @1k | @8k | @16k | decode @1k | @8k | @16k | acceptance @1k / @8k / @16k |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2048 | 558 | 796 | 778 | 34.9 | 27.2 | **34.5** | 62.5% / 53% / 49% |
| **8192** | 618 | **936** | 932 | 30.7 | **31.3** | 29.2 | 62.5% / 53% / 49% |
| **16384** | 487 | **942** | **970** | 34.4 | 31.0 | 28.6 | 62.5% / 53% / 49% |

Raw logs: `results/ubm-ub{2048,8192,16384}.log`; JSON `results/ubm-ub*.json`.

## What is robust here

1. **Bug A is stale.** `-b/-ub 8192` and `-b/-ub 16384` both load the shared MTP head and complete a
   full generation with identical acceptance to ub 2048. The `-ub 2048` restriction on MTP is no longer
   required. (Root cause of the original failure is not re-derived here; what matters is that it does
   not reproduce on the current binary — consistent with `shared-mtp-fit-report.md`.)
2. **Acceptance is ubatch-independent.** 62.5% @1k, ~53% @8k, ~49% @16k at *every* ub. Batch size
   does not change draft quality, so this is not a knob for acceptance (as expected — acceptance is
   argmax agreement, per `acceptance-metric-frozen-20260915.md`).
3. **Prefill at depth clearly improves with a larger ubatch.** @8k: 796 → 936 → 942 t/s; @16k:
   778 → 932 → 970 t/s. That is **+18–25% prefill** from lifting the restriction. ub 16384 with MTP
   reaches **970 t/s @16k**, only ~8% below the no-MTP 1057 t/s best.

## What is not clean (stated honestly)

The **decode** column does not show a consistent ub effect: big ub is *faster* at 8k (31.0–31.3 vs
27.2) but *slower* at 16k (28.6–29.2 vs 34.5). Those two together cannot both be a simple "ub helps/hurts
decode" story, and the 8k vs 16k prompts have different content, so the per-size decode figure is
confounded by prompt/acceptance trajectory. Treat the decode-vs-ub relation as **open** and needing a
paired same-prompt test; do not pick a ubatch on decode grounds yet. The prefill effect is the part
that reproduces across both depths.

## Practical recommendation

- **Lift the `-ub 2048`-with-MTP restriction.** It was based on a failure that no longer reproduces.
- **If prefill matters at depth**, run MTP at `-b/-ub 8192` (balanced: ~930 prefill @8–16k, decode
  ~29–31) or `-ub 16384` (max prefill ~970 @16k). The old max-prefill-shape `-ub 16384` is now
  usable *with* MTP.
- **If pure decode matters**, ub 2048 still shows the best single 16k decode figure (34.5), but this
  needs the paired confirmation above before it is trusted as a ub effect rather than content noise.

## Artifacts

`kernel-work/ub-mtp-sweep.ps1`; `kernel-work/results/ubm-ub*.{log,json,err}`; this doc.
