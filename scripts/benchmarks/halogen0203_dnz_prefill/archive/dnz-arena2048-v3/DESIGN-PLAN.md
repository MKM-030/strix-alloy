# DNZ paired2048 arena v3: finite GPU comparison

Goal: measure the native DN_Z_STREAM Prefill opportunity with a materially
smaller common working arena, preserving a useful complete causal comparison.
The two previous attempts never started the candidate and are closed. This
is not an unchanged retry: both max_prefill_tokens and prefill_chunk move from
8192 to2048 in every private arm. Prior engine evidence reports4.0 instead of
5.8GiB working allocation for these sizes. Current physical release remains
unproven until actual current-engine startup; no speed result is assumed.

Standing user authorization covers autonomous development and necessary normal
lifecycle stops/restarts. Root alone executes hardware. Do not request approval
again. Normal0.20.3 must be left ready/open on8840 with its original32K/8192
profile and47-source manifest. No model/driver/BIOS/voltage/globalWSL changes.

## Alternatives and selection

* Repeating the closed8K-capacity/8192-arena run on idle RAM rebound does not
  establish a changed postwarmup reserve; reject it.
* Lowering entry/runtime/startup floors is not authorized by this design;
  reject it.
* Reduce both arena controls in all private arms, leaving the exact2048+128
  request untouched and configured2048 piece above the native DNZ1280 threshold.
  Actual projection M/descriptor eligibility remain unobserved. Select this
  bounded mechanism subject to current-source feasibility review.

Private context/pool8192, implicit slots1, Prefill chunk/max2048, gate0.90,
PLD3,3, prefetch0, Cache/Thinking/VisionOff. Only DN_Z_STREAM0/1/0 differs
between before/candidate/after. Each arm has one excluded warmup and three
measurements. Request SHA remains
d7ae756957ef499de88880aba9c6c89da076cad6bcad70d120c54431c7bc071b.
One completed2K cohort is only a2K result. Do not chain an8K-input cohort.

## Implementation tasks and verification

1. Add inert private preparation/coordinator/counter-reader and CPU tests in
   this directory. Reuse exact prior source/artifact closure, current counter
   reader and RAW collector, without new compilation. No runtime on import or
   default CLI. Fresh paths only; never overwrite previous receipts.
2. Preserve private memory-budget clamp>=131GiB for v2, startup30/131,
   request entry22/22, runtime18/18. Change paired Prefill controls only to2048;
   assert native capacity8192 separately from Prefill2048. No external stream
   consumer, NPU helper or experimental embedding path.
3. Preserve normal restoration. Before its one ordinary launch, wait for
   actual30.25/131GiB stable10seconds (maximum300seconds), continuing18/18
   runtime checks. This outer margin does not change the service30/131floor.
   Handle observation timeouts as live observation, never restart triggers.
4. Save the exact frame on an admission failure, outside timed HTTP/RAW work,
   using the private reserve helper. Passing checks incur no new file write.
5. Root reviews/tests and freezes every executed dependency plus prospective
   plan, current actual identities and source/artifact hashes before one run.
   Check current games/Riot and real GPU load. No foreign program termination.
6. Collect complete RAW/QPC phase timings, actual counts, exact output/scoped
   parity, native DNZ counterdelta0/>0/0 outside HTTP, allocation and model
   identity evidence. Preserve incomplete data and recovery errors honestly.
7. Independently audit the complete result and bookend drift. No API-clock
   observation, warmup or component timing substitutes for qualified rates.
   Promote only a useful qualified result; restore exact normal baseline.

Review focus: source closure/import isolation,2048-vs8192native environment,
failed-frame capture fidelity, unchanged floors, restoration after partial
startup failure. Tests must exercise these with fake frames/lifecycles. They
must not call hardware, API, WSL, Docker or compilers.
