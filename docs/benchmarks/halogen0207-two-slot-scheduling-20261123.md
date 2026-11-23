# Halogen 0.20.7 simultaneous requests on one engine

Sending two requests together raised completed-output throughput by
**6.68–7.54%** for the natural 8K+16K pair and **15.55–15.56%** for the
two short coding prompts. Each individual answer took longer from its own
dispatch. All responses matched the corresponding sequential output byte for byte.

| Workload | Actual input tokens | Schedule | Mean pair HTTP (s) | Pooled output tok/s over pair HTTP |
| --- | --- | --- | ---: | ---: |
| Novel excerpts | 8,192 + 16,384 | Sequential before | 16.575 | 15.445 |
| Novel excerpts | 8,192 + 16,384 | Simultaneous | **15.537** | **16.477** |
| Novel excerpts | 8,192 + 16,384 | Sequential after | 16.709 | 15.321 |
| Publisher code | 31 + 41 | Sequential before | 5.448 | 93.977 |
| Publisher code | 31 + 41 | Simultaneous | **4.714** | **108.604** |
| Publisher code | 31 + 41 | Sequential after | 5.448 | 93.986 |

Pair time uses Windows QPC from the first dispatch through the last
response EOF. The sequential client waited for the first response to
finish before dispatching the second. Both schedules used the same
two-slot profile. The natural requests each produced 128 tokens. The
publisher requests each produced 256. The aggregate rate includes
prefill, response delivery and any waiting inside the pair.

A follow-up started the short request when the long response first
became visible. On 8,192- and 1,536-token inputs, this schedule finished
both responses 8.23–8.30% earlier than sequential dispatch. The long
response had larger gaps between streamed chunks.
[Staggered arrival comparison](halogen0207-staggered-decode-20261123.md)

## Per-request measurements

The latency range in the sequential column spans the two control means.
Each native head percentage uses the accepted and proposed counters
pooled over the three measured requests. API rates retain their original
phase-clock scope. [WSL phase-clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

| Request | Sequential HTTP (s) | Simultaneous HTTP (s) | Simultaneous API prefill tok/s | Simultaneous API decode tok/s | MTP head acceptance, sequential → simultaneous |
| --- | ---: | ---: | ---: | ---: | --- |
| Novel, 8,192 | 6.232–6.236 | 15.266 | 1,778.99 | 29.34 | 192/291 (65.98%) → 198/272 (72.79%) |
| Novel, 16,384 | 10.339–10.477 | 15.442 | 1,815.24 | 23.73 | 180/279 (64.52%) → 182/283 (64.31%) |
| Code A, 31 | 2.505–2.510 | 4.388 | 253.83 | 56.49 | 624/687 (90.83%) → 557/581 (95.87%) |
| Code B, 41 | 2.938–2.944 | 4.714 | 287.98 | 51.81 | 579/708 (81.78%) → 532/604 (88.08%) |

Each of the six groups used one excluded warmup and three measured pairs.
The 48 requests used one v2/r2-HT4 engine, two native slots with a shared
32,768-position pool, paired 8192 prefill settings, cache off, vision
off and `REV:N Performance`. Every schedule used the same wire
format and output token caps. All six measured simultaneous pairs had
interleaved visible output. The native concurrency startup marker was
present. Joint verifier counters were unavailable with tracing disabled.
The lowest measured reserve was 24.72 GiB. The normal single-slot server
was restored and verified on port 8840 after collection.

## Running the measured profile

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -Slots 2 -KvPoolPositions 32768 -Concurrency 2 -PrefillTokens 8192 -ConsoleTrace
```

The shared pool fits the measured 8K+16K pair and its outputs. Two
16,384-token prompts with 128 output tokens each require a larger
pool. The two-slot profile retains the 30 GiB physical and 131 GiB
commit startup thresholds, 22 GiB request admission and 18 GiB runtime
reserve. The default single-slot profile suits latency-sensitive
requests.

## Evidence

The retained capture includes each stream line and arrival timestamp,
request dispatch and EOF QPC, decoded output bytes and per-request
native counters. The private capture directory is
`server/.local/halogen-update-20261122/primary0207/two-slot-concurrency-prep-v1/two-slot-request-scheduling-run-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Plan | `cce431971144d3312eef737efcb7cb76f1b724ea04fcbad8c250f23fb1b13cd7` |
| Pair and response summary | `f59c62a77c636cb3a87db996f85a106b7933dd6bfbcf5b24c2fba1051f87ae9a` |
| Native measurement log | `40dbe7dce942677ee3baf566a7bf40b3efc14ed72111386318828b90db82206d` |
| Completed lifecycle handle | `ba5fb2068672ad278432c01e60c001d9dcedb5b210bde0d8a54bee4a64814433` |
| Independent wire and QPC audit | `15352fa220417ee52bdd310b18d2b90cfc63e86830d76acd47bdb6e39319c5eb` |
