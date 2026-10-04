# Qwen3.8-Flash-Next: three-turn comparison on Windows/WSL2

Measurements completed on 3 October 2026; the final retained result is timestamped 23:53:39 Europe/Berlin (21:53:39 UTC). Eleven timing cells passed; the selected PROJFIX `cache0` cell at 262144 capacity / 131072 input failed the physical reserve and is not scored. Halogen and GUFO completed the separate coding suite; PROJFIX stopped on the physical reserve after one graded exercise and remains unscored.

GUFO has the shorter normalized conversation at 32K input. Halogen has the shorter time at 64K, 96K and 128K input among the completed results. Every completed cell retrieves all its exact values. This is a comparison of the weight/runtime combinations on this machine.

## What is being compared

The table layout and occupied-context cases follow [deepu105's Reddit comparison](https://www.reddit.com/r/LocalLLM/comments/1wu0m53/benchmarks_best_engine_for_qwen_38flashnext_on/). The reference used a Flow Z13 on Arch Linux at 70 W, different engine revisions and different weights. Here the prompts are a disclosed replacement corpus, and the coding agent loop is different. The author's scores are not copied into our tables, and cross-post percentages would not isolate an engine or OS effect.

This host is a BOSGAME BeyondMax with Ryzen AI Max+ 395 / Radeon 8060S and 128 GiB installed memory. Windows 11 Pro build 26200 reports about 64 GiB physical RAM; the retained setup has a 64 GiB graphics carve-out. The directly observed Windows graphics driver is `32.0.32015.2008`. No fixed wattage was recorded for this comparison. GUFO and PROJFIX run natively on Windows; Halogen uses Ubuntu 24.04 WSL2/Docker with the DXG bridge. All requests pass through the same local authenticated Alloy gateway, with one engine and one slot at a time.

| Engine | Weights | Runtime / settings used for these cells |
|---|---|---|
| Halogen 0.16.2 | v2 HGN core with the populated w4b lookup source | Pinned release image and WSL2 adaptation; stock compute, default MTP depth 2, no prefill/arena override, **Exact** prompt cache |
| GUFO | Unsloth UD-IQ4_XS, three GGUF shards + shared Q8_0 MTP | Qualified `7e924c2d` plus numerical patch, TheRock `10.2.0a20260930`; proposal cap 3, full draft vocabulary, length policy, prefill 2048, no prompt lookup |
| PROJFIX, selected rerun | IQ4_NL-PROJFIX, nine GGUF shards + shared Q8_0 MTP | Original pinned Windows engine with TheRock `10.2.0a20260930` runtime; MTP-host depth 1, split 1, host-pinned experts 0–17, lazy on/load-mode none, batch 2048/microbatch 512, f16 KV; **only `--cache-ram 0` added** to the original profile |

The weights, draft depths, loading policies and host platforms differ. These results cannot establish how much of a difference comes from a kernel, quantization, cache policy or Windows versus WSL. The PROJFIX rerun retains the default 32 recurrent checkpoints; disabling the saved-conversation RAM cache does not disable current-slot continuation reuse.

## Shared workload and accounting

Each cell contains two three-turn conversations: exact-value retrieval from a large code snapshot, a small implementation proposal, then tests and a review. The input uses twelve pinned public LlamaStash source files plus explicitly marked deterministic fixtures. Files and matching tokenizer are pinned in [article-corpus-manifest.json](../../scripts/benchmarks/article-corpus-manifest.json). No generated code from this timing workload is executed or graded.

For every engine, the 65536-input and 98304-input cells share one 131072-capacity engine launch, in that fixed order. The 65536- and 262144-capacity cases each get a fresh engine launch. “Cold” here means zero prompt-context reuse; model and OS caches are not flushed.

Initial targets include template tokens, with a tolerance of max(128 tokens, 1%). Follow-ups extend the history. Requests use temperature 1, top-p .95, top-k 20, min-p 0, seed `20260930 + repetition`, thinking requested with low effort and a 1536-token output limit. These are the per-request sampling and thinking settings sent to each engine. Engines may handle reasoning requests and budgets differently; reported output counts include reasoning tokens.

A subsequent [pinned-engine dispatch audit](../research/halogen-sampled-mtp-depth-20261004.md) confirms that Halogen's sampled path proposes one token per round. Its configured startup depth 2 is the greedy chain policy and does not set the proposal count for these temperature-1 requests. The measured rates and acceptance counts below are unchanged.

“3-turn time” is the average across the two conversations of the sum of `TTFT + 1000 / decode_tps` for each turn. It estimates a conversation with 1000 output tokens per answer. It is not the measured duration of the benchmark job. Prefill is the mean of the two initial requests; decode is total output tokens divided by the sum of each request's output tokens / decode rate. This is an output-token-weighted harmonic mean over all six requests. MTP acceptance is the sum of accepted draft tokens divided by the sum proposed. Missing counters would be unavailable, and zero proposals would leave acceptance undefined.

Retrieval checks exact JSON string values, including Unicode and the leading ampersand in the spinner fixture. There are seven values per run at 64K capacity and eight above it, giving denominators 14 and 16. It is a small explicit-fixture check, not a coding score or the reference author's exact retrieval task.

Windows client TTFT and actual wall intervals are independent of engine phase timers. Halogen phase rates use the recorded per-request WSL monotonic/raw-clock adjustment; raw rates and calibration ratios remain in the local evidence. This is an approximate whole-request adjustment, not proof of a constant phase clock. Ratios in the completed Halogen cells range from approximately 1.000 to 1.047. Native GUFO/PROJFIX phase timers receive no WSL correction.

## 65,536 capacity; 32,768 initial input — 50% filled

| Engine | Weights | 3-turn time | Prefill t/s | Sampled decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | v2 HGN + lookup source | 2.17 min | 1010.3 | 30.55 | 83.9% | 14/14 |
| GUFO / native Windows | UD-IQ4_XS + Q8_0 MTP | 2.01 min | 715.7 | 39.63 | 79.8% | 14/14 |
| PROJFIX / native Windows, cache0 | IQ4_NL-PROJFIX + Q8_0 MTP | 3.70 min | 241.7 | 35.51 | 85.2% | 14/14 |

## 131,072 capacity; 65,536 initial input — 50% filled

| Engine | Weights | 3-turn time | Prefill t/s | Sampled decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | v2 HGN + lookup source | 2.44 min | 1011.7 | 37.25 | 85.1% | 16/16 |
| GUFO / native Windows | UD-IQ4_XS + Q8_0 MTP | 2.94 min | 673.3 | 37.23 | 76.7% | 16/16 |
| PROJFIX / native Windows, cache0 | IQ4_NL-PROJFIX + Q8_0 MTP | 5.33 min | 287.1 | 34.13 | 83.7% | 16/16 |

## 131,072 capacity; 98,304 initial input — 75% filled

| Engine | Weights | 3-turn time | Prefill t/s | Sampled decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | v2 HGN + lookup source | 2.49 min | 1398.7 | 36.72 | 83.6% | 16/16 |
| GUFO / native Windows | UD-IQ4_XS + Q8_0 MTP | 4.04 min | 632.8 | 33.94 | 73.1% | 16/16 |
| PROJFIX / native Windows, cache0 | IQ4_NL-PROJFIX + Q8_0 MTP | 4.72 min | 507.0 | 34.54 | 85.0% | 16/16 |

## 262,144 capacity; 131,072 initial input — 50% filled

| Engine | Weights | 3-turn time | Prefill t/s | Sampled decode t/s | MTP accept | Retrieval |
|---|---|---:|---:|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | v2 HGN + lookup source | 3.25 min | 1248.2 | 33.90 | 85.0% | 16/16 |
| GUFO / native Windows | UD-IQ4_XS + Q8_0 MTP | 5.10 min | 611.1 | 32.45 | 73.1% | 16/16 |
| PROJFIX / native Windows, cache0 | IQ4_NL-PROJFIX + Q8_0 MTP | Reserve failure | — | — | — | Not scored |

This final case occupies about 128K initially in a 256K-capacity engine. It is not a 256K-input test.

## Actual counts, caps and elapsed time

The following table contains the eleven valid cells, each with six requests. Initial counts are identical across the completed engines for each geometry. The wall column is the total measured request time over both conversations, excluding engine startup/loading and shutdown.

| Engine | Capacity / input target | Actual initial counts | Generated tokens | Accepted / drafted | Length-cap / EOS | Actual request wall |
|---|---|---|---:|---:|---:|---:|
| Halogen | 65536 / 32768 | 32791, 32792 | 4623 | 2094 / 2497 | 0 / 6 | 221.54 s |
| GUFO | 65536 / 32768 | 32791, 32792 | 5557 | 3522 / 4416 | 0 / 6 | 237.52 s |
| PROJFIX, cache0 | 65536 / 32768 | 32791, 32792 | 6165 | 2833 / 3326 | 3 / 3 | 452.67 s |
| Halogen | 131072 / 65536 | 65562, 65559 | 4907 | 2232 / 2622 | 0 / 6 | 267.58 s |
| GUFO | 131072 / 65536 | 65562, 65559 | 4950 | 3183 / 4151 | 1 / 5 | 333.64 s |
| PROJFIX, cache0 | 131072 / 65536 | 65562, 65559 | 5074 | 2309 / 2760 | 1 / 5 | 617.60 s |
| Halogen | 131072 / 98304 | 98331, 98326 | 4730 | 2141 / 2561 | 0 / 6 | 273.76 s |
| GUFO | 131072 / 98304 | 98331, 98326 | 5919 | 3704 / 5068 | 0 / 6 | 494.03 s |
| PROJFIX, cache0 | 131072 / 98304 | 98331, 98326 | 4502 | 2067 / 2433 | 0 / 6 | 526.57 s |
| Halogen | 262144 / 131072 | 131099, 131099 | 5335 | 2415 / 2842 | 0 / 6 | 377.74 s |
| GUFO | 262144 / 131072 | 131099, 131099 | 5439 | 3315 / 4535 | 1 / 5 | 611.16 s |

The output limit is 1536 tokens per response. GUFO hits it once at 128K/50% and once at 256K/50%; PROJFIX hits it three times at 64K/50% and once at 128K/50%. These truncated outputs remain in the timing and token accounting. Halogen has no cap hits. No completed response reports a max-token clamp.

## Cache and memory observations

In the eleven valid cells, all 22 initial requests have zero cached input; all 44 follow-ups report positive reused-token counts. For Halogen these are 32768, 65536, 98304 and 131072 cached tokens respectively; native GUFO and PROJFIX counts include their rendered-prefix boundaries. Selecting a cache mode alone is not the evidence for these hits.

| Engine | Capacity / input target | Minimum physical headroom | Minimum commit headroom | Initial / follow-up observations |
|---|---|---:|---:|---|
| Halogen | 65536 / 32768 | 25.30 GiB | 116.27 GiB | 2 cold / 4 warm |
| GUFO | 65536 / 32768 | 37.16 GiB | 128.99 GiB | 2 cold / 4 warm |
| PROJFIX, cache0 | 65536 / 32768 | 20.29 GiB | 125.49 GiB | 2 cold / 4 warm |
| Halogen | 131072 / 65536 | 21.34 GiB | 112.34 GiB | 2 cold / 4 warm |
| GUFO | 131072 / 65536 | 31.83 GiB | 123.28 GiB | 2 cold / 4 warm |
| PROJFIX, cache0 | 131072 / 65536 | 19.38 GiB | 122.43 GiB | 2 cold / 4 warm |
| Halogen | 131072 / 98304 | 20.79 GiB | 111.68 GiB | 2 cold / 4 warm |
| GUFO | 131072 / 98304 | 29.16 GiB | 121.46 GiB | 2 cold / 4 warm |
| PROJFIX, cache0 | 131072 / 98304 | 18.21 GiB | 122.67 GiB | 2 cold / 4 warm |
| Halogen | 262144 / 131072 | 18.20 GiB | 109.55 GiB | 2 cold / 4 warm |
| GUFO | 262144 / 131072 | 23.31 GiB | 114.90 GiB | 2 cold / 4 warm |

The harness samples host physical RAM and commit headroom every 0.2 seconds, with controller snapshots before and after each call. The controller enforces the 18 GiB floor independently. These are sampled host minima, not continuous GPU-allocation measurements. The Halogen 256K/50% and PROJFIX 128K/75% cells have observed physical minima of 18.196 and 18.212 GiB, close to the configured floor. Completed groups retain terminal stopped states and cleanup evidence, including the selected PROJFIX 64K and 128K groups.

## Original PROJFIX attempts and selected replacement

The original `fresh` PROJFIX attempts are excluded from the comparison tables:

| Original capacity / input | Recorded outcome | Completed requests | Cleanup |
|---|---|---:|---|
| 65536 / 32768 | Physical reserve crossed during request 5 | 4 | Proven |
| 131072 / 65536 | Reserve failure after the first conversation; the next request did not complete | 3 | Proven |
| 131072 / 98304 | Not measured after the owning 128K group terminated | 0 | Proven for the owning group |
| 262144 / 131072 | Deliberately cancelled by the operator while diagnosing the cache behavior | 0 | Proven |

The 256K baseline is an operator cancellation, not an observed out-of-memory result. At 64K the group-level lifecycle receipt reports success even though the cell failed; the cell's `passed_execution=false` and four completed requests control whether it is scored.

Source review found `prompt_save` copies both target and draft sequence state into the saved-conversation RAM cache, whose default budget is 8192 MiB. The selected `cache0` profiles add only `--cache-ram 0`; executable/DLL/model/loading settings and the default 32 recurrent checkpoints are retained. This workload does not need to restore a discarded earlier conversation. The three valid replacement cells each finish all six requests with four warm follow-ups, including the second-conversation boundaries where the original 64K/50% and 128K/50% profiles failed. Their sampled physical minima are 20.295, 19.381 and 18.212 GiB.

The selected `cache0` 256K/50% cell crosses the physical reserve during the second conversation's initial request, request 4. Three requests completed before the failure. The cell reports `passed_execution=false`; the terminal controller is failed with a recorded physical minimum of 17.560 GiB, below the 18 GiB floor. Owned cleanup is proven. Its completed first conversation contains 2742 generated tokens, one capped answer and two EOS answers. The sanitized evidence retains those three turn receipts, but none supplies a six-request cell score. This measured reserve failure is separate from the original `fresh` operator cancellation at the same geometry. The selected profile completes the first three PROJFIX geometries on this host, while the final one fails; no further engine tuning was performed for the timing comparison.

## Separate coding pass/time comparison

| Engine | First-attempt passes | Final passes (up to two attempts) | Actual suite elapsed |
|---|---:|---:|---:|
| Halogen 0.16.2 / WSL2 | 5/10 | 7/10 | 27.59 min |
| GUFO / native Windows | 5/10 | 6/10 | 36.23 min |
| PROJFIX / native Windows, cache0 | — | Unscored reserve stop | 5.26 min (partial) |

This is a disclosed tool-agent analogue, not Pi or the author's exact selected exercises. It uses the first ten Python exercise names in lexical order from `Aider-AI/polyglot-benchmark` revision `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`, a 131072-capacity engine and a 65536-token initial input target with a 655-token tolerance. Follow-ups grow the history. The ten exercises contain 181 unique official tests. A second attempt can run a test again, so attempted test observations are reported separately from that unique total.

The runner permits two externally graded attempts, with at most four API calls per attempt, a 4096-token output cap per call and read/write tools restricted to solution files. This coding cap differs from the timing workload's 1536-token cap. Tests are pristine and hidden from initial prompts/tools; a pass requires all official tests to run, no exceptional skipped/deselected outcomes and preserved test integrity. Grading uses the pinned Docker image with its recorded isolation limits. The deadlines are 600 seconds per API call, 1200 seconds per exercise and 7200 seconds per engine suite. Suite elapsed comes from real `summary.json` and excludes engine startup. An incomplete suite will be reported as partial/infrastructure failure, not an invented 0/10.

The original PROJFIX coding `fresh` attempt aborted on its first API call with HTTP 503 after about 300 seconds (300.330 seconds of suite elapsed), before any valid recorded model call or graded attempt. Local native logs showed about 279 seconds of prefill followed by normal decode around 35 t/s; the terminal physical minimum was 19.103 GiB, above the reserve. Diagnosis found the gateway's `sock_read=300` prematurely capped transport despite its 1800-second total request budget and the runner's intended 600-second API limit. The [gateway fix](../../server/gateway.py) makes socket reads honor that existing total budget. Only PROJFIX was retried under `gatewayfix`, using the same `cache0` profile, frozen runner, dataset and 600/1200/7200-second limits. Halogen/GUFO `fresh` results remain selected. The aborted attempt is retained with cleanup proven under `prior_coding_attempts`, without a pass score.

Halogen completed all ten exercises in 1655.349 seconds: five passed on the first attempt and seven after up to two attempts. `dominoes` and `forth` passed after feedback; `book-store`, `bowling` and `dot-dsl` remained failures. All 15 graded attempts ran every expected official test with integrity preserved: 311 test observations, covering the 181 unique tests. The 31 API calls include one 4096-token cap hit. All ten initial inputs passed the geometry check at 65709–65710 tokens. Recorded API-call host minima are 19.821 GiB physical and 109.946 GiB commit headroom. The coding group is stopped with cleanup proven.

GUFO completed all ten exercises in 2173.763 seconds: five passed on the first attempt and six after up to two attempts. `food-chain` passed after feedback; `beer-song`, `bowling`, `dominoes` and `dot-dsl` remained failures. All 15 graded attempts ran every expected official test with integrity preserved: 255 test observations, covering the same 181 unique tests. The 27 API calls include three 4096-token cap hits. All ten initial inputs passed the geometry check at 65709–65710 tokens. Recorded API-call host minima are 29.278 GiB physical and 120.257 GiB commit headroom. The coding group is stopped with cleanup proven.

PROJFIX's selected `gatewayfix` suite stopped after 315.528 seconds. It graded `affine-cipher` once and passed all 16 official tests with integrity preserved. Its two recorded API calls completed, with no output caps; the initial input was 65710 tokens and passed the geometry check. Recorded draft counters are 628 accepted / 676 proposed. The owning controller then reported that Windows physical reserve crossed 18 GiB. The runner's summary records a managed-run identity error after that stop; the public result is classified as a memory reserve failure from the owning controller lifecycle. The last persisted controller minimum is 18.431 GiB and the recorded API-call physical minimum is 20.066 GiB (commit headroom 122.689 GiB). Those samples do not capture the instantaneous breach value: the controller's fresh reserve check raises before updating persisted state. Cleanup is proven. The one passed exercise is retained as partial evidence, without a suite pass count or further engine retry.

The runner and dataset pins are public in [polyglot_tool_bench.py](../../scripts/benchmarks/polyglot_tool_bench.py) and [polyglot-coding-manifest.json](../../scripts/benchmarks/polyglot-coding-manifest.json). Failed solutions are retained as measured; no tuning or additional repair runs are substituted for them.

## Relation to the previous 65 tok/s post

The [earlier long-context report](halogen0162-long-context-20261003.md) measured repeated filler with predictable numbered-paragraph output and approximately 65 tok/s. Its sampling/workload and acceptance are different. It remains separate evidence and supplies no cell in these sampled retrieval/implementation/review tables. In particular, the present 256K-capacity row starts with 128K input; it is not the earlier approximately 260K-input probe.

## Build and evidence identity

Halogen image digest: `sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a`; `flash_serve` SHA256: `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`. Existing checkpoint receipts identify the v2 core (`71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`, 66,687,678,432 bytes) and populated lookup source (`9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6`, 124,068,083,904 bytes). Their installed-file identities were checked in the upgrade; these are not newly computed full-file article-run hashes. [Release and bridge evidence](halogen0162-upgrade-20261003.md)

GUFO executable SHA256: `eaa5f85b748b9b2ab1676266d55af02e783525ae2a88ed3d00284daa6a5b036f`, source `7e924c2d787aabf640db3c0f818cb824dc18ec8e`, numerical-patch SHA256 `f7173edf67d5d834da06554fbdfd7e3df39ec5246e87047eb2335ea34d24e1fd`. Its public operator proof, all 30 test-executable hashes, SDK/source pins and four AMD DLL hashes matched during profile preparation. The generator checks selected GGUF headers; native profiles do not contain full target-weight checksums. [GUFO qualification](../integration/gufo-latest-sdk-20260930.md)

PROJFIX executable SHA256: `9653c982f7ef3e83c0498d764f33d01e793a581a0043111c36fa87c3acb89ed6`. It is the retained `pwilkin/llama.cpp@40a9f4d0` plus eight Windows patches, combined with the exact newer application-local SDK runtime; it was not recompiled for these cells. All 279 isolated runtime files matched [compatibility.json](../../backends/projfix-windows/compatibility.json); model sizes and GGUF headers passed the existing generator. Published full shard and shared-sidecar digests remain in [engine provenance](engine-provenance-20260916.md), rather than being presented as new article-run hashes.

Local raw receipts retain profile/source/manifest hashes, actual output counts and text, phase timings, calibration, cache counters, memory samples and lifecycle. Public reporting must use the sanitized renderer and exclude request/key artifacts, code/full test feedback, private paths and run IDs. Selected article tags are Halogen/GUFO `fresh`, PROJFIX `cache0`; selected coding tags are Halogen/GUFO `fresh`, PROJFIX `gatewayfix`, recorded explicitly in `selected_coding_tags`. Each coding result's actual profile is matched by hash. Earlier article and coding attempts remain separate from the selected scores.

```powershell
python -B scripts/benchmarks/render_article_report.py --work <ignored-work> --tag fresh --projfix-tag cache0 --projfix-coding-tag gatewayfix --include-prior-attempts --include-coding --format json
```

The [sanitized evidence JSON](strix-alloy-article-comparison-20261003.json) retains all selected cells, the two complete coding suites, the unscored PROJFIX coding reserve stop and cleanup, and earlier attempts in separate keys. It contains no generated code, request/key artifacts or full test feedback. No fixed-power or driver-comparison claim is made.
