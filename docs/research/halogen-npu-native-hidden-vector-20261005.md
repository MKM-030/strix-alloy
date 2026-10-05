# Native hidden projection: contiguous vector implementation and evidence

5 October 2026. **The distinct default-off vector sibling passed its offline
gates and two-input native accuracy screen at the unchanged tolerance.** Root recorded
three focused synthetic layout tests, a successful owned offline build, exact
inverse reconstruction of every prepared decoded weight word, 64-byte alignment
of all 96 worker input/weight buffers, and a complete static stack audit of all
32 linked cores. Its **two actual vector NPU calls** observed complete costs of
2.9699/0.3556 ms including the host input transpose, mean 1.66275 ms. These are
initial observations with zero warmups; exact parity and steady-state cost are
unqualified. Root restored the original server ready/idle at 21:34:46 UTC.

The [machine-readable report](halogen-npu-native-hidden-vector-20261005.json)
preserves exact parsed receipt objects, original UTC date strings, paths and file
SHA256 hashes. Its preparation snapshot records receipt-backed state, not a
live server query. This author performed source/receipt reads and wrote only
assigned research documentation: no compiler, tests, hardware, SDK device queries, installs,
lifecycle changes, continuation changes, original-weight reads or commits.

## Implemented mechanism and arithmetic

The separate
[source package](../../scripts/benchmarks/halogen_npu_native_hidden_vector/README.md)
implements the [reviewed plan](halogen-npu-native-hidden-vector-plan-20261005.md).
The external protocol remains canonical `[4,2560]` BF16 input and output for the
original H store7/variant0 projection. Design, build, artifact and weight sidecars
use distinct vector format tags and bind both internal layouts plus 64-byte
alignment, so same-sized older payloads or artifacts fail the new host's checks.
No controller/profile/engine route enables this sibling by default.

Outer streamed weight order remains `[column8,group5,Kchunk10,worker4]`. Each
8192-byte chunk uses `[row16,pair8,component2,lane16]`:

```text
Wp[row,pair,component,lane] = W[row,lane*16 + pair*2 + component]
Xp[stream,kchunk,pair,component,lane]
  = Xcanonical[stream,kchunk*256 + lane*16 + pair*2 + component]
```

The host permutes 10,240 BF16 words directly into the existing input BO once per
call, using canonical bytes for request digest binding. It performs no float
conversion or second affine weight decode. The complete component timer starts
before the input transpose and includes poison/copy, input sync, launch/wait,
output sync and readback. Device launch/wait remains a separate interval; neither
interval measures consumer publication or all readiness/transport costs.

One contiguous 32-word weight vector supplies its two sixteen-lane halves to four
independent stream accumulators. Each stream retains the ordered first and second
MAC for every pair; each row starts four zeroed accumulators, with eight pairs per
K256 chunk and ten separate FP32 chunk additions. Reset, XOR8/4/2/1 finish and
BF16 RNE conversion remain unchanged. The existing numeric reference's SHA is
`73cf7859aa8fceafb7ad34b85f95be70e65b0cd1da8d4dd90239f3a2d71562ba`.
The GPU dot2 instruction's internal rounding remains unresolved; source and
lowering preservation do not establish exact native/GPU parity.

## Actual packing, build and placement

Root's [offline plan](../../server/.local/optimization9h-20261004/native-hidden-vector-offline-build-plan-20261005.json)
records the three passed focused tests: full inverse/source reconstruction,
independent weight coordinates/alignment, and exhaustive canonical input word
permutation including signed zero. These tests were not rerun for this report.

The actual build is
[`native-hidden-build-c5d5e236a4ec42fca3904202fa4e8565`](../../server/.local/optimization9h-20261004/native-hidden-build-c5d5e236a4ec42fca3904202fa4e8565/owned-result.json).
It exited 0, passed with `errors=[]`, closed its owned job and reports
`NPU_executed=false`, `server_changed=false`. Its
[outer wrapper](../../server/.local/optimization9h-20261004/native-hidden-vector-outer-3278c4efaae84c5e8dcd3a658419c7f3/result.json)
also passed with no errors and its owned job closed. The
[build receipt](../../server/.local/optimization9h-20261004/native-hidden-build-c5d5e236a4ec42fca3904202fa4e8565/artifacts/build-receipt.json)
reports `device_opened=false`, `runtime_executed=false`, with UTC build interval
`2026-10-05T21:18:43.0601331Z`–`2026-10-05T21:18:57.7205811Z`.

The [pack receipt](../../server/.local/optimization9h-20261004/native-hidden-vector-packed-20261005/pack-receipt.json)
reports a word-only permutation from the already pinned decoded payload; no
original Q8 file or affine conversion was used. All **6,553,600 decoded words**
inverse-reconstruct bit for bit. Both original decoded and inverse SHA are
`6c324951fa67bf51b66e3911f1dc31560f05a18f5143312714c47f7d38acb008`.
The new packed SHA is
`deb8c1e82b3eb90081ab4329e92397422c27e77ba5b567f700b132a97ba461ff`.
This equality concerns decoded BF16 words; it does not reconstruct discarded
original Q8 information. Total offline preparation was 54.2873 ms.

The [emission receipt](../../server/.local/optimization9h-20261004/native-hidden-build-c5d5e236a4ec42fca3904202fa4e8565/artifacts/emission-receipt.json)
passes source/physical DMA, lowered patches/sync counts, allocation, declared
stack and vector alignment checks. All 96 actual worker input/weight buffers
align to 64 bytes. Each worker's input starts at 4096 and two weights at
24576/32768; its partials start at 40960, outputs at 45056/45184, and a generated
12-byte metadata allocation starts at 45312. The source's nominal 45,312-byte
worker budget excludes that generated metadata; actual map entries are retained.
The compiler emitted 32 bank-aware allocation fallback warnings before basic
sequential allocation. The successful actual map establishes placement and
alignment, without establishing optimal bank scheduling or cycle cost.

Weight/input/output BOs remain 13,107,200/20,480/20,480 bytes. Chunk/aggregate
extents remain 8192/32768 bytes, partials 4096 bytes, declared stack 4096 bytes.
The emitted per-call DDR count remains **13,291,520 bytes**: 13,107,200 weights,
163,840 input fan-out and 20,480 output. Host input permutation adds host work
inside the complete timer; it does not reduce those emitted DMA bytes.

## Actual static lowering and all-core stack review

The independent source/LLVM/linked review examined the actual
[`kernels.ll`](../../server/.local/optimization9h-20261004/native-hidden-build-c5d5e236a4ec42fca3904202fa4e8565/artifacts/kernels.ll)
and retained disassembly. Per pair, LLVM contains one aligned 64-byte weight load
and four aligned 64-byte input loads, eight ordered MAC intrinsics in four
independent chains (configuration 828), then four separate FP32 partial adds
(configuration 60). Those configurations match the decoded baseline. Reset and
finish LLVM bodies match that baseline after metadata renumbering.

All 32 linked `hidden_chunk` instruction streams are identical: 95 bundles,
624 bytes at address `0x700`, with no scalar hot-chunk loads/stores, SP accesses,
calls or spills, and four final `vadd.f` instructions. Canonical instruction-text
SHA is `f2b22c06e34e45f9cdcc356f60abbadbc9ad19da2a1f97c9f50ba4db4a50f8ca`.
This is the independent review's static instruction evidence, not a cycle count.

The [linked stack audit](../../server/.local/optimization9h-20261004/native-hidden-vector-linked-stack-review-20261005/linked-stack-review.json)
reports `verified-static` for all 32 actual ELF paths. Each core call path is
bounded at 64 bytes; each complete CRT/startup path is conservatively bounded at
128 bytes, within the actual 4096-byte reservation (3968-byte margin). It accounts
for the core and `_main_init` frames, enumerated direct calls, SP aliases and
linked access widths. Absence of hot-chunk spills does not imply the outer
core/startup has no stack use. All paths retain zero audit errors.

## Actual frozen native screen and prior context

The vector [component plan](../../server/.local/optimization9h-20261004/native-hidden-vector-component-plan-20261005.json)
bound two distinct frozen original-H A/B calls, zero warmups, unchanged
NPU rtol 0.03 / atol 0.003 and a complete interval including the host transpose.
The actual [native report](../../server/.local/optimization9h-20261004/native-hidden-vector-stopped-component-2dbd6aa0ac934e52ab923c794c607256/native-result.json)
passes that tolerance gate across all 20,480 values. Input A has no exact BF16
word mismatch; input B has one, with reported maxabs 0.000488. This is a bounded
frozen tolerance pass, not bit-exact native/GPU parity or general correctness.

| Initial component observation | Call A | Call B |
| --- | ---: | ---: |
| Complete, including host input transpose | 2.9699 ms | 0.3556 ms |
| Device launch/wait | 2.9620 ms | 0.3485 ms |
| Exact BF16 word mismatches | 0 | 1 |
| Tolerance-gate mismatches | 0 | 0 |

Complete mean is **1.66275 ms**; XRT initialization was **525.5006 ms**, separately
excluded from these samples. The report confirms once-only weight sync, zero
per-projection weight-decoder calls and unchanged 13,291,520 DDR bytes/call.
The difference between complete and launch/wait includes multiple host/sync
costs; it is not an isolated transpose measurement. The
[owned wrapper](../../server/.local/optimization9h-20261004/native-hidden-vector-stopped-component-2dbd6aa0ac934e52ab923c794c607256/result.json)
passes with `errors=[]`, native PID 23400 exited 0 and its owned job closed.
[Scope](../../server/.local/optimization9h-20261004/native-hidden-vector-stopped-component-2dbd6aa0ac934e52ab923c794c607256/scope.json)
retains the frozen cohort bindings and already-terminal original controller and
backend identities. Native completion does not establish restored serving.

The earlier [decoded screen](halogen-npu-native-hidden-comparison-20261005.md)
observed complete calls of 4.7757/2.2519 ms, mean **3.5138 ms**, with zero warmups
in a separate session. It passed the unchanged tolerance gate across 20,480
values with one BF16 word mismatch and reported maxabs 0.000488. It is useful
initial context, not a steady-state baseline or a vector speed ratio.

No steady-state cohort, matched original readiness-to-consumer/GPU comparison,
live consumer replacement, full-head correctness or acceptance qualification is
established by these component receipts. No token throughput or engine gain is
inferred. The distinct sibling remains default-off.

The [source cost decision](halogen-npu-native-hidden-vector-decision-20261005.md)
recommends no live H cohort for this implementation. The original H executes
asynchronously on already-resident GPU input and publishes to the seed consumer
on the same stream. Its earlier 158.707124-us device-only mean excludes copies;
the vector's second 355.6-us complete sample excludes required HIP capture,
Windows bridge and GPU publication. These cohorts/scopes are unmatched, so no
controlled ratio is inferred. A real NPU consumer would add synchronization,
D2H capture and a bridge round trip, then H2D upload and publication sync.
There is no measured readiness-to-GPU-visibility result or plausible gain case
for the current synchronous replacement. Further live work requires a changed
mechanism; the engine gain goal remains unmet.

## Original GPU server restored after the vector screen

Root's [final-ready receipt](../../server/.local/optimization9h-20261004/native-hidden-vector-held-restoration-e7f8e9446e8a4248994c6a89f0a12b66/final-ready.json)
passed at **2026-10-05 21:34:46.593685 UTC**. It binds controller PID 28392,
birth time `134357094846453519`, run `5623a5421a8442488c20b21cbb816fd6`, backend
PID 23824/run `50f336f9ba9f483e86346738c745a579`, and container
`4abbc1dc44b126871d3d226727a82c2b0952fee81da107d9369d94e6aefe8793`.
Health is ok with zero active requests, context 262144, and original serving
through port 8840 at `/v1`.

The [restoration result](../../server/.local/optimization9h-20261004/native-hidden-vector-held-restoration-e7f8e9446e8a4248994c6a89f0a12b66/result.json)
passes with `errors=[]`, `observation_errors=[]`, `original_ready_open=true`,
`recovery_pending=false` and the owned WSL hold job closed. Root reports session
exit 0. No NPU calls or benchmark ran during restoration. A later
[authenticated check](../../server/.local/optimization9h-20261004/native-hidden-vector-held-restoration-e7f8e9446e8a4248994c6a89f0a12b66/post-restoration-authenticated-check.json)
at **21:35:53.139080 UTC** binds the same identity, records health ok/idle,
models HTTP 200 and all owned helpers terminal. These establish readiness at
their recorded checks; candidate integration and acceleration remain disabled.
Startup floors of 44 GiB physical / 131 GiB commit and 18 GiB live reserves are
unchanged. Earlier packed/decoded restoration and failed attempts remain intact
in their historical reports.
