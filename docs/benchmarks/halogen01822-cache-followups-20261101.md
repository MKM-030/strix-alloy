# Halogen 0.18.22 cache follow-up comparison

One engine, one slot: Cache Off → Flexible → Off. The frozen workload uses a stable natural document and a changed final question. This measures follow-up latency and avoided work; it does not change the CacheOff Prefill/Decode headline.

Recorded dispatched requests: 28 of 28 planned. Normal serving is restored on port 8840 with its original profile and all 44 normal source members unchanged.

| Arm / turn | Actual full input range | Cache counts | Processed counts | Output counts | First-content mean (s) | DONE mean (s) | Native head accepted/drafted |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| before / turn1 | 8126–8126 | [0, 0, 0] | [8126, 8126, 8126] | [34, 34, 34] | 4.130281 | 4.893883 | 45/76 |
| before / turn2 | 8121–8121 | [0, 0, 0] | [8121, 8121, 8121] | [20, 20, 20] | 4.211215 | 4.450131 | 42/48 |
| candidate / turn1 | 8126–8126 | [0, 0, 0] | [8126, 8126, 8126] | [34, 34, 34] | 4.601054 | 5.163577 | 45/76 |
| candidate / turn2 | 8121–8121 | [8064, 8064, 8064] | [57, 57, 57] | [20, 20, 20] | 0.324077 | 0.558341 | 42/48 |
| after / turn1 | 8126–8126 | [0, 0, 0] | [8126, 8126, 8126] | [34, 34, 34] | 4.488327 | 5.052069 | 45/76 |
| after / turn2 | 8121–8121 | [0, 0, 0] | [8121, 8121, 8121] | [20, 20, 20] | 4.335307 | 4.573703 | 42/48 |

Each measured turn below is compared separately with each control; controls are not averaged.

- Candidate turn1 versus before: first-content mean reduction -11.40%; DONE mean reduction -5.51%; exact output/full-input parity True.
- Candidate turn2 versus before: first-content mean reduction +92.30%; DONE mean reduction +87.45%; exact output/full-input parity True.
- Candidate turn1 versus after: first-content mean reduction -2.51%; DONE mean reduction -2.21%; exact output/full-input parity True.
- Candidate turn2 versus after: first-content mean reduction +92.52%; DONE mean reduction +87.79%; exact output/full-input parity True.

Cold first turns are slower with Flexible: first-content latency rises by
11.40%/2.51% and DONE latency by 5.51%/2.21% against the two respective controls.
The gain applies to follow-ups that actually reuse the stable prefix. The
follow-up native head acceptance stays **42/48 = 87.50%** in all three arms;
this experiment does not establish a general MTP acceptance improvement.

The optional PowerShell 5.1 launcher preset `FollowupText32K` exposes the measured
Flexible configuration. `CurrentText32K` remains Cache Off, and the restored
running server retains that original profile. Seven portable PS5.1 tests verify
that the new preset differs only in the cache mode and preserves authentication,
capacity, reserves, sampling and refusal behavior. No instance SDK configuration
was changed.

Candidate A/B/A/B ground-truth and cache-hit isolation gate: True. All four sentinel requests are excluded from latency headlines.

Each complete arm has one excluded warmup pair and three measured pairs. The candidate also has four isolation-only requests. Output is capped at 128 but actual positive counts can be shorter. Full input equals cached plus newly processed input; actual token lengths come from complete response usage, not character estimates. The private document contains 32,693 Unicode characters / 33,397 UTF-8 bytes and is a separate workload from the historical exactly 8K/16K requests.

First-content latency excludes the empty assistant-role frame and ends at the chunk completing the first nonempty content event. DONE latency ends at the completed DONE event. Exact raw chunk byte ranges and receipt QPC stamps were replayed through the frozen final public parser. Native head/lookup/grammar acceptance is pooled from accepted/drafted counts, not averaged percentages. Matching JSON retains per-request counts, selected hashes, QPC endpoints, distributions, phase observations and both control comparisons.

No prompt bodies, generated text, credentials or complete private manifests are published. Quality parity is a separate gate from transport validity and complete capture; cache numerical ties may change otherwise valid output. No ServiceNow instance or source change is deployed by this report.

Evidence:

- `server/.local/halogen-update-20261101/primary01822/cache-followup-finite-comparison/handle.json` — `ec8d9528283c12cb6fcc74e3a2e08b170c7c9a611693c7743c0cd7f847918a16`
- `server/.local/halogen-update-20261101/primary01822/cache-followup-finite-comparison/normal-left-ready.json` — `f13a2685524948295e4662bf98b4e401da20ae77ecd09c05587eb16353ebd258`
- `server/.local/halogen-update-20261101/primary01822/serving01822-text32k.json` — `53a943ec4c61d0f3c057d13da561d5551720fe65d29b9a5a2bff39b7cc5566a1`
- `backends/halogen-wsl2-0.18.22/.local/services/dd974efa8c244b5cb24447c8f1fdb4ad/manifest.json` — `301c8d906eaa7d19729d30ef5aaa8bc08c3e79dc03dc77ceff19ac686879a01b`
- `server/.local/halogen-update-20261101/primary01822/cache-followup-run-prep/campaign-spec.json` — `8a5fee2ebb8b73141ef869b31aad9d88b6ca5664667793b3d53734fb229308c3`
- `server/.local/halogen-update-20261101/primary01822/cache-followup-prep/frozen-followups-v1/manifest.json` — `0c93ee8b221031578fb138ad5defe6e89dc21b8e46e69fe47e5461ba5cdbd06c`
- `scripts/benchmarks/halogen_cache_followup/offline_sse.py` — `3a6e856c27a24c22143c844898882836dee8fcd065a66d0ed48542685b27f77a`
- `server/.local/halogen-update-20261101/primary01822/cache-followup-run-prep/collect_cache.py` — `09a2df68ee76cc9aac3be0d5b5d71957f780559fd7f5cc0e18eee10e5f83d0e6`
- `server/.local/halogen-update-20261101/primary01822/cache-followup-run-prep/cpu-readiness.json` — `0a842b395afdeb4276d6e97ac8251a56996f76376505c237dbcf56e8fe5d37c5`
- `server/.local/halogen-update-20261101/primary01822/cache-followup-prep/offline-publication.json` — `b19966af1f1937be481833679830f1236d7eaa2e515a347400f25b6e676ad27b`

Limits:

- First-content/DONE latencies are API delivery QPC clocks, not isolated GPU phases.
- Cached input represents avoided work; no full/cached-input divided by latency is reported as prefill throughput.
- Native phase rates are retained observations only for this changed workload.
- A native stop result alone does not distinguish regular completion from native cancellation; clean EOF, gateway counters and sentinels are separate evidence.
- Only complete four-pair arms contribute descriptive cohort means; each warmup pair is excluded.
- Exact output/full-input parity and candidate A/B isolation are separate qualification gates; differing valid outputs do not become a promoted speed improvement.
- Restored readiness is the root post-campaign snapshot; the publisher makes no fresh model/API/process call.
- No ServiceNow source or SDK deployment, new session headers, NPU acceleration or general kernel speedup is established.
