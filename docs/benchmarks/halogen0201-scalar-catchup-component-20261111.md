# Scalar NPU catch-up: exact endpoints and lower component cost

The real FLM 1.0.12 NPU replay completes with **72 exact endpoint comparisons,
17,861,040 BF16 values and unchanged tolerance**. One native engine executes
eight alternating runs: an excluded warmup and three measurements per mode.
Each run starts from the same 512-token tail and commits the same 128 recorded
target IDs. This is an isolated component replay; these IDs never feed a live
Halogen proposal stream.

| Component mode | Mean commit time, ms | Measured repetitions |
| --- | ---: | ---: |
| Singleton authoritative updates | 3431.4798 | 3 |
| Already-queued groups of 16 | 2594.9090 | 3 |

The mean drops by **836.5708 ms, or 24.3793%**. Windows QPC surrounds the
commit work. Seed/reset, endpoint capture, comparison and disk writes are
outside that interval. Model forwards remain scalar and ordered. At the same
128-token trajectory, grouped processing uses 120 append-only calls, eight
row-producing forwards and nine snapshots, rather than 128 row-producing
forwards and 129 snapshots, including the initial seed snapshot.

The exact checks cover G0,16,32,...128 for each run; intermediate head rows
are not all observed. Both modes match the retained same-runtime reference
at every declared endpoint, including greedy IDs and owned-row hashes. No
approximation or numerical tolerance was introduced.

The owned child exits 0 and all native resources close. The same GPU server
remains online. The four selected loaded DLL paths/hashes were observed;
one Windows Win299 module-enumeration error is retained in the evidence rather
than discarded. No native test was repeated to remove it.

These are component milliseconds, **not measured Halogen prefill/decode tok/s
or MTP acceptance**. Actual queue depth, timely proposals, memory admission
and whole-engine benefit remain for the new controlled live comparison.
[Numeric evidence and independent audit](halogen0201-scalar-catchup-component-20261111.json).
