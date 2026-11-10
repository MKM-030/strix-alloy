# Halogen 0.20.1 natural 8K/16K API observations

On 10 November 2026, **Halogen 0.20.1** completed both genuine contiguous novel-prefix workloads: one excluded warmup and three measured repetitions per input size. These are complete serial cohorts on the one-slot 32K v2 text profile.

| Actual input tokens | API-reported prefill tok/s | API-reported decode tok/s | API-reported head accepted/drafted | Whole HTTP QPC mean, s |
| ---: | ---: | ---: | ---: | ---: |
| 8,192 | 1276.59 | 46.95 | 189/318 = 59.43% | 9.208794 |
| 16,384 | 1103.35 | 40.02 | 165/327 = 50.46% | 18.110871 |

The phase-rate columns are arithmetic means of three API-reported values. Acceptance sums the API's all-neural head accepted and drafted counters over those same three requests. Warmups are excluded. Lookup and grammar each proposed zero tokens.

**Acceptance scope:** the API head includes single-step head drafts outside the native diagnostic chain counter. Later source review explains why a chain-only trace can differ from these API totals. The existing trace omits a field required to independently reconstruct full accepted totals. These remain API-reported acceptance observations; no fixed offset or counter correction has been applied.

**Clock scope:** API phase clocks remain independently unqualified (`api_phase_clock_qualified=false`); no RAW observer ran (`RAW_observer_used=false`). Windows QPC measured the whole HTTP response before persistence. Reported phase durations fit inside that interval for all eight requests; residuals range from 28.915 to 83.534 milliseconds. These API observations do not establish an independently measured phase-speed improvement or manufacturer parity.

## Frozen requests and serving profile

Both inputs are genuine contiguous *War and Peace* prefixes followed by the frozen story instruction and explicit closed Thinking Off frame, with no padding or added corpus repetition. Actual native input counts are exactly 8192 and 16384. Both use `/v1/completions`, 128 actual output tokens, temperature 0, seed 1, native MTP, Cache Off and `prompt_cache_policy=no_store`. Every response finishes at length, reports zero cache reuse and zero reasoning tokens.

The configuration is v2, one slot, context/pool 32768, concurrency 1, paired 2048-token prefill chunk/arena, adaptive MTP gate 0.90, PLD `3,3`, Vision Off, Thinking Off/low and prefetch 0. Request entry required 22/22 GiB physical/commit headroom; runtime retained 18/18 GiB. Every saved before/after GPU check had no actual game process and no nonzero GPU engine load.

The controller/backend run IDs are `107c1fe3e0db42d492d81438d22a77f2` and `50be3c92c293476f931089d70c17ae92`. Actual ready API/engine versions match 0.20.1 before and after collection. Profile SHA256: `06df227385b7f6de97d1de0123c08f70a544cad9396ab4aedbd6d2607598a128`.

## Output identity and evidence

| Actual input tokens | Within-cohort output SHA256 |
| ---: | --- |
| 8,192 | `eed0e9bf07effec4daf4650c7647b9c3e39323b50307e32882eeeda0a34fe6cc` |
| 16,384 | `0cf493d551bddf5f93b2f5cd3a303f086585e08b81b6bca2bb357f03c54d07c0` |

Each case produced the same output hash across its warmup and all three measured requests. The [numeric report](halogen0201-natural8k16k-20261110.json) retains all eight samples, warmup labels, native timing/counter fields, scoped acceptance, output hashes, whole-HTTP observations, runtime identities and SHA256 pins for requests, source, readiness and raw responses.

Earlier releases and profiles retain their separate workload and clock qualifications. This record changes engine version from the historical 0.19.1 cohort; it does not claim a controlled cross-version gain. No NPU performance comparison or manufacturer-workload comparison was performed.

The API endpoint remains `http://127.0.0.1:8840/v1`, public model `halogen-v2`. Use the existing protected ServiceNow credential. [ServiceNow integration](../integrations/halogen-servicenow.md).
