# Native original-H projection implementation — 5 October 2026

The complete original hidden projection now has a native Windows XRT/MLIR-AIE
prototype and a separate before-original-H replacement consumer. The live
consumer remains disabled. **Packed, decoded and contiguous-vector prototypes now pass their
two-input standalone real-H NPU screens at the unchanged tolerance.** These are
initial component observations; no steady-state or engine speed gain is qualified.
Read [the evidence](halogen-npu-native-hidden-implementation-20261005.json)
and [the route concept](halogen-npu-new-route-concept-20261005.md) together.

The implementation replaces only H, leaving embedding preparation/projection on
the original GPU. It computes all four 2560-element streams in one launch,
retains the DDR weight BO and context/run between calls, and has a finite
64-call device schedule. Weights and normalized inputs preserve the original
BF16 boundaries. The repaired CPU oracle matches all 20,480 frozen original-GPU
A/B words; native exact parity and complete-head qualification remain separate.

The [packed package](../../scripts/benchmarks/halogen_npu_native_hidden/README.md)
uses 6,963,200 B of losslessly rearranged Q8 weights and 7,147,520 B specified DDR
traffic/call. Its actual build succeeded without opening the NPU. All 32 linked
stack paths were reviewed: the worst CRT/core/hidden-chunk/affine path was 384 B
within its 4096-B reservation. This static proof is separate from the frozen
runtime numerical screen recorded below.

The [decoded sibling](../../scripts/benchmarks/halogen_npu_native_hidden_decoded/README.md)
decodes the original weights once during initialization. It removes 6,553,600
scalar affine conversions from a complete projection, at the cost of increasing
weight storage to 13,107,200 B and DDR traffic to 13,291,520 B/call. Three layout
tests pass, including inverse reconstruction of every synthetic BF16 word;
independent source review found no blocking layout/arithmetic/bounds/ABI issue.
This sibling has now been built separately, including its complete 32-core
lowering, actual DMA/allocation checks and device-free host metadata inspection.
Its own linked ELF audit proves a maximum full CRT/core/kernel stack path of
128 B within 4096 B on all 32 cores. The recorded enclosing and inner compiler
jobs are closed; neither compilation nor inspection opened the NPU. Preparation
decoded the unchanged, SHA-pinned 6,963,200-B original H extract once in
118.3896 ms and inversely reconstructed all 6,553,600 BF16 weight words exactly.
This one-time preparation time is not per-projection latency or XRT startup.
The sibling subsequently completed the frozen native screen below. Operation
counts and static proofs alone establish no speed advantage.

## Actual original-H frozen component screens

Root ran each distinct frozen A/B input once, with zero warmups. Both wrappers
exited 0, recorded two confirmed native calls and closed their owned jobs. Each
screen checked 20,480 output values against the original GPU oracle using the
unchanged NPU rtol=0.03 / atol=0.003; both have zero tolerance-gate mismatches.
Each has one nonidentical BF16 word on its second input, with reported maximum
absolute error 0.000488. These are tolerance passes, not bit-exact native parity.

| Initial component observation | Packed Q8 | Decoded BF16 |
| --- | ---: | ---: |
| Complete A / B calls, ms | 25.4992 / 22.8709 | 4.7757 / 2.2519 |
| Complete two-call mean, ms | 24.18505 | 3.5138 |
| XRT initialization, ms, separate | 33.7685 | 505.8045 |
| Specified DDR bytes/call | 7,147,520 | 13,291,520 |
| Weight synchronization | once | once |
| Confirmed real-H calls | 2 | 2 |

The complete interval covers input copy, output poison, synchronization,
launch/wait and output synchronization/readback. Initialization is excluded from
those call samples; the decoded preparation's 118.3896-ms exact conversion is
also a separate earlier cost. The decoded report records zero per-projection
weight-decoder calls. Its two observed call times are lower than the packed
screen, but the pronounced first/second-call spread and zero warmups prevent
steady-state qualification or a controlled causal speed claim. No matched GPU
timing, Windows/WSL live publication, full-head/output or acceptance measurement
was part of either screen. No conversion to tokens/s is justified.

[Comparison and retained receipts](halogen-npu-native-hidden-comparison-20261005.md)
link both raw native reports, wrapper results and exact hashes. Both runs kept
the already-terminal original server state unchanged. A later root-owned
restoration succeeded; its separate final-ready receipt is recorded below.

An independent source cost review found 6,553,600 scalar affine decodes per
complete packed call, followed by 1,638,400 sixteen-lane BF16 MAC calls. The
decoded source's vector construction contains 13,107,200 lane-loop iterations and
52,428,800 scalar load/set pairs in source, with weight gathering repeated for
four streams. These counts describe the source, not measured instructions or
cycle costs; compiler transformations may change them. The two real-H screens
now establish frozen output tolerance and initial complete cost, while leaving
steady-state and live replacement cost unqualified. The distinct default-off
[contiguous-vector sibling](halogen-npu-native-hidden-vector-20261005.md) now
implements a lossless lane/pair permutation for weights and a host input
transpose, preserving lane membership, ordered MACs, block adds and XOR reduction.
Its own three focused tests, fresh offline build, all 96 aligned worker buffers,
exact inverse of 6,553,600 prepared decoded words and all 32 linked stack paths
passed their gates. The hot linked chunk uses contiguous loads with no spills.
Its subsequent two frozen A/B calls passed the same .03/.003 tolerance across
20,480 values with one BF16 word mismatch (reported maxabs .000488), complete
2.9699/.3556 ms, mean 1.66275 ms including the host input transpose; initialization
525.5006 ms is separate. There were zero warmups and its owned native job closed
with exit 0. This is a third initial component screen, without a controlled
steady-state speed ratio, live consumer or engine acceleration qualification.
The [vector report](halogen-npu-native-hidden-vector-20261005.json) retains its
actual build/pack/LLVM/linked/native receipts and latest restoration status.
The [source cost decision](halogen-npu-native-hidden-vector-decision-20261005.md)
recommends keeping this consumer default-off and running no live H cohort for
the current mechanism. The original GPU result is already available to its seed
consumer on the same stream; the candidate adds HIP capture, bridge transport
and GPU upload/publication beyond its standalone component timer. Those costs
remain unmeasured at a matched useful consumer boundary.

The shared binary wire and private TCP/pipe bridge avoid packet files and
millisecond polling. The H consumer can skip the original projection after a
complete validated result; before publication, failure falls back once to the
original. Publication failure stops the candidate. Compiled bridge CPU fixtures
cover clean short sessions, remote death, unsolicited data, truncation and
stalled transfers. Actual Windows/WSL live transport, full-head correctness,
acceptance and engine throughput remain unqualified.

## Historical blocked attempts and restoration — 5 October 2026

The earlier scheduled two-input native accuracy/initial-latency screen had zero
warmups and launched no native call. The first coordinator stopped
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
job is closed. That attempt did not restore serving; the later successful
restoration below is a separate retained lifecycle.
No global WSL setting or foreign program was changed.
Current live identities/status belong to ignored
`server/.local/optimization9h-20261004/continuation-current.json`; this document
preserves the failed attempt separately from the later readiness receipt.

The separate stopped-server component coordinator has now been corrected and
independently reviewed at source SHA256
`e08750d156b7e63114c1c80ba9a27dfb180552ec5b066f370347cf536feb70d3`.
It retains suspended process ownership and recovery owners, checks runner lock,
container/listener isolation during execution and after completion, and keeps
the recovery latch until owned closure is confirmed. Host launch and confirmed
native call count are recorded separately. Syntax compilation passed; this is
not itself a hardware result. Its finite two-input, zero-warmup screen can run at the
existing 22/18-GiB standalone bounds while the original engine is already
terminal. At the earlier preparation receipt, League of Legends PID25960
prevented a clean window and no child launched. Its single 40.62-GiB physical
sample after WSL activation was below the separate 44-GiB server-start floor,
not stable startup admission. Those historical blocked receipts remain intact;
the later isolated packed and decoded runs above each completed two native calls.

## Original GPU server restored after the packed/decoded pair

The later restoration passed at **2026-10-05 21:11:36 UTC**. Its final-ready
receipt binds controller PID 21092/run `ae427fa7f0fa405c8b5dc8ec231310ab`, backend
PID 3804/run `7bfe79407b5b47aa922704d37f9b83d2` and the exact container identity.
Health is ok at context 262144, with zero active requests, completed or cancelled
requests; the persistent original service is open through port 8840 at `/v1`.
The result records errors=[], recovery_pending=false and the owned WSL hold job
closed. Restoration executed no NPU calls or benchmark and did not integrate
the candidate into the engine. Transient observer errors remain in the result
alongside the successful final identity/health check; earlier failures remain.
[Final-ready receipt](../../server/.local/optimization9h-20261004/native-hidden-held-restoration-v2-f346f01978f748b8a47457e7cda58889/final-ready.json),
[restoration result](../../server/.local/optimization9h-20261004/native-hidden-held-restoration-v2-f346f01978f748b8a47457e7cda58889/result.json).

After the later vector screen, root again restored original serving ready/idle
at **2026-10-05 21:34:46.593685 UTC**: controller PID 28392/run
`5623a5421a8442488c20b21cbb816fd6`, backend PID 23824/run
`50f336f9ba9f483e86346738c745a579`, context 262144 and gateway 8840 `/v1`.
The result has no errors, recovery_pending=false and its owned WSL job closed;
root's authenticated health/models check at 21:35:53 UTC passed on that same
identity. Exact later receipts are retained in the
[vector report](halogen-npu-native-hidden-vector-20261005.md). The earlier
restoration above remains historical evidence, rather than the current identity.

Only after adequate resident memory and a useful complete replacement cost
would a regular, bookended engine cohort
be justified. Component microseconds must not be converted into tok/s. The NPU
runtime preserves the original numerical tolerances; the server preserves all
18-GiB runtime, 22-GiB request and 44/131-GiB full-context startup constraints.
