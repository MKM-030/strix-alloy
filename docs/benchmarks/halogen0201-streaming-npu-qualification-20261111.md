# Real stateful NPU producer: retained-prefix qualification

The actual serial producer and its new typed FLM 1.0.12 Windows C boundary pass exact parity against the retained same-runtime sequential reference: **129 committed states × 248,070 shared BF16 values = 32,001,030 values**, zero differing words, unchanged tolerance. The 250 nonshared head rows are excluded from both sides. This extends the earlier [always-restore component](halogen0201-stateful-npu-20261111.md) to actual cached-state promotion and correction. [Numbers and evidence hashes](halogen0201-streaming-npu-qualification-20261111.json).

The actor commits each of 128 recorded target IDs once. It promotes 66 cached committed prefixes without native replay, and handles 62 corrections by restoring the exact preceding state and forwarding the true correction. Its 250 speculative forwards plus 62 correction forwards total 312. Complete rows are copied and finite-checked before the next native call; actual state ownership and cleanup remain bound to the one worker thread.

| Recorded native component window | Calls | Mean ms |
| --- | ---: | ---: |
| Forward through owned-row copy, validation and argmax | 312 | 21.1542 |
| State read | 313 | 4.5956 |
| State write | 62 | 5.4826 |

State-read windows exclude opaque `state_new` allocation and free. These are not pure NPU kernel times or engine token rates. Seed512 is 399.2741 ms; native startup is 540.8568 ms. The worker phase is 10,193.6262 ms. The 26.016-second child lifetime additionally includes offline comparison and process overhead; it is not target decode duration. API state-size estimates span 25,829,376–27,402,240 bytes, not independently measured allocations.

The finite runner deliberately fills a bounded greedy ring before each singleton authoritative feedback. It supplies no future teacher IDs to the engine. Its schedule is an offline correctness fixture, not real target pacing or evidence that READY arrives before a GPU query. The 66/128 committed next-ID agreement is offline and is not native MTP acceptance. The new CPU-tested no-restore path for an already-correct physical tail was not exercised by this full-ring run. Full-retain **state parity** is qualified; engine benefit and native acceptance remain unmeasured.

The input is the same single non-repeated8192 family used by the previous component: the NPU seeds only its tail512 and grows through640 using the excluded paired2048 warmup's 128 recorded IDs. This is not the promoted paired8192 output trajectory or a 16K result. The complete8192 prompt was reconstructed offline with an existing tokenizers0.22.2 installation, requiring exact length/tail and the original captured domain hash. That captured `db50995e…` is SHA256 of `halogen-authoritative-token-ids-v1\0` followed by little-endian IDs; the distinct raw-ID SHA is `322ad3ae…`. Older raw-hash wording was incorrect; the captured data and criterion were not changed.

The one owned child exits0. Worker thread, native context and cancellation cleanup all close; no resident NPU helper remains. Actual new wrapper/Qwen/Q4 and current System32 XRT paths and hashes match the frozen preparation. Entry22/22 and runtime18/18 GiB limits remain, with observed minima21.8192/111.4252 GiB. Both zero-GPU entry/post checks pass and the same GPU controller30100/backend41248 remain ready on8840. No GPU restart occurs during this qualification.

Independent closed audit SHA256: `17b4b4835d0fbe70f716229289e1b93c159c89578005ec5dcc9adb8d2d4da7f4`. The next step is the default-off HDO2 real-prefix handoff and a common-RAW Stock/NPU/Stock comparison. No Halogen prefill/decode increase or live NPU acceptance is claimed here; the full acceleration goal remains open.

The [published producer source](../../scripts/benchmarks/halogen_flm_streaming_producer/README.md)
retains the exact actor, native wrapper and request-scoped lifecycle. Its 51
portable CPU tests pass without a model or accelerator. The session-finalization
supplement preserves the original audit and reconstructs its earlier session
record exactly: only the final `terminal: true` and `exit_code: 0` fields were
added afterward. The qualification, comparison, monitor and ready-snapshot
hashes are unchanged. This metadata clarification changes no numerical result.
