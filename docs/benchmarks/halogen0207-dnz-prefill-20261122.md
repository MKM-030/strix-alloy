# Halogen 0.20.7 auxiliary GPU prefill stream at 8K and 16K

The native auxiliary Z-projection stream ran on the Strix Halo GPU. With the
stream enabled, complete HTTP requests took **2.05–2.50% longer at 8K** and
**3.87–4.43% longer at 16K** than the two controls. Output bytes and native
MTP acceptance matched. The serving profile keeps the stream disabled.

| Actual input tokens | Auxiliary stream | Prefill tok/s | Decode tok/s | Native MTP accepted/drafted | Mean HTTP time (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8,192 | Off, before | 1,916.91 | 53.10 | 192/291 (65.98%) | 6.184 |
| 8,192 | On | 1,838.00 | 52.29 | 192/291 (65.98%) | 6.338 |
| 8,192 | Off, after | 1,903.49 | 53.15 | 192/291 (65.98%) | 6.211 |
| 16,384 | Off, before | 1,893.35 | 51.20 | 180/279 (64.52%) | 10.355 |
| 16,384 | On | 1,779.01 | 50.41 | 180/279 (64.52%) | 10.755 |
| 16,384 | Off, after | 1,899.91 | 51.54 | 180/279 (64.52%) | 10.299 |

Prefill and decode use the arithmetic means of the native API-reported rates.
The sum of the reported native phase durations exceeded the host HTTP interval
for all 24 responses. The largest excess among measured responses was 1.003 s.
The independent Windows QPC clock measures request dispatch through response
EOF and provides the end-to-end latency comparison. The individual API phase
rates retain their native timing scope.

## Workload and activation

One private Halogen 0.20.7 installation ran all three arms with
`HALOGEN_DN_Z_STREAM=0`, `1`, and `0`. The controls used the same package,
paths and runtime settings. The v2 checkpoint, HT4 draft head, native MTP cost
rule, PLD 3,3, 32,768-position slot, paired 8192 prefill settings and
`REV:N Performance` profile stayed fixed.

The two frozen inputs are non-repetitive novel prefixes. Each of the three
arms received one excluded warmup and three measured requests per input size.
Every request used temperature 0, seed 1, Thinking Off, Vision Off,
`prompt_cache_policy=no_store`, and 128 generated tokens. Every response
finished at the requested length. The output SHA-256 matched across all 12
responses for each input size. The lowest retained request reserve was
26.43 GiB.

The read-only native counter stayed at zero in both controls. The enabled arm
recorded **36 enqueues per 8,192-token request** and **72 per 16,384-token
request**, including the warmups. The observations bind the counter to the
exact executable, process and container before and after the HTTP timer. The
counter records successful GPU work submissions.

The three private arms ran in succession. The ordinary HT4 controller was
restored on port 8840 after the final arm. Authenticated gateway and native
checks passed, and the local ServiceNow router reported ready. The Voice
health check reported ASR and TTS ready. For an earlier serving baseline
using the same input texts, see the
[stock Performance cohort](halogen0207-performance-after-recovery-20261122.md).

## Reproducibility

Local raw responses, sample summaries, native counter snapshots, host clock
pairs and lifecycle receipts are under
`server/.local/halogen-update-20261122/primary0207/dnz-prefill-prep-v1/dnz-prefill-comparison-run-v1`.

| Evidence | SHA-256 |
| --- | --- |
| `handle.json` | `7ab89e137a4ac81c2d74b64c67e1619faef2c2eba12b7a88100eb7b5e3f91b8a` |
| `before-summary.json` | `ab663f945bf72714640f09279714db52adb7936c8a0bbf49730ddb7288f3818c` |
| `candidate-summary.json` | `7b2dde3952c9236c9b16e0c58c9a79617f802ddab09010e9ff68f81958f0eeab` |
| `after-summary.json` | `9b66144b609c2253162b044dd9b7a16694ad43d6ca17404301a899a43a7b014d` |
| `independent-terminal-audit-v1.json` | `f001a64c56f8444cdfedd0d961cad9d7bc4416d513257b1b013240ca78d06f45` |
| `restore-stock-launch.ready.json` | `74fe4f7cbfd17dc232357826235f77c43339d9bbc1765fd857323ed09159db99` |
| `post-restore-health-v1.json` | `1a5dc76855232398afd71885eab5264452d91ead19aad72aa813ac17961b0dcf` |

| Actual input tokens | Exact output SHA-256 |
| ---: | --- |
| 8,192 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 16,384 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
