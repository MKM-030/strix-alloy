# Halogen 0.20.7 Exact-cache smoke at 16K

Exact cache stored three states and reused zero tokens in the 32,768-position
pool. The repeated prompt took 10.416 s with Exact and 10.445 and 10.455 s with
Cache Off. Those are single requests. All 12 requests completed and each case
matched the output hash, token counts and finish reason across the three arms.

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

## Disposition and evidence

Cache Off remains the serving default. The next controlled cache candidate
uses the documented [copied-KV mode](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/FLAGS.md#speed-levers)
at the same pool size. It can preserve a saved copy after the serving region
is reassigned. Its cache hits, transfer overhead and output parity require
runtime verification.

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
