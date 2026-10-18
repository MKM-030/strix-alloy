# Halogen 0.18.10 versus the historical 8K result — 19 October 2026

The retained historical Stock A request averaged **7.054107 s**; the current 0.18.10 historical8K cohort averaged **9.941384 s**, a **40.93% increase**. The current cohort does not reproduce the old performance. This is a measured historical gap, but its cause is not established: a similar slowdown already occurred on the same 0.16.2 engine before the upgrades, and the old/current serving configurations differ materially. No new speedup is established by this audit.

This report uses existing files and CPU calculations only. It made no HTTP, hardware, provider, lifecycle, model-payload, or authentication call. It reproduces no request text or generated content. The [JSON evidence index](halogen01810-historical-regression-20261019.json) records source hashes, selected raw timing rows, calculations, and qualifications. The separate pending measurement packet is not modified here.

## Comparable request scope and rate aggregation

Both cohorts have one excluded MTP warmup followed by three measured requests, each with 8192 reported input tokens, 128 output tokens, temperature 0, seed 1, Thinking Off, and no cache reuse. The recovered old and current message arrays are identical. The only non-message body difference is current `prompt_cache_policy: "no_store"`; the old server instead had global cache Off. The old harness also performed calibration and serial requests between MTP requests; the current cohort used consecutive MTP requests.

| Cohort | Prefill tok/s | Decode tok/s | Whole HTTP mean ± sample SD |
|---|---:|---:|---:|
| 0.16.2 Stock A, raw API arithmetic means | 1866.539000 | 48.423667 | 7.054107 ±0.006680 s |
| 0.16.2 Stock A, pooled API rates | 1866.526920 | 48.423097 | same requests |
| 0.18.10, pooled API rates | 1211.774567 | 40.870195 | 9.941384 ±0.363600 s |
| 0.18.10, API arithmetic means | 1212.636000 | 41.048333 | same requests |

Pooled rates are total tokens divided by summed reported phase seconds; arithmetic means average the response rate fields. The earlier published Stock A rates, 1866.537225/48.423621, apply its retained near-unity clock correction. Those tiny differences do not explain the gap. Pooled-to-pooled rates decline 35.08% for Prefill and 15.60% for Decode. Current phase clocks remain **independently unqualified**; whole HTTP timing uses the client’s Windows performance counter through complete response-body receipt. Nonstream first-body receipt is not TTFT.

Sources: [Stock A raw samples](../../server/.local/optimization9h-20261004/pld-stock8k-bookend-1742f9e165de45bea641446004e9733e/stocka/cold/samples.jsonl), [historical published report](../benchmarks/halogen0162-pld-stock8k-20261004.md), [current cohort summary](../../server/.local/halogen-update-20261018/primary01810/bench-results/cohort-01810-fresh/summary.json), and the raw response/client paths in the index.

The separate **1925.160 Prefill tok/s** headline is the PLD-off **serial PP8192/TG1** cohort. Its PLD-off MTP8192/TG128 cohort measured **1884.410 Prefill /48.232 Decode tok/s**. Stock A’s approximately 48.424 Decode belongs with 1866.537 Prefill in the stock PLD3,3 MTP cohort. Combining 1925.160 and 48.424 would join measurements from different cells and generation lengths. The published PLD bracket found no useful PLD-off gain.

## Descriptive phase-time bookkeeping

The table reads `prompt_ms` and `predicted_ms` directly from the retained API records and `wall_seconds` from the client receipts. No phase scaling or subtraction correction is applied.

| Cohort / measured rep | API Prefill s | API Decode s | Whole HTTP s | Whole minus API phase sum, ms |
|---|---:|---:|---:|---:|
| Stock A /1 | 4.3789 | 2.6478 | 7.047164 | 20.464 |
| Stock A /2 | 4.3833 | 2.6493 | 7.054667 | 22.067 |
| Stock A /3 | 4.4045 | 2.6330 | 7.060489 | 22.989 |
| 0.18.10 /1 | 6.5459 | 3.2409 | 9.808516 | 21.716 |
| 0.18.10 /2 | 6.9873 | 3.3058 | 10.352731 | 59.630 |
| 0.18.10 /3 | 6.7478 | 2.8489 | 9.662906 | 66.206 |

| Mean quantity | Stock A s | 0.18.10 s | Difference s |
|---|---:|---:|---:|
| API Prefill | 4.388900 | 6.760333 | +2.371433 |
| API Decode | 2.643367 | 3.131867 | +0.488500 |
| API phase sum | 7.032267 | 9.892200 | +2.859933 |
| Whole HTTP | 7.054107 | 9.941384 | +2.887277 |
| Whole minus API phase sum | 0.021840 | 0.049184 | +0.027344 |

Numerically, the API Prefill difference is 82.13% of the whole-time difference, Decode 16.92%, and the remaining difference 0.95%. These are **descriptive arithmetic shares**, not a causal decomposition. The difference between clocks/scopes is not a measured network, Python, scheduler, or gateway overhead. The current phase clocks have not been independently qualified, and close agreement of their sum with HTTP time does not qualify their individual boundaries.

Stock A accepted 207/345 drafted tokens (60%); current accepted 201/360 (55.833%). The old log records 58 rounds per request; current records 60. Output hashes also differ: old `0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6`, current `7a75932a0a22967f4f93083f03bcc263b514c49ce8fe01edf609af7b786f507b`. Thus Decode is not an identical token-trajectory comparison. The extra two rounds alone are not evidence explaining the full slowdown, and no per-round counterfactual has been measured.

## The gap already existed on 0.16.2

The [5 October gap audit](halogen-performance-gap-audit-20261005.md) compared actual image, environment, source seals, entrypoint, and startup allocation. Its first three cohorts matched those premises and retained the same prompt/output identities and 207/345 acceptance:

| Retained 0.16.2 cohort | Corrected Prefill tok/s | Corrected Decode tok/s | Whole HTTP mean s |
|---|---:|---:|---:|
| Historical Stock A | 1866.537225 | 48.423621 | 7.054107 |
| Initial keep-open measurement | 1239.198392 | 42.150412 | 9.674220 |
| Fresh same-engine control | 1229.125265 | 41.945034 | 9.751004 |
| Later serial-conditioned control | 1259.987028 | 41.625016 | 9.603823 |

The [raw initial samples](../../server/.local/optimization9h-20261004/colleague-mtp-measurement-83c7b2c6c4ef48498104fe40b2a1cbae/samples.json), [fresh control](../../server/.local/optimization9h-20261004/colleague-mtp-control-6bfeff8a087049b3b41282e5ac8b6a73/samples.json), and [conditioned control](halogen-conditioned-control-20261005.json) establish that the gap predates 0.18.x. Conditioning did not restore historical speed. This rules out treating the whole historical gap as a newly demonstrated 0.18.10 regression; it does not identify what changed in operating state.

## A newer high natural16K state also failed to return

The [15 October 0.18.5 gather bracket](../benchmarks/halogen0185-natural16k-gather-20261015.md) is a distinct natural-prose workload: 16384 input/128 output, context 32768, chunk/arena 4096, MTP 2/gate 0/PLD 3,3, Thinking Off and Cache Off. Its two gather64 control windows together measured **1852.827756 pooled Prefill /45.288894 pooled Decode tok/s** and **11.7601243 s** mean whole HTTP time. This is a newer high result, not the 0.16.2 pseudoprose reference. The gather128 candidate was slower and was not selected.

Two days later, the [0.18.7→0.18.5→0.18.7 bracket](../benchmarks/halogen0187-combined-prefill-mtp-20261017.md) measured:

|4K natural16K version arm | Whole HTTP mean s | Accepted /drafted |
|---|---:|---:|
|0.18.7 before |16.244788 |177/408 |
|0.18.5 middle |16.118757 |177/408 |
|0.18.7 after |16.403995 |177/408 |

The [saved bracket analysis](../../server/.local/halogen-update-20261017/goal-next-20261017/version-bracket-4k/analysis/results.json) confirms identical outputs and measured work within that bracket. The older 0.18.5 version did not restore its earlier approximately 11.8 s state. The published comparison also records equal GPU fatbin, GEMM plans, and six mapped libraries for the examined version comparison. This reinforces that version labels alone do not explain the historical state changes. It does not prove a particular host, power, thermal, runtime, or dispatch cause across dates. Phase clocks remain unqualified, and the separate historical runs are not a randomized simultaneous control.

## Configuration and implementation differences

| Premise | Stock A 0.16.2 | Measured 0.18.10 run `026bc316…` |
|---|---|---|
| Context / one-slot KV pool | 262144 | 32768 |
| Prefill chunk / maximum arena | no overrides; actual 32768/32768 | explicit 8192/8192 |
| Cache | global Off | Exact; request `no_store`, zero reuse/stores |
| Vision | absent | enabled, approximately 0.8 GiB tower |
| MTP / PLD | depth 2 / `3,3` | depth 2 / `3,3`, explicit gate `0` |
| Runtime reserve / SDMA | 18 GiB /`1` | 18 GiB /`1` |
| Actual weights + KV + working allocation | 62.1+7.2+12.3=81.6 GiB | 62.9+0.9+5.4=69.3 GiB |
| rocRoller | mounted compatibility library | stock image library |

See the saved [old manifest](../../server/.local/optimization9h-20261004/pld-stock8k-bookend-1742f9e165de45bea641446004e9733e/stocka/backend-manifest.json), [old engine log](../../backends/halogen-wsl2-0.16.2/.local/services/83ff523e6bae443499adff02a7177b4a/engine.log), [current manifest](../../backends/halogen-wsl2-0.18.10/.local/services/026bc316418c416980c39b817bf59108/manifest.json), and [current engine log](../../backends/halogen-wsl2-0.18.10/.local/services/026bc316418c416980c39b817bf59108/engine.log). Current thinking defaults are On/medium/2048, but the frozen request explicitly overrides thinking and reasoning effort. Profile names, preload library names, and offline mode also differ by release.

Saved complete-file main-model and n-gram receipts match across versions. The main upload range remains 66,687,358,944 bytes, with the same 64 GiB device-copy cap and 64 MiB transfer chunks; transfer chunks are separate from prefill-token chunks. No quality overlay is used, and current KV is BF16. The retained identities do not support a model/KV precision downgrade as the explanation.

Compute equivalence is not established. CPU inspection of the retained ELFs found different `.hip_fatbin` bundles: 23,677,600 bytes in 0.16.2 versus 24,965,128 in 0.18.10. Old Stock A mounted a 465,578,929-byte rocRoller compatibility library; current does not. Matching HIP/HSA provider hashes in a later October 4 record and the current CPU-provider receipt do not bind Stock A’s live engine provider closure. The finite eight-function proof covers the 0.18.8→0.18.10 demand seam, not 0.16.2→0.18.10 compute performance. Hashes and evidence limits are in the index.

The [new offline baked-plan receipt](../../server/.local/halogen-regression-20261019/baked-plan-inspection/handle.json) narrows the tuning-plan lead. The pinned 0.18.10 image’s `/opt/halogen/flash-tune.plan` is 132,980 bytes, SHA256 `e1c51d93c0ae375bdf1c853641e092a3676d9d7c8da58a51c7712b424206938a`, with 2,077 records. All 478 old shipped-plan records remain byte-identical, and 1,599 records were added. The envelope matches except its count. Under the [retained old audit key](../../server/.local/halogen-regression-20261019/baked-plan-inspection/key-comparison.json), `(bucketM,N,K,type)`, there are no duplicate keys or conflicts; each old bucket 8192/16384/32768 has 14 keys. This weakens a missing/changed-old-plan-record explanation. It does not prove 0.18.10 key selection, called kernels, provider binding, or performance equivalence. The receipt records no engine/container start and removal of its never-started owned container.

The current source accepts context 262144 and chunk/max 32768 without a new bridge or provider override. With Vision Off, its normal admission floors remain 35 GiB physical/131 GiB commit and runtime reserve18 GiB. This is source support, not a fresh host admission. Current old `runner.py`, `portable.py`, and `release.json` have drifted from stockA seals, so this audit uses its saved actual manifest/entrypoint for historical configuration.

## Tokenizer and rendering: what the CPU reconstruction establishes

Both saved full service health files identify the loaded template text with SHA256 `c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041`. The saved independent [tokenizer reference](../../server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/dflash-root-tokenizer-reference-v3-20261009/tokenizer-reference/reference.json) embeds those exact 8,952 UTF-8 bytes. StockA’s input seal binds the retained `upgrade0162/tokenizer.json` SHA256 `0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3`.

Current `tool_parse.normalize_messages` preserves this single plain user message. The matching template’s Thinking-Off branch trims that content, adds the user delimiters, then appends the assistant prefix and empty think block. The request has no added-token spellings, tools, continuation, or images. Its old/current message arrays are equal; current `reasoning_effort: "none"` removes the medium template default. Current shielding therefore has no client marker to replace in this request.

An in-memory CPU calculation, without importing the service, reconstructed 8192 IDs from this exact template branch. Rendered UTF-8 SHA256 is `09a684d240ef7bf987271a6ee16fa3403f328875163763e0eeb5a0511271cb68`; IDs serialized as unsigned 32-bit little-endian have SHA256 `a85f2ac1fe29d97549b5adc38d02233f9fd0cbbde2fbf7a9daea1909a3438c93`.

The saved reference proves that raw tokenizer JSON is not the loaded `AutoTokenizer` backend: the loader changes a Unicode pre-tokenizer regex, offset/decoder flags, and merge serialization. Applying its recorded changes reproduced loaded-backend canonical SHA256 `537fdfe1168e1c78d55cc922b74633986d27aa8aac96cdbe3529523a0963368e`; both reconstructed-loaded and raw backends yielded the same 8192 IDs for this request. CPU tokenizers was 0.23.2; the independent serving reference used tokenizers 0.22.2, transformers 5.15.0, Python 3.12.15.

This establishes a reproducible candidate sequence and eliminates that recorded backend transformation as a difference within this CPU encoding. It **does not prove actual old/new service input-ID equality**: the newer run captured counts, not input IDs, and the full runtime tokenizer/config/loader tree is not bound identically across dates. The shared read-only mount path is insufficient. The older `token-map-94d…` tokenizer/template files differ and were not used as an exact reproduction.

## Operating-state and lookup evidence limits

The exact 1866/48.42 StockA cohort has no matched frequency/power/temperature telemetry. The [conditioned-control telemetry](halogen-conditioned-control-20261005.md) covers its measured windows and records a lower observed operating range than a separate historical sensor control. That comparison is not the exact StockA reference. One-hertz sampling, unknown sensor refresh latency, and unqualified power-rail accounting prevent a power-limit, thermal, or phase-specific diagnosis. A saved performance-scheme name does not prove effective OEM power mode. Historical CPU rate/affinity is not sufficiently bound to establish a changed cap or affinity effect.

The [GPU-counter audit](halogen-gpu-counter-cohort-20261005.md) weakens large named desktop-client competition, but incomplete process identity and VM counter accounting above 100 on some paths prevent an exclusive-utilization claim. October 18’s saved inspection and matched-cohort GPU files contain empty GPU arrays; they supply no frequency/power telemetry for the 0.18.10 cohort. Memory guard success establishes the observed reserve, not comparable performance state.

Current logs record long lookup reads on excluded cold warmups: 5.5 s for historical8K and 5.7/8.3 s for natural16K. No corresponding slow-read line or exposed wait/join measurement appears for the measured warm requests. The older [0.17.2 intrusive observation](halogen0172-prefill-overlap-20261008.md) exposed 200.944 ms from wait entry to join; most of its 8.648 s worker interval already overlapped GPU work. That old observation is not a 0.18.10 ABI binding or proof of a current page-I/O bottleneck. No new page-prefetch/NPU attachment follows from these records.

## Matched 0.18.8→0.18.10 observations

The [retained sequential comparison](../../server/.local/halogen-update-20261018/primary01810/matched-lifecycle-recovered/comparison.json) has one excluded warmup plus three measurements per workload, matching output identities and acceptance across these two versions:

| Workload |0.18.8 pooled PP / Decode tok/s |0.18.10 pooled PP / Decode tok/s | Whole mean s; change |
|---|---:|---:|---:|
| Historical8K |1243.189923 /38.502802 |1211.774567 /40.870195 |9.963491→9.941384; −0.222% |
| Natural16K |1170.960411 /36.786190 |1186.423904 /36.313087 |17.570649→17.430703; −0.796% |

The phase directions are mixed and whole-time differences are small relative to the observed three-sample spread. There is no returning 0.18.8 bookend or independent phase-clock qualification. The earlier `cohort-0188-before` stopped after one warmup on the request-entry reserve and is not a measured cohort. These observations do not establish a new 0.18.10 speedup or a causal explanation for the much older historical gap.

## Pending: single 32768-chunk candidate measurement

**No candidate result is included.** The separate bounded packet is frozen at `server/.local/halogen-regression-20261019/batch32768/`. It changes only chunk and arena from8192 to32768, preserving the current32768 context, Vision, MTP2/PLD3,3 and request-level `no_store`. The sequence is8192→32768→8192; each window contains the same historical8K and natural16K requests, each with one excluded warmup and three measurements. There are24 requests in total,18 measured. The selected serving instance remains online while the specifically requested coordinated measurement window is unanswered. The packet has not run. This report neither changes it nor infers its results.

The [pinned official 0.18.10 FLAGS](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/9d11f18aa40d93ba6bc7cb65ee488b1acc834d7d/docs/FLAGS.md) identifies 32768 as its fastest measured prefill chunk and describes 8192 as about 13% lower throughput. That is evidence for a candidate, not a local gain estimate. A 16K prompt can change from two 8K calls to one; an 8K prompt offers no promised 13% gain. A larger KV pool independently consumes page-cache capacity, so historical-shape reproduction and operational chunk optimization answer different questions. Exact-cache resume granularity also changes with chunk size. Until the bounded comparison completes, performance improvement, numerical/output parity, and any operating-state explanation remain pending.
