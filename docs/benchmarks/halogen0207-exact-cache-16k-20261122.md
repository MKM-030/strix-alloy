# Halogen 0.20.7 Exact-cache smoke at 16K

The first comparison used Exact in-place cache. It stored three states and
reused zero tokens in the 32,768-position pool. The repeated prompt took
10.416 s with Exact and 10.445 and 10.455 s with Cache Off. Each time is a
single observation. All 12 requests completed and each case matched the output
hash, token counts and finish reason across the three arms.

The candidate reported native Exact mode 1, 8,192-token alignment and in-place
KV storage. For both the identical request and the changed-suffix request, the
engine asked for another 16,640-position region and evicted the region holding
the previous cache entry. Two regions require 33,280 positions, 512 more than
the pool. The shutdown report recorded 0 hits, 7 misses and 3 stores. API
responses recorded zero cached tokens without having to infer them from timing.

## Reported results

Each case had 16,384 actual input tokens and 128 output tokens. The two prompt
forms shared 16,338 leading token IDs. Status, cache ledger and MTP scope
counters were checked independently of timing. The first arm's changed-suffix
decode time was much slower than the same case in the final control. The
candidate's zero reuse and control variability preclude a cache speed claim.

| Arm | Request | Cached input tokens | API prefill tok/s | API decode tok/s | MTP head accepted/drafted | Whole HTTP (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Off before | First, no store | 0 | 1,282.455 | 46.960 | 60/93 | 15.579 |
| Off before | Seed | 0 | 2,020.247 | 56.138 | 60/93 | 10.419 |
| Off before | Identical | 0 | 2,027.196 | 54.811 | 60/93 | 10.445 |
| Off before | Changed suffix | 0 | 2,068.844 | 17.988 | 68/101 | 15.061 |
| Exact | First, no store | 0 | 1,292.389 | 45.947 | 60/93 | 15.501 |
| Exact | Seed | 0 | 2,026.093 | 54.717 | 60/93 | 10.453 |
| Exact | Identical | 0 | 2,026.970 | 55.842 | 60/93 | 10.416 |
| Exact | Changed suffix | 0 | 2,048.333 | 49.524 | 68/101 | 10.615 |
| Off after | First, no store | 0 | 1,276.003 | 46.991 | 60/93 | 15.653 |
| Off after | Seed | 0 | 2,067.930 | 55.898 | 60/93 | 10.240 |
| Off after | Identical | 0 | 2,016.939 | 55.452 | 60/93 | 10.455 |
| Off after | Changed suffix | 0 | 2,053.570 | 46.466 | 68/101 | 10.762 |

The smoke used 0.20.7 v2, r2 HT4, the native cost rule, paired 8,192-token
prefill settings, one 32,768-position slot, the Windows lookup table, temperature
0, seed 1 and Thinking Off. Every arm used the same request order. Each row is
one observation and the first request is shown separately. Phase rates are
native API observations, with RAW observation disabled. Whole HTTP uses
Windows QPC. The lowest request-sampled reserve was 24.85 GiB.

## Copied-KV smoke

The follow-up comparison enabled the documented [copied-KV mode](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/FLAGS.md#speed-levers)
at the same pool size. The candidate log reports 916 MiB each way at context
32,768. The two in-place region eviction messages were absent. The copied
mode still reported 0 hits, 7 misses and 3 stores. The API confirmed zero
reused tokens in every request. Region eviction therefore cannot explain all
the misses observed across the two campaigns.

All 12 requests completed with 16,384 input and 128 output tokens and exact
output parity per case. The identical request took 10.668 s with copied-KV,
versus 10.520 and 10.241 s in the Off controls. The changed-suffix request took
11.149 s, versus 10.765 and 10.696 s. Each row is one observation. The lowest
request-sampled reserve was 24.16 GiB.

| Arm | Request | Cached input tokens | API prefill tok/s | API decode tok/s | MTP head accepted/drafted | Whole HTTP (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Off before | First, no store | 0 | 1,342.236 | 46.921 | 60/93 | 14.974 |
| Off before | Seed | 0 | 2,069.732 | 55.580 | 60/93 | 10.247 |
| Off before | Identical | 0 | 2,000.024 | 55.589 | 60/93 | 10.520 |
| Off before | Changed suffix | 0 | 2,032.048 | 48.693 | 68/101 | 10.765 |
| Exact copied-KV | First, no store | 0 | 1,312.358 | 47.402 | 60/93 | 15.282 |
| Exact copied-KV | Seed | 0 | 1,958.192 | 55.708 | 60/93 | 10.693 |
| Exact copied-KV | Identical | 0 | 1,963.284 | 55.722 | 60/93 | 10.668 |
| Exact copied-KV | Changed suffix | 0 | 1,918.681 | 49.614 | 68/101 | 11.149 |
| Off after | First, no store | 0 | 1,327.618 | 44.579 | 60/93 | 15.294 |
| Off after | Seed | 0 | 2,030.386 | 55.337 | 60/93 | 10.407 |
| Off after | Identical | 0 | 2,068.243 | 55.795 | 60/93 | 10.241 |
| Off after | Changed suffix | 0 | 2,027.346 | 49.430 | 68/101 | 10.696 |

The copied-KV receipts are under
`server/.local/halogen-update-20261122/primary0207/exact-cache-copy-prep-v1/exact-cache-copy-run-v1`.

| Copied-KV evidence | SHA-256 |
| --- | --- |
| `before-summary.json` | `6e73d178caa943f570d98f9992645016089421e07439d4eaa2546fce610d7881` |
| `candidate-summary.json` | `dc267c0d869d0715ccbdccc7441d20dcf8d4e92850b9d254030064e855fdd73d` |
| `after-summary.json` | `602069f8ef20174f2cd621388e26f69d81b70b3e4cd88c136f16fbfd21a1246a` |
| Candidate `engine.log` | `76b03f83e34b8c75ea12e2f1910cf2262d98b881e1cd6ddf33b2daad587fafbc` |
| `handle.json` | `c1180555cc4c325603fb6936346cadff647a65556ce7782d048e69a8150b6237` |
| `restore-stock-launch.ready.json` | `d5cd4285a5acb2d2a47ab03de656fbb92664e8d1977e2758929e9418f95966da` |

The copied-KV campaign ended at 20:49:52 UTC. The restored stock controller
`247f9379332843ee9ae01ae769bc3f6e` and backend
`83978d0355be44b8b47928d416447409` passed readiness on port 8840, with Cache
Off. The local router on port 8831 confirmed that upstream was ready. The
gateway reported zero active requests at the readiness check.

## Disposition and original in-place evidence

Cache Off remains the serving default. Neither Exact mode qualified a speed
gain for these raw completion requests.

The first attempt preserved one real response and ended with a collector schema
error. The corrected collector uses the field locations confirmed in that
response and in the packaged API implementation. The 12 rows above come from
the fresh campaign after that correction.

The campaign finished on 22 November at 20:30:33 UTC. The restored stock
controller `ebe17a1f924641d48fbc8ebb64e7ad5a` and backend
`2fb74882645241f99a79fe5ad3eee42e` were ready on port 8840. A streamed
Responses request through the local router on port 8831 returned HTTP 200
and the expected `HALOGEN-READY` text after restoration.

Local receipts are under
`server/.local/halogen-update-20261122/primary0207/exact-cache-prep-v1/exact-cache-run-v2`.

| Evidence | SHA-256 |
| --- | --- |
| Package source manifest | `81210ca5a0391056ce1abb67d93ee05ec398f612e99ee194a434b3cea4b23a8a` |
| `before-summary.json` | `d2a145cd3019aec654e2e2b75f9438ffe91637fbd7b8f1b02a5d5de3042b6c0a` |
| `candidate-summary.json` | `0d4c5a0141d3213b6d45d04c8156b3899ec7a72f536ddb8705b6d9dda0fc053a` |
| `after-summary.json` | `700f32f7196a5793d916fb26e6a4966efe9678e3ddec9412485bd53fa4afac7a` |
| `candidate-launch.ready.json` | `882e01340dbd1683146e6c98ad4e8791ae13cfddb74f88381701e4e5b560410d` |
| Candidate `engine.log` | `4307d2946c96fd685887f49a62b5fcaedeb61f0e55aecfa5e0053b3e82bd4990` |
| `handle.json` | `d2e04668eb33e785e4b367647726fbe8fb459bded2cb80764d960c72ffa49c48` |
| `restore-stock-launch.ready.json` | `72db373193c10bc5e010bdfe87ecdf0f6f4c05f3c24f92530906617eee4eea25` |
| `router-smoke.json` | `1444f8b68d8de69d927016ddeabc52e62f784ef0c9cd650ce3d604c302835727` |
