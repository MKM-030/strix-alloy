# Native original-H projection implementation — 5 October 2026

The complete original hidden projection now has a native Windows XRT/MLIR-AIE
prototype and a separate before-original-H replacement consumer. Both remain
disabled. The packed prototype builds and its 32 linked cores pass static memory
and stack review. **No real-H NPU call or engine speed gain was measured in this
stage.** Read [the evidence](halogen-npu-native-hidden-implementation-20261005.json)
and [the route concept](halogen-npu-new-route-concept-20261005.md) together.

The implementation replaces only H, leaving embedding preparation/projection on
the original GPU. It computes all four 2560-element streams in one launch,
retains the DDR weight BO and context/run between calls, and has a finite
64-call device schedule. Weights and normalized inputs preserve the original
BF16 boundaries. The repaired CPU oracle matches all 20,480 frozen original-GPU
A/B words; native and complete-head qualification remain separate requirements.

The [packed package](../../scripts/benchmarks/halogen_npu_native_hidden/README.md)
uses 6,963,200 B of losslessly rearranged Q8 weights and 7,147,520 B specified DDR
traffic/call. Its actual build succeeded without opening the NPU. All 32 linked
stack paths were reviewed: the worst CRT/core/hidden-chunk/affine path was 384 B
within its 4096-B reservation. This is static proof, not runtime arithmetic proof.

The [decoded sibling](../../scripts/benchmarks/halogen_npu_native_hidden_decoded/README.md)
decodes the original weights once during initialization. It removes 6,553,600
scalar affine conversions from a complete projection, at the cost of increasing
weight storage to 13,107,200 B and DDR traffic to 13,291,520 B/call. Three layout
tests pass, including inverse reconstruction of every synthetic BF16 word;
independent source review found no blocking layout/arithmetic/bounds/ABI issue.
This sibling has not been built or executed. The packed build's stack evidence
does not qualify it. Operation counts alone establish no speed advantage.

The shared binary wire and private TCP/pipe bridge avoid packet files and
millisecond polling. The H consumer can skip the original projection after a
complete validated result; before publication, failure falls back once to the
original. Publication failure stops the candidate. Compiled bridge CPU fixtures
cover clean short sessions, remote death, unsolicited data, truncation and
stalled transfers. Actual Windows/WSL live transport, full-head correctness,
acceptance and engine throughput remain unqualified.

The scheduled two-input native accuracy/initial-latency screen had zero
warmups and was not a steady-state benchmark. The first coordinator stopped
the original server, but its unchanged memory-recovery threshold was initially
missed. Later independent samples passed that original threshold and explicit
44/131-GiB startup bounds; the original failure evidence was preserved. A
subsequent observer rejected a transiently reused numeric PID; the observer was
corrected to distinguish birth time from the old controller identity. The final
fresh GPU screen observed 1.091942% maximum against its existing <=1% criterion,
so no native child was launched. None of these failures is a native arithmetic
failure or a measured NPU slowdown.

The ordinary original-server restoration then exited before readiness: after
WSL activation it had 42.05 GiB physical reserve and 196.98 GiB commit headroom,
below the unchanged 44-GiB physical startup requirement. Cleanup and recovery
completed. A separate owned restoration held a harmless WSL client for its
bounded five-minute resident-memory check, so idle guest shutdown could not
conceal its working memory during admission. It did not reach the unchanged
44/131-GiB stable admission and started no new engine or benchmark. Its owned WSL
job is closed. The server remains stopped pending adequate resident reserve.
No global WSL setting or foreign program was changed.
Current live identities/status belong to ignored
`server/.local/optimization9h-20261004/continuation-current.json`; this document
does not assert that the server is ready.

Only after adequate resident memory, an isolated real-H accuracy/latency result,
and a useful complete replacement cost would a regular, bookended engine cohort
be justified. Component microseconds must not be converted into tok/s. The NPU
runtime preserves the original numerical tolerances; the server preserves all
18-GiB runtime, 22-GiB request and 44/131-GiB full-context startup constraints.
