# Halogen 0.20.7 forced decode prefetch at 8K and 16K

Forced decode prefetch increased complete HTTP time by **9.34–9.67% at
8K** and **6.31–6.64% at 16K** relative to the two controls. Output bytes
and native MTP acceptance matched. The regular HT4 serving profile uses
decode prefetch off.

| Actual input tokens | Decode prefetch | Prefill tok/s | Decode tok/s | Native MTP accepted/drafted | Mean HTTP time (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8,192 | Off, before | 1,923.96 | 53.19 | 192/291 (65.98%) | 6.140 |
| 8,192 | On | 1,908.09 | 42.82 | 192/291 (65.98%) | 6.734 |
| 8,192 | Off, after | 1,919.15 | 53.20 | 192/291 (65.98%) | 6.158 |
| 16,384 | Off, before | 1,900.94 | 51.11 | 180/279 (64.52%) | 10.253 |
| 16,384 | On | 1,885.99 | 40.49 | 180/279 (64.52%) | 10.934 |
| 16,384 | Off, after | 1,899.06 | 51.45 | 180/279 (64.52%) | 10.285 |

Prefill and decode are arithmetic means of the native API phase rates.
The sum of the reported phase durations exceeded the independently measured
HTTP interval in all 24 responses, with a maximum excess of 1.116 s. The
Windows QPC intervals run from request dispatch to response EOF. The complete
HTTP comparison determines the latency outcome. The API rates retain their
native timing scope.

## Workload and native verification

The three windows used the same managed 0.20.7 image and v2 checkpoint, a
single 32,768-position slot, paired 8192 prefill settings, Q4 draft vocabulary,
the r2 HT4 head with its cost calibration, automatic concurrency and the
`REV:N Performance` host power scheme. The only profile difference was
`HALOGEN_DECODE_PREFETCH=0`, `1`, and `0`.

Each arm used two frozen non-repetitive novel prefixes with 8,192 and 16,384
actual input tokens. Each size contributed one excluded warmup and three
measured requests. The requests used temperature 0, seed 1, MTP, no cache
store, Thinking Off and 128 generated tokens. Every response finished at its
length cap. The exact output digest matched across all 12 responses per input
size. The lowest retained request reserve was 26.02 GiB.

The pinned 0.20.7 native binary permits sparse launch messages whenever
`HALOGEN_DECODE_PREFETCH` is set explicitly. The comparison left the general
serve trace unset. The enabled arm reported 16 blocks, a maximum of four
rows, set 15 and eight ranges for the example geometry labeled layer 4. After
startup had reached 100 enqueues, the owned engine log recorded milestones of
1,000 and 10,000. These are successful enqueue counts at sampled milestones.
Both off arms showed no prefetch startup or launch marker.

The ordinary HT4 profile was restored on port 8840 after the final arm.
Authenticated gateway and engine health passed. The ServiceNow router and
shared gateway reported ready, and the Voice check showed ASR and TTS ready.

## Reproducibility

Local raw responses, sample summaries, exact host clock pairs and lifecycle
receipts are under
`server/.local/halogen-update-20261122/primary0207/decode-prefetch-prep-v1/prefetch-campaign-run-v2`.
The separate [GPU auxiliary prefill comparison](halogen0207-dnz-prefill-20261122.md)
uses the same natural input texts and measures a different mechanism.

| Evidence | SHA-256 |
| --- | --- |
| `handle.json` | `2c627fe3645a4c7590acc9d4c5856621c3b9322cfab569c0407970c3703d8cac` |
| `before-summary.json` | `89496dfeeb6e006fd726d3cd7f4423371efa4701358b284c08c3a7f0efef0080` |
| `candidate-summary.json` | `9277862676c0fef1a5b7edc6666979c1d9b11c0da5478735b1beece558234711` |
| `after-summary.json` | `1274d446fbaaa5199bfbfb92cccb70063a03b70f50134727013fe9931a340dc5` |
| `independent-terminal-audit-v2.json` | `39ebdbad6caed1f60c004a6a906be2c2a82b18e44679034d1cf2137bb2093936` |
| `restore-stock-launch.ready.json` | `e767dd0fd6b19ccec52abd472e4894f982e51bf45c5a3eec0dd64575203571a4` |
| `post-restore-health-v2.json` | `2d7da9fb5992130f940e2ae1ff563b535068ae01190fcd1459f0a4fead19f0d7` |

| Actual input tokens | Exact output SHA-256 |
| ---: | --- |
| 8,192 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 16,384 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
