# Halogen 0.20.7 deployment confirmation: natural 8K/16K serving

The 22 November deployment-confirmation cohort completed all eight requests on the unchanged live `CurrentText32K` server. It records the following native API observations:

| Actual input tokens | Reported prefill tok/s | Reported decode tok/s | Native-head accepted/drafted | Whole HTTP mean, s |
| ---: | ---: | ---: | ---: | ---: |
| 8192 | **1618.895333** | **51.575000** | **192/291 = 65.9794%** | 7.567984 |
| 16384 | **1534.869667** | **49.656333** | **180/279 = 64.5161%** | 13.283862 |

Each row excludes one warmup and averages three measured requests. Every request used the exact frozen non-repetitive input, 128 output tokens, temperature 0, seed 1, Cache Off with `prompt_cache_policy=no_store`, Thinking Off, Vision Off, cost-based MTP gate 0.90 and PLD `3,3`.

These are native API phase-clock means, not independently observed RAW phase rates. All eight native phase sums now fit inside their corresponding Windows QPC whole-request durations, but enclosure alone does not qualify the phase clock or its individual boundaries. Accordingly, `api_phase_clock_qualified=false` and `RAW_observer_used=false` remain explicit.

## Retained runs

| Input | Run | Status | Prefill tok/s | Decode tok/s | Head accepted/drafted | Whole HTTP, s | Native phase sum, s | Output SHA-256 |
| ---: | ---: | :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| 8192 | 0 | warmup (excluded) | 839.473 | 34.217 | 64/97 = 65.98% | 13.5677212 | 13.4993 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 1 | measured | 1624.301 | 51.652 | 64/97 = 65.98% | 7.5486569 | 7.5215 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 2 | measured | 1609.114 | 51.412 | 64/97 = 65.98% | 7.6058522 | 7.5807 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 8192 | 3 | measured | 1623.271 | 51.661 | 64/97 = 65.98% | 7.5494416 | 7.5243 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 16384 | 0 | warmup (excluded) | 1237.425 | 36.893 | 60/93 = 64.52% | 16.7458225 | 16.7099 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 1 | measured | 1526.891 | 49.782 | 60/93 = 64.52% | 13.3315267 | 13.3015 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 2 | measured | 1531.401 | 49.682 | 60/93 = 64.52% | 13.3077689 | 13.2751 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
| 16384 | 3 | measured | 1546.317 | 49.505 | 60/93 = 64.52% | 13.2122896 | 13.1811 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |

Lookup and grammar proposed zero tokens in this workload. A zero drafted count has undefined acceptance. Native-head acceptance retains its API scope and was not independently reconstructed.

## Comparison with the preserved 20 November cohort

| Input | 20 Nov prefill | 22 Nov prefill | Change | 20 Nov decode | 22 Nov decode | Change | 20 Nov HTTP, s | 22 Nov HTTP, s | Change |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8192 | 1210.161667 | 1618.895333 | **+33.775%** | 49.209667 | 51.575000 | **+4.807%** | 8.555664 | 7.567984 | **-11.544%** |
| 16384 | 1216.505000 | 1534.869667 | **+26.170%** | 49.717000 | 49.656333 | **-0.122%** | 14.611266 | 13.283862 | **-9.085%** |

Deterministic output hashes and accepted/drafted totals match the 20 November cohort. The profile hash is unchanged, but the source manifest is not: the 20 November run pinned `1462ebcabd4a63bf93b027b9d59c9b87ce59c02ca1c699e1f4a8f840c97578a2`, whereas this run pins `574bfad341728635b13457cbdb1eb769f9f55be32a4d868f7ea1bad90e0970e0` after runtime-control hardening. The collector performed no lifecycle action. The source change, separate collection window and uncontrolled machine/runtime state prevent assigning the differences to a specific optimization. This is a deployment confirmation, not a causal A/B result, a new engine build, or proof of the publisher's release-to-release claim.

## Fixed controls and runtime seal

The server used Halogen API/engine 0.20.7, v2, one slot, context/slot/KV pool 32768, paired 8192 prefill settings, HT4 MTP, PLD `3,3`, decode prefetch zero and `REV:N Performance`. Profile SHA-256 was `69d28caee11c0e23eb2e8dba4bc0910ffbbeef7bde9656186baa4abf7cac385d`; source-manifest SHA-256 was `574bfad341728635b13457cbdb1eb769f9f55be32a4d868f7ea1bad90e0970e0`.

Before and after the cohort, controller run `2cda5a066fa44b7db3cc2dce41f27cf6` (PID 24704) and backend run `8a0dbfadefc04547afa6bbaee3387f46` (PID 23916) remained `ready` on port 8840 with zero active requests. The lowest request-sample reserve was 37.0413 GiB, above the unchanged 18 GiB runtime floor. Those identities and availability values are dated snapshots, not durable live-state claims.

The compact [machine-readable evidence](halogen0207-performance-natural-8k16k-20261122.json) retains all run values, qualifications and hashes. The failed pre-request `v1` wrapper attempt remains separately preserved under the local evidence tree and contributes no request or rate.
