# Halogen 0.16.2 gather 64/32/64 probe — 2026-10-04

Changing gather threads from 64 to 32 shows no demonstrated performance gain against the warmed 64-thread bookend. The candidate is 0.43% slower on normalized three-turn time and 0.59% slower on decode; all three cells have exactly the same MTP acceptance. Keep stock compute and defaults unchanged.

This is an opt-in kernel-control probe on the sampled article client: 65,536 context capacity, 32,768 initial-token target, two repetitions of three turns per cell, in fixed 64/32/64 order. Actual initial inputs are 32,791 and 32,792 tokens. Sampling is temperature 1.0, top_p 0.95, top_k 20, seeds 20260930/20260931 by repetition, low-effort thinking, MTP drafter, and a 1,536-token output cap. All manifests retain MTP depth 2.

| Cell | Gather threads | Normalized three-turn seconds | Prefill t/s | Decode t/s | Actual six-request wall seconds | Native lookup seconds, rep 0 / 1 |
|---|---:|---:|---:|---:|---:|---:|
| gather64a | 64 | 139.386 | 766.484 | 32.226 | 240.796 | 36.6 / 10.7 |
| gather32 | 32 | 103.929 | 1085.305 | 40.504 | 177.790 | 10.4 / 9.4 |
| gather64b | 64 | 103.488 | 1087.219 | 40.742 | 176.980 | 10.4 / 9.8 |

Against the first 64-thread cell, 32 has 25.44% lower normalized time and 25.69% higher decode throughput. Against final64, 32 is 0.43% slower in normalized time, 0.18% slower in prefill, 0.59% slower in decode, and 0.46% slower in actual request wall time. The candidate normalized repetitions are 106.584/101.274 seconds; final64 is 105.933/101.044 seconds, so both paired repetitions favor warmed64 slightly.

The first64 lookup read took 36.6 seconds, followed by 10.7 seconds. 32 took 10.4/9.4 seconds; final64 took 10.4/9.8 seconds. This pattern is consistent with lookup-file cache warming and run order affecting the first comparison. It does not isolate a causal thread-count gain. The experiment restarted each engine but did not flush or measure OS file-cache residency. Initial KV/prompt-cache counters were zero in every repetition; those counters do not establish a cold lookup-file cache. All four follow-ups in each cell reused 32,768 prompt tokens.

Normalized three-turn time is the mean of two repetition sums, where each turn contributes `TTFT + 1000 / calibrated_decode_tps`. It assumes 1,000 output tokens per turn and is not actual elapsed conversation time. Decode is an output-token-weighted harmonic mean of native phase rates calibrated by each measured guest-monotonic/guest-raw ratio. Prefill is the mean of the two calibrated initial rates. Actual wall is the sum of six client request times for the recorded output lengths, excluding startup, inter-request checks, process overhead, and cleanup.

Each cell completed six requests, generated 4,623 tokens, and stopped naturally six times with zero capped or clamped outputs. Exact-value retrieval scored 14/14 in each cell. Sampled code/review outputs were ungraded. SHA-256 checks match request JSON, output JSON, content and reasoning across all three cells for each of the six repetition/turn pairs. Prompt/output token counts, request-message counts, cache counters, and proposed/accepted draft counters also match. The JSON contains hashes and numeric evidence only.

Every cell proposed 2,497 draft tokens and accepted 2,094: `0.8386063275931117` (83.8606%). There is no MTP acceptance increase. [Pinned upstream flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md#L30) document depth tuning for greedy requests; [prompt lookup documentation](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md#L79-L84) says sampled requests use the head alone. This probe held depth 2 constant and provides no sampled-depth sweep or depth-related acceptance evidence.

| Cell | Controller full-run RAM minimum GiB | Per-request RAM minimum GiB | Per-request commit headroom minimum GiB |
|---|---:|---:|---:|
| gather64a | 24.795 | 24.816 | 115.891 |
| gather32 | 25.825 | 25.851 | 117.257 |
| gather64b | 26.119 | 26.102 | 117.837 |

Controller RAM minima cover its 0.5-second monitoring interval from engine start through readiness, requests, and shutdown. Per-request minima come from 0.2-second host samples plus retained controller snapshots. The 18-GiB RAM/commit reserve held, and every group ended with stopped controller/backend, passed result, clean cleanup, and confirmed recovery. The full-run minimum commit headroom is not retained. Native startup logs say 0.0 GiB host memory remains; the separate Windows host measurements above establish the observed reserve and are not replaced by that guest startup warning.

Actual manifests confirm gather controls 64/32/64, MTP depth 2, the same immutable image, source hashes, allocation settings, and prompt-cache policy. The only manifest environment difference is `HALOGEN_NGRAM_GATHER_THREADS`. Normalized profiles differ only at the matching engine/qualification gather control. Client and corpus hashes match across all cells, and the coordinator source seals still match current files. Per-cell profile, manifest, summary, identity, log, lifecycle, and source hashes are retained in the [sanitized JSON](halogen0162-gather-20261004.json). The original native manifest bytes match the identity hash; the coordinator copy has separately pinned bytes and identical parsed content.

Two repetitions in fixed order provide no randomized estimate of run-to-run variation. Identical sampled outputs demonstrate equivalence for these 18 requests; they do not establish general sampled-distribution equivalence or coding quality. The larger baseline article and Reddit reports were not changed.

Local source artifacts are retained under `server/.local/article0162-20261003/halogen-v2-c65536-{gather64a,gather32,gather64b}` and the corresponding `halogen-v2-c65536-p32768-*` directories. Lookup log lines and all local artifact paths/hashes are listed in the JSON. These are fresh selected cells, not substitutions from older runs.

Client SHA-256: `d44d2f1a18099207f6c4df5bbc22ea0190ce0ed190035cc9722adae00529976a`.

Corpus SHA-256: `0e97b463b61bf6c8b5d9e97128bc44cf5638e30c4c97108681a3007260aaac83`.
