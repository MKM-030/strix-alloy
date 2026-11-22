# Halogen 0.20.7 Performance measurement after recovery

## Natural 8K and 16K results

The restored stock server completed all eight requests from 19:58 to 20:00 UTC
on 22 November 2026. The mean rates exclude each size's first request.

| Actual input tokens | Prefill tok/s | Decode tok/s | MTP head accepted/drafted | Whole HTTP mean (s) |
| ---: | ---: | ---: | ---: | ---: |
| 8,192 | 2,020.559 | 57.441 | 192/291 (65.98%) | 6.332 |
| 16,384 | 2,012.239 | 55.239 | 180/279 (64.52%) | 10.513 |

Every response contained 128 output tokens and finished at the requested
length. Each input size reproduced the corresponding output hash and native
head counters from the [Windows lookup controls](halogen0207-native-lookup-20261122.md).
The lowest request-sampled reserve was 25.95 GiB. The native phase sums fit
within their QPC HTTP windows in all eight requests.

| Actual input tokens | Run | Prefill tok/s | Decode tok/s | MTP head accepted/drafted | Whole HTTP (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8,192 | Excluded warmup | 1,032.583 | 48.419 | 64/97 | 10.612 |
| 8,192 | 1 | 2,038.419 | 58.047 | 64/97 | 6.245 |
| 8,192 | 2 | 1,975.976 | 56.350 | 64/97 | 6.477 |
| 8,192 | 3 | 2,047.283 | 57.926 | 64/97 | 6.275 |
| 16,384 | Excluded warmup | 1,944.942 | 49.501 | 60/93 | 11.092 |
| 16,384 | 1 | 2,016.542 | 55.730 | 60/93 | 10.489 |
| 16,384 | 2 | 2,012.702 | 55.895 | 60/93 | 10.455 |
| 16,384 | 3 | 2,007.474 | 54.091 | 60/93 | 10.595 |

## Measurement protocol

The stock cohort uses Halogen API and engine 0.20.7 on the `REV:N Performance`
profile. The v2 checkpoint runs in one 32,768-position text slot with
`prefill_chunk=8192` and `max_prefill_tokens=8192`, the r2 HT4 drafter and its
native cost rule, MTP gate 0.90, PLD `3,3`, the Windows lookup mount and decode
prefetch off.

The requests reuse the frozen, non-repetitive 8,192- and 16,384-token novel
prefixes from the [previous deployment confirmation](halogen0207-performance-natural-8k16k-20261122.md).
Each input size has one excluded warmup and three measured requests targeting
128 output tokens at temperature 0 and seed 1. The benchmark uses Cache Off
with `prompt_cache_policy=no_store`, Thinking Off and Vision Off. The collector
checks the running server before and after the cohort and uses the benchmark's
22 GiB physical and commit admission threshold. The runtime floor is 18 GiB.

Prefill and decode are arithmetic means of the native API phase rates. The
protocol leaves RAW observation disabled and phase clocks independently
unqualified. Native-head acceptance pools accepted and drafted tokens across
the three measured requests. Whole-request time uses Windows QPC from request
dispatch through response EOF. This single stock cohort establishes a serving
baseline for its collection window.

## Keep Trunk attempt and stock recovery

The planned Keep Trunk comparison ended during the initial stock stop, before
any benchmark arm launched. Docker recorded exit code `0` for the stock
container. While a TTS service came online, the old recovery check waited for
physical availability to reach its 38.175 GiB target. Its final sample was
36.424 GiB. The campaign recorded a terminal `StopObservationTimeout` with
zero completed requests. Consequently it yields no Keep Trunk speed or
acceptance result.

The separate recovery reconciled the exact stopped controller, backend and
container with the retained campaign receipt. After those owners reached a
terminal state, it archived the failed recovery lock and used the normal stock
controller on gateway port 8840. The fresh start used the profile's 30 GiB
physical and 124 GiB commit-headroom thresholds. Those startup thresholds apply
to a different operation from the old post-stop recovery check.

The earlier 503 reported port 8826. After restoration, a streamed local
Responses request through router port 8831 to gateway port 8840 returned HTTP
200, `completed`, and the expected `HALOGEN-READY` text. The stock cohort
retained controller run `36c24480fd6b4e68989c03a5531c92f9` and backend run
`8fa3a0feb6244cfbb8e77edadf207bfb`. The gateway and router remained ready after
collection.

## Reproducibility

Local recovery receipts are under
`server/.local/halogen-update-20261122/primary0207/vanished-serving-recovery-v1`.
The failed campaign handle is under
`server/.local/halogen-update-20261122/primary0207/keep-trunk-prep-v1/keep-trunk-campaign-run-v1`.
The complete stock cohort is under
`server/.local/halogen-update-20261120/primary0207/natural8192-16384-performance-after-recovery-20261122-v1`.

| Evidence | SHA-256 |
| --- | --- |
| Stock profile | `69d28caee11c0e23eb2e8dba4bc0910ffbbeef7bde9656186baa4abf7cac385d` |
| Package source manifest | `81210ca5a0391056ce1abb67d93ee05ec398f612e99ee194a434b3cea4b23a8a` |
| Frozen 8,192-token request | `2e26413988ce75fcf745a1a143aa3647297349c1516f9d18968e9d1b4da0632d` |
| Frozen 16,384-token request | `0d9cd3c7820d39ebb3c6f8ec4b712b8301e91d2eb2b97c52d9be678699ce6b3d` |
| Prior local Responses `router-smoke.json` | `f2b755e9d31889899bfc27666ee0e9f24b9a4659e3a4609c7fcb000aad94bb22` |
| Failed campaign `handle.json` | `ad19e3d1a6d14086c5bbb2be4d48b62debc73c4e39758533a13d466332d79e9c` |
| Old post-stop memory `recovery.json` | `45bcfecf9a3e81b750b796d12de677467cf098b9c86d01a4a9885a886b265c25` |
| `post-keep-trunk-stop-reconciliation.json` | `e66810ebc2a125117bf6efa55b524cdfe8cc47b4ef1ab80ad9d91264c127cac6` |
| `post-keep-trunk-restore-launch.json` | `8eca5ec2423d01f032421ed77cc9da201e83a2e863e61c6f887a290f1727e55d` |
| `post-keep-trunk-restore-launch.ready.json` | `3774ad85bfd024b931aef5e4d06d1544c4ae7a391eab3f5ba1d9f5b59a26acc8` |
| `post-keep-trunk-router-smoke.json` | `8224a17c6db42d39102659e61b88a77a8a3a4d0248af44960835ccb2c2f2511b` |
| Completed stock `handle.json` | `d22249fda374e8bebd3e02dbcb675974c844c06aecf6b40d0ffa1ab697ee74ee` |
| `summary.json` | `b6cb927d79605231d8d6cd1fad56ea59c12f2b7cedbc3d43a7eb546dd5f292e3` |
| `ready-after.json` | `7a62262d38a74631ab23830871add01244d072781261d17491cc85befafc5957` |
