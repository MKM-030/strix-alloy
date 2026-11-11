# Real NPU handoff: partial result

The NPU supplied a real prefix-bound proposal to the GPU target, with identical
128-token output. The complete Stock/NPU/Stock comparison did not finish, so
**no NPU throughput gain is qualified**. The normal server was restored on port
8840. [Captured numbers and evidence](halogen0201-real-npu-partial-20261111.json).

The completed stock arm used 8192 actual, non-repeated War and Peace input
tokens and 128 output tokens, temperature0/seed1, Cache/Thinking Off, one32K
slot and paired8192 prefill settings. One excluded warmup plus three measured
requests passed the common RAW observer and separate Windows HTTP QPC checks.
Mean prefill was **1553.90 tok/s**, decode **45.92 tok/s**, and API head
acceptance **192/312 = 61.54%**. This is one stock arm, not a causal gain study.

The NPU arm contains only its excluded warmup: 809.56 RAW prefill and 34.53 RAW
decode tok/s. These are not post-ready or repeated NPU benchmark values, and
cannot establish improvement or regression against the measured stock mean.
The cold stock warmup was also excluded. Native observation found13 READY
records, one hit in63 queries and three proposed IDs. The API reports lookup
acceptance0/3, head64/103 and combined64/106. The head ratio alone would conceal
the rejected NPU proposal; no acceptance improvement is claimed. Complete native
head-count reconstruction remains separate from these API observations.

After that request, the next entry wait never reached22/22 GiB within120seconds;
physical availability ranged18.928–21.962 GiB. No request was retried. The
helper's context closed1.470seconds after the HTTP response, so the saved
telemetry does not establish a live-context leak or identify a retaining
allocator/process. The original exit1/Win10038 shutdown-report error is kept,
despite complete reported native cleanup. A separate, default-off shutdown fix
has seven CPU regressions and independent source review.

The worker performed131 forwards and132 state reads. The next
[scalar catch-up implementation](../../scripts/benchmarks/halogen_flm_streaming_producer/catchup_v2/README.md)
avoids intermediate row copies and snapshots for already-queued true tokens,
without vectorizing the model forward or changing its weights. Its18portable
tests pass and the new C wrapper compiles. Exact native endpoint parity and
component timing are the next qualification; whole-engine benefit remains open.
