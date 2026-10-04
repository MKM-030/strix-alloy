# Native GPU embedding cache: correct but slower — 5 October 2026

The bounded shared-core replay passes all 24 exact output comparisons to the
frozen original GPU outputs, including eviction and generation reset. This
cache is not selected for Halogen: hits save essentially no host time, misses
cost more, and the synthetic 50% hit schedule is slower overall.

| Measured group | Calls | Original GPU ms | Cache GPU ms | Original host ms | Cache host ms |
|---|---:|---:|---:|---:|---:|
| Ready hits | 8 | 0.183242 | 0.176677 | 0.352730 | 0.351627 |
| Misses | 8 | 0.173628 | 0.347264 | 0.360357 | 0.522051 |
| Synthetic 50% hit aggregate | 16 | 0.178435 | 0.261970 | 0.356543 | 0.436839 |

These are means from two measured eight-step cycles after one warmup cycle.
Each step runs the unchanged original M1 first, then the cache call. GPU timing
is an event bracket; host timing spans enqueue through end-event wait. Cache
capture, ordered D2D copies, publication and event queries are inside that
bracket. Setup, input/poison/output copies, reset, hashing and validation are
outside it. The hit host difference is about 0.0011 ms amid overlapping
measurement ranges; no reliable hit acceleration is established.

Synthetic keys select two frozen normalized BF16 rows. A one-row, 5,120-byte
cache forces six evictions and five resets. There are 12 misses and 12 hits
across all 24 calls, 38 exact native launches including baselines and canonical
outputs, 24 D2D copy enqueues, 18 cache readiness queries and six cache stream
drains. Native and cached outputs match frozen SHA256 values and `memcmp` on
every call. All allocations, events and the code module have successful cleanup.

This demonstrates the core's completed-hit/eviction/reset behavior on these
fixtures. It does not qualify native token gather/RMS, pending lookups, model
lifetime, full head, live hit rate, proposals or acceptance. No NPU is run here.
No prefill or decode tok/s delta follows from this component measurement.
The native shim is compile-gated off by default and was not loaded into the
colleague's engine.

Root compiled the pinned source with `-O2 -Wall -Wextra -Werror`, then executed
one bounded small replay in the pinned image. The component container had a
2-GiB memory limit, no checkpoint mount and no network. Root continuously
checked the preserved idle colleague and 18-GiB physical/commit reserve, with
22-GiB admission. Actual minimum reserve was 27.641953 GiB physical and
119.934662 GiB commit. Its own container was removed, owned Windows job closed,
and monitor stopped. The colleague's existing server remains open.

[Pinned source, compile, runtime, output, timing and closure receipts](halogen-embedding-cache-replay-20261005.json),
[source contract and live limitations](halogen-mtp-embedding-cache-contract-20261005.md),
and [NPU precision/placement decision](halogen-useful-npu-decision-20261005.md).
