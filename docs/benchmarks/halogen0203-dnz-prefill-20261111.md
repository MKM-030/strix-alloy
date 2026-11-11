# Halogen 0.20.3 DNZ: two partial attempts, no qualified speed result

Neither attempt completed the planned Stock/DNZ/Stock comparison. **The DNZ
candidate never started.** No new Prefill rate, Decode rate, acceptance value
or DNZ speed difference is qualified. The single v2 Stock warmup remains
excluded; its throughput and acceptance are not published as results.

| Attempt | Actual input / output cap | Context capacity | Excluded warmups | Measured requests | Stop condition |
| --- | --- | ---: | ---: | ---: | --- |
|v1|2048 /128|32768|0|0|22-GiB entry check before any request|
|v2|2048 /128|8192|1 Stock warmup|0|22-GiB entry check before the first measurement|

Both used Prefill chunk/max8192, one slot, temperature0/seed1, gate0.90,
PLD3,3, Cache/Thinking/Vision Off and prefetch0. Startup stayed30 GiB physical
and131 GiB commit, request entry22/22 GiB and runtime18/18 GiB. The v2 private
commit clamp preserved131 GiB despite its ordinary implicit8K-capacity path.
No NPU helper or external-stream consumer was enabled.

The v1 attempt had zero counter reads and no inference. Its last saved
pre-request Windows frame showed21.954399 GiB available. v2 proved native
context/slot_ctx/pool8192 with slots1 and completed one excluded2048+128 Stock
warmup. Its Stock DNZ counter delta was0, with both reads outside HTTP QPC.
The saved post-warmup frame showed21.912460 GiB available,89.64 MiB below22 GiB.
These are adjacent retained frames, not the unsaved exact admission-failure
samples. They do not attribute memory use to the observer, driver or engine.

Native rounded startup accounting changed from0.9 to0.2 GiB of KV pool and
68.8 to68.1 GiB total; weights62.1 and working memory5.8 GiB were unchanged.
This corroborates the capacity change, not exact resident memory release,
Windows headroom recovery or a speed gain. DNZ's159.5-MiB first-use candidate
scratch was never exercised. Neither partial cohort is automatically repeated.

## Original restoration failure and separate recovery

v1 restored the exact normal47-source manifest and32K profile in its own
finally path. Independent audit verified249 execution pins and48 restored
baseline files, removal of16 private extras and the RAW artifact, and saved
authenticated normal readiness.

v2's original restoration also failed: the unchanged normal startup guard
reported29.97 GiB physical free against its30-GiB floor (a rounded service
observation). The original coordinator exited with
`phase=restoration_incomplete`, `terminal=false`, `completed=false` and
`restored=false`; its recorded restoration error remains unchanged.

A **separate later Root recovery** completed successfully. Its independently
pinned receipt establishes normal32768-context serving on8840 and an
authenticated READY functional smoke. That smoke is not a benchmark. The
composite audit verified262 execution pins,48 normal baseline files, removal
of the private sources/artifact and the warmup's saved RAW/QPC evidence.
Successful later recovery does not rewrite the original campaign as completed.

## Latest normal-server verification

At **2026-11-11 19:45:48 UTC**, Root's final saved check confirmed installed
API/engine0.20.3, one normal32768-context/pool server on8840, the original47-source
manifest and matching controller/backend identities. An authenticated API
request returned HTTP200 and `READY`. This was a functional check, not a
benchmark; it did not restart the server and left it online. DNZ remains
default off and no experimental path is promoted.

[Machine-readable result and evidence pins](halogen0203-dnz-prefill-20261111.json),
[v1 protocol](halogen0203-dnz-prefill-plan-20261111.md),
[v2 capacity protocol](halogen0203-dnz-prefill-plan-20261111-v2.md),
[archived sources, offline checks and recovery evidence](../../scripts/benchmarks/halogen0203_dnz_prefill/README.md).
