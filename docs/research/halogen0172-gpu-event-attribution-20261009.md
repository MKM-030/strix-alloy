# Halogen 0.17.2 sampled GPU event brackets

The default-off observer completed one excluded warmup and one diagnostic request, retaining the original GPU kernels. Both produced exactly the same visible choices, model and usage as all four retained stock responses, including 70 accepted of 113 proposed tokens per request. This qualifies the retained diagnostic's output parity and internal record integrity; it supplies no new serving speed or optimization gain. The observer was removed through the normal lifecycle. Stock 0.17.2 was restored ready on port 8840 with its visible request-log console open.

The frozen request contains 8,192 actual synthetic input tokens and 128 normally generated story tokens, temperature 0/seed 1, Thinking Off and Cache Off. Its input includes 116 repeated calibration units; it is **not non-repetitive natural prose**. Combined API MTP+PLD acceptance is 140/226 = 61.95%, not a separately observed native-MTP-only acceptance. The diagnostic wall duration was 10.288079 seconds; its preceding warmup was 16.293643 seconds. Neither is promoted to a qualified throughput cohort.

## What was measured

The interposer forwards original launch arguments, streams and native return values. It records exact host API/function/caller/stream/grid/block/shared-memory metadata, without reading tensors or kernel argument payloads. A seeded Bernoulli 1/32 sample places timing-enabled HIP events before and after the original launch on its original stream. A collector thread queries and harvests event pairs at native-completion notifications; those notifications are harvest opportunities, not engine-idle leases. There is no added GPU synchronize.

512 reusable pairs, an 8,192-sample lifetime cap and a 32 MiB output cap bound this diagnostic. The exported snapshot contains 111,302 records: 106,122 launches, 3,316 completed timings and 1,864 counter snapshots. All 3,316 unique selected launches join exactly to their later timing records. Observed native/marker/query/elapsed statuses are zero; elapsed values are finite and nonnegative. Final pending, pool-full, retired and deferred counters are zero; 1,024 observer event handles were created and successfully destroyed. The final timing-disabled flag is the intentional idle close. Successful destruction alone does not establish immediate deferred-runtime-resource release; the diagnostic process was subsequently stopped normally.

| Request window | Recorded launches | Completed samples | Caller/geometry groups | Unsampled groups |
| --- | ---: | ---: | ---: | ---: |
| Warmup | 49,263 | 1,513 | 251 | 103 |
| Diagnostic | 49,168 | 1,571 | 261 | 115 |

7,691 launches and 232 samples outside the request windows remain outside their rankings. All recorded launches use stream 0 and the same native thread. The observer skipped 1,023 reentrant or contended calls; hidden-library, per-thread-default, graph and earlier-preload-internal work is not completely covered. Zero observed capture skips does not qualify concurrent capture-transition safety.

139 verified host registrations cover all 128 descriptors observed in the retained snapshot plus 11 relevant variants. The pinned engine SHA256 is `ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`. Grouping includes caller RVA so distinct native paths are not merged. FL's source-qualified geometry derives operation N from grid.x/400 only at its validated stock callsite. All semantic Prefill/Decode phases remain unclassified: geometry and operation N do not identify a request phase.

## Source targets and limits

| Diagnostic group | Caller RVA | Grid.x | Recorded / sampled | Mean instrumented bracket, ms |
| --- | --- | ---: | ---: | ---: |
| HC6 fused3, N=3 | `0x180e5ec` | 256 | 5,259 / 177 | 0.311877 |
| I4R GL, template 1 | `0x17d3d39` | 600 | 2,686 / 95 | 0.445447 |
| I4R FL | `0x17d3e59` | 1,200 | 2,686 / 86 | 0.338243 |
| Q4MoE mode1 GU BN128 | `0x17d119a` | 5,760 | 35 / 1 | 26.906763 |
| Q4MoE mode1 DN BN128 | `0x17d1ffa` | 11,520 | 36 / 5 | 14.795456 |

These are **instrumented original-stream brackets**, not isolated kernel execution times. NULL-stream events can add cross-stream ordering. Event work, scheduling, driver/runtime gaps, stream dependencies and sampling variation remain inseparable. The diagnostic count-times-sampled-mean ranking scores sum to 16,443.21 ms, exceeding the 10,288.08 ms request wall duration. Neither that score nor 32 times the sampled sum is actual request GPU time or a removable compute budget. In the diagnostic, 53 groups have only one timing and 27 have two; 115 have none. A single bulk-GU sample cannot establish a stable kernel cost.

Selected host spans have median 0.002571 ms, while event brackets have median 0.276589 ms. The host end timestamp precedes stop-event recording. There is no post-stop host timestamp or absolute GPU timeline, so no common marker/driver floor can be isolated or subtracted. No GPU busy percentage, phase split or expected token-rate gain follows from this receipt.

The observed successful paths preserve output and statuses, while general HIP last-error transparency on marker failure and capture-transition races remain unqualified. Keep this observer disabled for ordinary serving. Its useful result is a concrete native source identity and shape for bounded optimization hypotheses. The current HC6 source investigation targets activation/decoded-weight register live ranges while preserving arithmetic order; a lower register count or this diagnostic's ranking does not establish a speedup.

## Cleanup, retained rates and archival

The initial normal stop cleaned its processes/container but failed recovery against an eight-hour-old startup-memory baseline. Actual exited identities and container state were reconciled, and five fresh frames met the unchanged 35/131 GiB startup admission before only that run's stale lock was released. The failed recovery receipt remains failed. The diagnostic's later normal cleanup and recovery both passed. No startup-floor study, model, driver, BIOS, voltage or global WSL change occurred.

The last qualified stock 0.17.2 reference remains **1,225.98 Prefill tok/s, 43.00 Decode tok/s and 210/339 = 61.95% combined API MTP+PLD acceptance** on the retained synthetic 8K/128 workload, Thinking/Cache Off, one excluded warmup and three measured runs. It was not remeasured here. Historical 48.42 Decode tok/s belongs to 0.16.2 with 8K actual input, not 0.17.2 or 260K actual input. Normal serving defaults remain Thinking On/medium/budget 2,048; that interactive profile is not the frozen benchmark request.

[Compact machine-readable evidence](halogen0172-gpu-event-attribution-20261009.json) records hashes, counts, limitations and cleanup. Observer/analyzer source and the metadata-only descriptor map are archived under `scripts/benchmarks/experimental/halogen0172_gpu_events/`. The raw snapshot, responses, live receipts and independent reviews remain private under the preparation directory; no model weights, activations, credentials or engine binary are archived. The full acceleration goal remains unachieved and the recurring automation remains paused.
