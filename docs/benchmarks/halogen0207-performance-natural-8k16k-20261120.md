# Halogen 0.20.7 OEM Performance natural 8K/16K serving

The collector bound this cohort to OEM mode `1` (Performance) and the active `REV:N Performance` Windows scheme. The reviewed provider receipt records the mode-1 readback before the current server run; it does not independently measure package wattage or clocks.

The server completed eight frozen non-repeated document requests. Each exact input has one excluded warmup and three fully retained measured requests, all producing 128 output tokens.

| Actual input tokens | Reported prefill tok/s | Reported decode tok/s | API neural-head accepted/drafted | Whole HTTP mean, s |
| ---: | ---: | ---: | ---: | ---: |
| 8192 | 1210.16 | 49.21 | 192/291 = 65.98% | 8.5557 |
| 16384 | 1216.51 | 49.72 | 180/279 = 64.52% | 14.6113 |

Rates are arithmetic means from native phase fields returned through the API, with `api_phase_clock_qualified=false` and `RAW_observer_used=false`. Whole-request time uses the independent HTTP QPC clock. Warmups are excluded from every headline mean, no faster sample was selected, and `causal_comparison=false`.

## Run-level observations

| Input | Run | Status | Prefill tok/s | Decode tok/s | Head accepted/drafted | Whole HTTP, s | Output SHA-256 |
| ---: | ---: | :--- | ---: | ---: | ---: | ---: | :--- |
| 8192 | 0 | warmup (excluded) | 724.808 | 42.314 | 64/97 = 65.98% | 13.1177009 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 1 | measured | 1200.381 | 51.904 | 64/97 = 65.98% | 8.4681346 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 2 | measured | 1220.792 | 43.897 | 64/97 = 65.98% | 8.7746820 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 3 | measured | 1209.312 | 51.828 | 64/97 = 65.98% | 8.4241757 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 16384 | 0 | warmup (excluded) | 1190.628 | 43.879 | 60/93 = 64.52% | 15.1974091 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 1 | measured | 1221.237 | 49.703 | 60/93 = 64.52% | 14.5647287 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 2 | measured | 1211.521 | 49.977 | 60/93 = 64.52% | 14.6493578 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 3 | measured | 1216.757 | 49.471 | 60/93 = 64.52% | 14.6197109 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |

Lookup and grammar counters remain separately available in the numeric summary. A zero drafted count has undefined acceptance. API head acceptance retains its source-derived scope and is not independently reconstructed.

## Observed comparison with the earlier 0.20.7 cohort

| Input | Earlier prefill | Performance prefill | Change | Earlier decode | Performance decode | Change | Earlier HTTP, s | Performance HTTP, s | Change | MTP acceptance |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8192 | 951.05 | 1210.16 | +27.25% | 45.09 | 49.21 | +9.14% | 10.4630 | 8.5557 | -18.23% | 192/291 = 65.98% |
| 16384 | 938.34 | 1216.51 | +29.65% | 43.54 | 49.72 | +14.18% | 18.5797 | 14.6113 | -21.36% | 180/279 = 64.52% |

Both deterministic output hashes and both accepted/drafted totals match the earlier 0.20.7 cohort. The OEM mode transition, server restart and separate collection window prevent assigning the entire difference causally to OEM mode, so this comparison remains observational.

## Observed comparison with 0.20.2

| Input | 0.20.2 prefill | Current prefill | Change | 0.20.2 decode | Current decode | Change | 0.20.2 acceptance | Current acceptance |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8192 | 1460.34 | 1210.16 | -17.13% | 47.99 | 49.21 | +2.55% | 192/312 = 61.54% | 192/291 = 65.98% |
| 16384 | 1414.62 | 1216.51 | -14.00% | 43.45 | 49.72 | +14.43% | 180/324 = 55.56% | 180/279 = 64.52% |

The 0.20.2 values are the published natural8192/16K reference collected with the same frozen workload and high-level request controls. The releases use different MTP gate rules: 0.20.7 is cost-based, while the 0.20.2 report records confidence gating. Neither deterministic cohort output hash matches the 0.20.2 reference. This separately collected release comparison is observational and not causal; the output difference also prevents treating it as an identical-completion speed comparison.

## Fixed controls and qualification

The run additionally binds OEM mode `1` (Performance) and Windows scheme `REV:N Performance`. The fixed model controls are v2, context/KV pool 32768, one slot and one concurrent request, paired 8192 prefill settings, cost-based MTP gate 0.90, PLD 3,3, decode prefetch zero, Cache/Thinking/Vision Off, temperature 0, seed 1, `prompt_cache_policy=no_store`, and 128 output tokens.

The lowest monitored request-time reserve was 27.32 GiB, calculated per sample as the lower of physical availability and commit headroom. The before/after terminal evidence retained the same ready runtime seal. This document makes no live-state claim beyond that snapshot.

All eight observations failed the necessary QPC enclosure check: each API phase sum exceeded its independently timed whole-HTTP duration. The API phase clock therefore remains unqualified; no correction, rescaling, or overhead subtraction was applied. No NPU speedup or full acceleration-goal completion is claimed.
