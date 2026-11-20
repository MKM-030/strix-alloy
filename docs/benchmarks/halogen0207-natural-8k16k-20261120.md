# Halogen 0.20.7 natural 8K/16K serving

The server completed eight frozen non-repeated document requests. Each exact input has one excluded warmup and three fully retained measured requests, all producing 128 output tokens.

| Actual input tokens | Reported prefill tok/s | Reported decode tok/s | API neural-head accepted/drafted | Whole HTTP mean, s |
| ---: | ---: | ---: | ---: | ---: |
| 8192 | 951.05 | 45.09 | 192/291 = 65.98% | 10.4630 |
| 16384 | 938.34 | 43.54 | 180/279 = 64.52% | 18.5797 |

Rates are arithmetic means from native phase fields returned through the API, with `api_phase_clock_qualified=false` and `RAW_observer_used=false`. Whole-request time uses the independent HTTP QPC clock. Warmups are excluded from every headline mean, no faster sample was selected, and `causal_comparison=false`.

## Run-level observations

| Input | Run | Status | Prefill tok/s | Decode tok/s | Head accepted/drafted | Whole HTTP, s | Output SHA-256 |
| ---: | ---: | :--- | ---: | ---: | ---: | ---: | :--- |
| 8192 | 0 | warmup (excluded) | 596.007 | 29.307 | 64/97 = 65.98% | 16.5200163 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 1 | measured | 972.564 | 44.856 | 64/97 = 65.98% | 10.3378133 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 2 | measured | 920.129 | 45.206 | 64/97 = 65.98% | 10.6957558 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 3 | measured | 960.443 | 45.201 | 64/97 = 65.98% | 10.3555145 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 16384 | 0 | warmup (excluded) | 879.428 | 32.371 | 60/93 = 64.52% | 20.5680399 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 1 | measured | 941.052 | 43.676 | 60/93 = 64.52% | 18.5248741 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 2 | measured | 935.133 | 43.450 | 60/93 = 64.52% | 18.6417261 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 3 | measured | 938.820 | 43.506 | 60/93 = 64.52% | 18.5723975 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |

Lookup and grammar counters remain separately available in the numeric summary. A zero drafted count has undefined acceptance. API head acceptance retains its source-derived scope and is not independently reconstructed.

## Observed comparison with 0.20.2

| Input | 0.20.2 prefill | Current prefill | Change | 0.20.2 decode | Current decode | Change | 0.20.2 acceptance | Current acceptance |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8192 | 1460.34 | 951.05 | -34.88% | 47.99 | 45.09 | -6.04% | 192/312 = 61.54% | 192/291 = 65.98% |
| 16384 | 1414.62 | 938.34 | -33.67% | 43.45 | 43.54 | +0.23% | 180/324 = 55.56% | 180/279 = 64.52% |

The 0.20.2 values are the published natural8192/16K reference collected with the same frozen workload and high-level request controls. The releases use different MTP gate rules: 0.20.7 is cost-based, while the 0.20.2 report records confidence gating. Neither deterministic cohort output hash matches the 0.20.2 reference. This separately collected release comparison is observational and not causal; the output difference also prevents treating it as an identical-completion speed comparison.

## Fixed controls and qualification

The fixed controls are v2, context/KV pool 32768, one slot and one concurrent request, paired 8192 prefill settings, cost-based MTP gate 0.90, PLD 3,3, decode prefetch zero, Cache/Thinking/Vision Off, temperature 0, seed 1, `prompt_cache_policy=no_store`, and 128 output tokens.

The lowest monitored request-time reserve was 26.02 GiB, calculated per sample as the lower of physical availability and commit headroom. The before/after terminal evidence retained the same ready runtime seal. This document makes no live-state claim beyond that snapshot.

All eight observations failed the necessary QPC enclosure check: each API phase sum exceeded its independently timed whole-HTTP duration. The API phase clock therefore remains unqualified; no correction, rescaling, or overhead subtraction was applied. No NPU speedup or full acceleration-goal completion is claimed.
