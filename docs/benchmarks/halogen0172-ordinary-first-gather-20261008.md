# Halogen 0.17.2 ordinary-first-gather experiment — 2026-10-08

The candidate ran as **preload + stock fallback**. Its exact-version attachment marker was recorded, but **zero completed-row markers** were recorded. Copied-row execution and a serving improvement are unqualified. Numerically higher decode values remain diagnostic and are not attributed to the ordinary-first-gather path.

Halogen engine 0.17.2; backend `halogen-v2`, Qwen3.8 Flash Next checkpoint v2; context 262144, expected slot context/KV positions 262144, one expected slot and concurrency 1. Frozen requests use 8192 actual synthetic pseudoprose input tokens, including 116 repeated ` a` prefix units for token calibration, 1 or 128 output tokens, serial/MTP drafter, Cache Off, Thinking Off, temperature 0 and seed 1. Profiles request `draft_tokens=2`, `HALOGEN_PLD=3,3`, prefill chunk 8192 and maximum prefill tokens 8192. The draft_tokens setting does not independently establish a fixed per-round MTP depth.

The retained before/candidate/after prompt copies normalize to the same 42,238 LF bytes as `fixed-depth2-comparison/prompts/prompt-8192-prose.txt`, SHA256 `0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1`. Those bytes begin with 116 repeated ` a` units followed by `Weeks valley cheese clouds`.

## Measured requests

Each window/workload has three measured repetitions (rep1–3). Rep0 warmups are excluded. Rates use the frozen harness clock calibration; spread is sample standard deviation (n−1).

| Window | Workload | Prefill tok/s | Decode tok/s | Request wall s | Combined API MTP+PLD acceptance |
|---|---|---:|---:|---:|---:|
| stock-before | p8192-serial-tg1 | 1291.68 ± 15.14 | n/a | 6.3732 ± 0.0713 | n/a (0/0) |
| stock-before | p8192-mtp-tg128 | 1238.85 ± 24.94 | 43.03 ± 0.52 | 9.6196 ± 0.1174 | 210/339 = 61.95% |
| stock-before | p8192-serial-tg128 | 1288.33 ± 15.37 | 32.06 ± 0.23 | 10.3796 ± 0.0804 | n/a (0/0) |
| candidate preload + stock fallback | p8192-serial-tg1 | 1239.20 ± 23.02 | n/a | 6.6598 ± 0.1087 | n/a (0/0) |
| candidate preload + stock fallback | p8192-mtp-tg128 | 1187.08 ± 43.33 | 43.96 ± 0.54 | 9.8475 ± 0.2269 | 210/339 = 61.95% |
| candidate preload + stock fallback | p8192-serial-tg128 | 1202.24 ± 44.31 | 32.57 ± 0.17 | 10.7784 ± 0.2278 | n/a (0/0) |
| stock-after | p8192-serial-tg1 | 1261.00 ± 22.29 | n/a | 6.5307 ± 0.1137 | n/a (0/0) |
| stock-after | p8192-mtp-tg128 | 1226.59 ± 15.57 | 42.88 ± 0.10 | 9.6956 ± 0.0777 | 210/339 = 61.95% |
| stock-after | p8192-serial-tg128 | 1254.58 ± 17.39 | 31.95 ± 0.08 | 10.5678 ± 0.0906 | n/a (0/0) |

API `timings.draft_n_accepted` / `timings.draft_n` equals the saved harness accepted/drafted counters. Acceptance is the sum of accepted tokens divided by the sum of drafted tokens across measured requests; it combines MTP and PLD. Native head-only acceptance is unavailable.

## Pooled stock before + after

The stock pool uses six measured rows per workload. Its sample spread includes within-window variation and between-window drift. Candidate values above describe the fallback experiment.

| Workload | Stock pooled prefill tok/s | Stock pooled decode tok/s | Stock pooled request wall s | Stock pooled MTP+PLD acceptance | After vs before prefill / decode / wall |
|---|---:|---:|---:|---:|---:|
| p8192-serial-tg1 | 1276.34 ± 23.93 | n/a | 6.4520 ± 0.1210 | n/a (0/0) | -2.37% / n/a / +2.47% |
| p8192-mtp-tg128 | 1232.72 ± 19.77 | 42.96 ± 0.35 | 9.6576 ± 0.0983 | 420/678 = 61.95% | -0.99% / -0.35% / +0.79% |
| p8192-serial-tg128 | 1271.46 ± 23.61 | 32.01 ± 0.17 | 10.4737 ± 0.1284 | n/a (0/0) | -2.62% / -0.36% / +1.81% |

## Raw API rates and clocks

The frozen harness multiplies each raw API rate by its whole-request monotonic/raw factor. These factors do not independently establish phase-specific correction. The raw/QPC checks passed the existing helper allowance. Both raw and calibrated values are retained to expose this distinction.

| Window | Workload | Raw prefill tok/s | Raw decode tok/s | Measured monotonic/raw factor range |
|---|---|---:|---:|---:|
| stock-before | p8192-serial-tg1 | 1291.68 ± 15.14 | n/a | 0.999999759–1.000000044 |
| stock-before | p8192-mtp-tg128 | 1171.46 ± 71.19 | 40.66 ± 1.49 | 1.010981112–1.083333191 |
| stock-before | p8192-serial-tg128 | 1222.68 ± 71.16 | 30.42 ± 1.35 | 0.999999818–1.083333110 |
| candidate preload + stock fallback | p8192-serial-tg1 | 1239.20 ± 23.02 | n/a | 0.999999848–0.999999928 |
| candidate preload + stock fallback | p8192-mtp-tg128 | 1187.08 ± 43.33 | 43.96 ± 0.54 | 0.999999754–0.999999954 |
| candidate preload + stock fallback | p8192-serial-tg128 | 1202.24 ± 44.31 | 32.57 ± 0.17 | 0.999999750–0.999999986 |
| stock-after | p8192-serial-tg1 | 1261.00 ± 22.29 | n/a | 0.999999926–1.000000026 |
| stock-after | p8192-mtp-tg128 | 1226.59 ± 15.57 | 42.88 ± 0.10 | 1.000000065–1.000000179 |
| stock-after | p8192-serial-tg128 | 1254.58 ± 17.39 | 31.95 ± 0.08 | 1.000000111–1.000000223 |

## Excluded warmups

One rep0 per window/workload is retained here separately. Warmups contribute no measured mean, pooled stock result, or measured acceptance ratio.

| Window | Workload | Calibrated prefill tok/s | Calibrated decode tok/s | Request wall s | Accepted/drafted |
|---|---|---:|---:|---:|---:|
| stock-before | p8192-serial-tg1 | 1289.85 | n/a | 6.3794 | 0/0 |
| stock-before | p8192-mtp-tg128 | 1261.12 | 33.80 | 10.3132 | 70/113 |
| stock-before | p8192-serial-tg128 | 1295.63 | 31.48 | 10.4163 | 0/0 |
| candidate preload + stock fallback | p8192-serial-tg1 | 1302.09 | n/a | 6.3210 | 0/0 |
| candidate preload + stock fallback | p8192-mtp-tg128 | 1220.19 | 33.39 | 10.5763 | 70/113 |
| candidate preload + stock fallback | p8192-serial-tg128 | 1230.45 | 31.20 | 10.7941 | 0/0 |
| stock-after | p8192-serial-tg1 | 1271.40 | n/a | 6.4731 | 0/0 |
| stock-after | p8192-mtp-tg128 | 1226.38 | 33.68 | 10.5098 | 70/113 |
| stock-after | p8192-serial-tg128 | 1238.36 | 30.74 | 10.8087 | 0/0 |

## Parity and evidence

| Matching workload | Request hash parity | Prompt hash parity | Measured output hash parity |
|---|---|---|---|
| p8192-serial-tg1 | True | True | True |
| p8192-mtp-tg128 | True | True | True |
| p8192-serial-tg128 | True | True | True |

All windows also match serial/MTP measured output hashes for the 128-token workload. Exact parity does not qualify copied-row coverage. No NPU execution, NPU serving gain, long-input improvement, or sustained/generalized improvement is established by this experiment.

Numerical evidence, hash pins, clock factors, sample variances and runtime qualification are in [halogen0172-ordinary-first-gather-20261008.json](halogen0172-ordinary-first-gather-20261008.json). Public CPU-only sources: [analyzer](../../scripts/benchmarks/experimental/analyze_halogen0172_ordinary_first_gather.py) and [publisher](../../scripts/benchmarks/experimental/publish_halogen0172_ordinary_first_gather.py). Pass the private frozen work directory with `--work`; run the analyzer first, then the publisher with `--publish`. No benchmark, engine, or lifecycle module is imported by either source.
