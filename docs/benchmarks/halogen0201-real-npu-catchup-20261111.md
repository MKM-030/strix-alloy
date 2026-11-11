# Real NPU catch-up: incomplete engine comparison

The 11 November 2026 live comparison does **not establish a Halogen speedup**.
Stock BEFORE and the real NPU candidate each completed an excluded warmup and
three measured requests. Stock AFTER completed only its excluded warmup: the
next request reached the unchanged 120-second, 22-GiB memory-admission limit.
The campaign therefore exited **1**, with `completed=false` and `restored=true`.
The normal Halogen **0.20.1** server was restored and verified online; the NPU
path remains disabled.

[Machine-readable results, per-request values and pinned evidence](halogen0201-real-npu-catchup-20261111.json)
preserve the failed cohort and distinguish API head acceptance from native
lookup counters. These are descriptive observations, not a qualified causal
Stock/NPU/Stock result.

| Arm | Measured requests | Prefill tok/s, RAW mean | Decode tok/s, RAW mean | API all-neural head acceptance | Native lookup acceptance |
| --- | ---: | ---: | ---: | ---: | --- |
| Stock BEFORE | 3 | 1523.21 | 43.73 | 192/312 = 61.54% | 0/0, undefined |
| Real NPU helper candidate | 3 | 1429.62 | 43.10 | 192/312 = 61.54% | 0/0, undefined |
| Stock AFTER | 0 | — | — | — | — |

Means exclude warmups and average the three per-request rates without
weighting, scaling or overhead subtraction. The corresponding means of the
rounded API rates are 1523.2147/43.7283 tok/s BEFORE and
1429.6160/43.1007 tok/s for the candidate. The primary table uses the saved RAW
phase brackets; it does not infer a token rate from NPU component milliseconds.

## Frozen workload and individual requests

The request contains **8192 actual, non-repeated input tokens** and generates
128 output tokens. Context capacity is 32768, with one slot,
`prefill_chunk=max_prefill_tokens=8192`, Cache Off/no_store, temperature 0,
seed 1, thinking off, MTP gate 0.90 and PLD `3,3`. The same common RAW observer,
request and transition `815f2cd…` are retained across the three arms. Only the
candidate enables the real external producer.

RAW decode uses the established numerator of 128 output tokens. The engine
already reports one generated token at the decode boundary; the remaining
generated-count delta is 127. That convention is unchanged across arms.

| Arm | Request | Prefill tok/s, RAW | Decode tok/s, RAW | API head accepted/drafted | Native lookup accepted/drafted |
| --- | --- | ---: | ---: | ---: | --- |
| BEFORE | Warmup, excluded | 872.91 | 32.83 | 64/104 | 0/0, undefined |
| BEFORE | Measured 1 | 1372.65 | 40.83 | 64/104 | 0/0, undefined |
| BEFORE | Measured 2 | 1636.36 | 42.47 | 64/104 | 0/0, undefined |
| BEFORE | Measured 3 | 1560.63 | 47.87 | 64/104 | 0/0, undefined |
| Candidate | Warmup, excluded | 774.32 | 30.62 | 64/103 | 0/3 = 0% |
| Candidate | Measured 1 | 1258.11 | 44.66 | 64/104 | 0/0, undefined |
| Candidate | Measured 2 | 1550.99 | 44.87 | 64/104 | 0/0, undefined |
| Candidate | Measured 3 | 1479.75 | 39.77 | 64/104 | 0/0, undefined |
| AFTER | Warmup, excluded | 865.19 | 36.19 | 64/104 | 0/0, undefined |

The native chain-only subset reports 63 accepted of 103 drafted tokens in each
measured request, or 189/309 across each complete arm. Its scope is narrower
than the API all-neural head's 192/312. The retained native trace does not
independently prove the complete all-neural accepted count, so API head
acceptance is explicitly labeled. Zero measured lookup drafts make lookup
acceptance undefined; they do not establish a measured 0% acceptance rate.

## Actual NPU consumption and correctness

The excluded candidate warmup has one native consumer hit, three proposed
lookup IDs and zero accepted lookup IDs. Each of the three measured candidate
requests has **zero hits, zero proposed IDs and zero native lookup rounds**.
Their 189 combined native queries all fall back to the original MTP path.
Consequently, the measured candidate rates cannot demonstrate acceleration
from accepted NPU proposals. The faster component catch-up path is implemented
and exercised; that is separate from useful arrival before GPU demand.

All nine saved requests have the same complete 128 native target IDs, exact
output bytes and `length` finish reason. Independent file auditing reconstructs
the native-ID and text hashes, checks causal API/native request pairing and
rehashes every saved response and RAW journal. Both completed arms retain valid
RAW and HTTP-QPC bracket audits. No tolerance is relaxed.

The genuine service-v3 helper exits **0**, with all four request contexts,
worker, transport threads and native state closed. Its scoped local-shutdown
Win10038 observation is preserved; it has no fatal transport errors, guard
failure or forced termination. The actual new catch-up DLL and the unchanged
Qwen, Q4NX and System32 XRT providers were observed and pinned. Recorded
operations include 418 append-only forwards, 110 full forwards, 114 state reads
and six state writes. The helper's minimum sampled reserves are 20.6144 GiB
physical and 110.8970 GiB commit headroom.

## Failure, restoration and remaining explanation

AFTER's second request never starts inference. Its admission receipt contains
473 samples over 120 seconds, with physical availability between 21.5905 and
21.9807 GiB and no eligible 22-GiB frame. The single AFTER warmup supplies no
measured control mean. This failure is retained; no replacement cohort was
started to fill the missing observations.

A separate CPU check of the actual frozen consumer found no request-rearm
defect: five lifecycle tests pass, and all four live candidate requests have
one BEGIN, 126 authority events and no sequence failure. The initial second
prediction, ID 14367, differs from actual ID 29262; measured producer tails end
0.50–0.73 seconds after HTTP completion. The exact per-query prefix/READY
timeline is absent, so the precise cause of zero measured hits remains
unproven. This audit warrants no source fix or new cohort by itself.

The campaign restores the normal server at 11:11:48 UTC. A fresh authenticated
verification at 11:19:14 UTC confirms matching API/engine version 0.20.1,
controller 32308/backend 41560, the original paired8192 profile and all 47
normal source members. A separate 17-input/two-output-token smoke returns
`READY`; it is not a benchmark. The server remains online on port 8840 with
NPU integration disabled. A complete causal acceleration result and the full
optimization goal remain unachieved.
