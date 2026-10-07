# Halogen 0.16.2 native GRAM + standalone norm, CRLF 8K - 2026-10-07

The candidate remains disabled. Exact requests, greedy outputs and native acceptance match across stock-before / candidate / stock-after, but the candidate does not beat the final stock complete-request timing. The full acceleration goal remains unachieved.

## Workload and controls

Native v2, context capacity 262144; exactly 8192 actual natural prose input tokens, arena and prefill chunk both 8192. PP1 serial, TG128 serial and TG128 MTP each have one excluded warmup and three measured requests per window. All three windows completed: 36 raw / 27 measured / nine excluded warmups. Temperature 0, seed 1, Thinking Off, Cache Off, MTP2 / PLD3,3; ordinary gateway on port 8840, console tracing off for all measurement windows.

Candidate controls: GRAM=1, FUSED_NORM=0, PAIR=0, NORM_FOLD=0, DN_FUSED=1, DN_SCAN=0. This runs the existing native GPU GRAM-only DN route followed by existing standalone gated RMS normalization. It introduces no external NPU producer or host capture. Stock profiles are byte-identical; the candidate differs only in the six explicit controls. Source and image bindings are identical in all three runtime manifests, with source pins checked.

The prepared LF-normalized prompt hash is historical preparation metadata. The unchanged client actually sends raw CRLF text: SHA256 `e17340a7af7ee2cc77c747af7bad30044a474719ad52abfb2e0c8c0cd700fde3`, model `halogen-v2`. Those exact request hashes match in all windows. This is a different workload from the older LF request with 60% acceptance; neither that acceptance nor the historical 48.42 tok/s belongs to this table.

## Measured phase rates

Prefill here is the separate PP1 serial cohort; Decode and acceptance are the TG128 MTP cohort. Acceptance is accepted/drafted, reconstructed from native API counters and aggregated over the three measured requests. It is combined MTP+PLD acceptance with no per-head attribution.

| Window | Prefill tok/s | MTP Decode tok/s | Native draft acceptance |
|---|---:|---:|---:|
| before | 1238.44 | 39.00 | 201/360 = 55.83% |
| candidate | 1277.10 | 39.68 | 201/360 = 55.83% |
| after | 1299.98 | 38.99 | 201/360 = 55.83% |

These phase rates use the whole-request guest monotonic/raw ratio checked against the host clock. A constant ratio within each phase is unproven; calibrated phase times and rates remain approximations. Full independent client request walls are below. All raw and calibrated values and standard deviations are retained in the accompanying JSON.

## Actual complete-request wall times

| Window | PP1 wall seconds | TG128 MTP wall seconds | MTP wall sample stdev |
|---|---:|---:|---:|
| before | 6.642984 | 10.157060 | 0.073753 |
| candidate | 6.442179 | 10.011580 | 0.083468 |
| after | 6.329108 | 9.992579 | 0.106318 |

Candidate MTP Decode is 1.77% above the equal-weight mean of the two stock phase means, while its MTP request wall is only 0.63% lower than that bracket mean and 0.19% higher (slower) than stock-after. Stock itself improves 1.62% in complete MTP request wall between bookends. Candidate PP1 wall is 1.79% slower than stock-after. This cohort therefore does not establish a stable net serving gain; no adoption or statistical-significance claim is made. Native acceptance is unchanged. The unchanged experiment will not be repeated merely for more samples.

Complete greedy output hashes match across every mode/window for this workload. That bounds observed output parity; it does not prove exact internal recurrent states or universal model quality. No NPU production ran, and there is no measured NPU-on/off token-rate delta.

## Lifecycle and preservation

Each trial used the normal owned lifecycle; all three trial engine sessions exited 0 after cleanup/recovery and all three client sessions exited 0. The original ServiceNow profile, without experimental controls and with visible console tracing enabled, was restored and authenticated ready/idle on port 8840. Its new process and console identities are sealed in the JSON restoration receipt. The startup threshold is 35 GiB physical / 131 GiB commit at capacity262144; runtime remains 18/18 GiB. Starts with roughly 40 GiB physical admission headroom do not prove sufficiency at exactly35 GiB. Models, drivers and global WSL settings were preserved. The automation remains paused.

## Evidence

The accompanying JSON binds the unchanged client, immutable plan, exact request/output hashes, source/image/environment checks, raw files, manifests, actual process receipts and final restoration. Private raw evidence remains in `server/.local/optimization9h-20261004/next-mechanism-20261007/gramnorm-59020ee95ed9483bb0b5e55d50cab75b`.
