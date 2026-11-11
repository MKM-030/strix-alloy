# FLM 1.0.12 unused-head append experiment

This source archive prepares a new default-off NPU component. It removes the
unused output-head computation only while appending already-authoritative
intermediate token IDs. It does not change the normal Halogen server, model
weights or installed provider DLLs on disk. No engine speed or acceptance gain
is established by a build or CPU test.

The independent source review identifies a separate head command whose DDR
inputs are hidden state and head weights and whose only DDR output is logits.
The candidate suppresses only its exact start/wait calls in the one private
child process, scoped to a single intermediate append. Layer completion, both
buffer synchronization calls, context updates and row-producing forwards remain.
The original instruction bytes, RX protection and instruction cache are restored
before returning; a restoration failure is terminal. One-engine and thread
ownership checks prevent nested or concurrent use. Python checks the actual
loaded provider's path and complete file hash before enabling the mode; the
bridge independently checks mapped PE identity and instruction bytes.

Files retain the exact private preparation bytes listed in
[`source-manifest.json`](source-manifest.json). The orchestration paths expect
materialization under
`server/.local/halogen-update-20261110/primary0201/stateful1012-core-append-v1/producer`;
they are a Root-bound experiment, not a general installation command. Model,
SDK, compiled DLL, private credentials and raw native outputs are not bundled.
The accelerator-free C++ fixture tests the guard independently of FLM. The
Python tests use fake native state and check the qualifier, failure handling,
module admission and retained-child cleanup. Native execution requires a
separately compiled bridge and explicit frozen preparation/identity pins.

The finite native design compares eight alternating queued16 replays: one
excluded warmup and three measured 128-commit runs per mode, with exact seed512
and nine complete BF16 endpoints per run. One separate unmeasured mixed-batch
replay checks groups `(1,2,3,4,6)` within each 16-token span. All 81 endpoint rows
must equal the original sequential reference exactly; the nine correctness-only
rows never enter either timing mean. Original tolerances and 22-GiB entry /
18-GiB runtime reserves remain. Component milliseconds are not measured Halogen
prefill/decode tok/s or MTP acceptance.

See the [implementation plan](../../../../docs/superpowers/plans/2026-11-11-npu-unused-head.md).

The [completed native component](../../../../docs/benchmarks/halogen0201-core-append-component-20261111.md)
passes all 81 endpoint rows exactly and reduces mean queued catch-up work from
2602.95 to 1626.48 ms (37.51%). All 568 head skips restore the original calls;
the single native child exits cleanly and the GPU server stays unchanged.
This does not establish a Halogen tok/s or acceptance improvement. The live
producer integration requires its own reviewed source closure and full comparison.
