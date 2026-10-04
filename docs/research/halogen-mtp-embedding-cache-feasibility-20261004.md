# Embedding-projection cache feasibility — 4 October 2026

A bounded GPU resident cache of the count1 embedding projection is feasible
from the retained native dataflow. A ready hit could avoid the original M1 FC
without waiting for Windows or the NPU. This is a source-only design: no cache
implementation, model/payload read, hardware execution, test, throughput gain or
useful NPU offload is established here. The colleague's current engine instance
was untouched.

The NPU is not proven useful compared with native GPU memoization. Both would
feed the same local cache, and native GPU output capture is the presently more
reliable producer. A slower NPU producer can be hidden only when its complete
work and upload finish before a future lookup; it must never delay a miss.

## Native dependency and replacement seam

The [head ABI](halogen-mtp-full-head-state-abi-20261004.md) and
[projection seam](halogen-mtp-d-projection-integration-20261004.md) establish
the following order for the pinned native count1 wire-D path:

| Operation | Native boundary | Input and output |
|---|---|---|
| Token staging | Host copy `0x17db364`; H2D copy `0x17db382` | ABI host token -> staging `*(model+0x6b0)` -> device token `*(model+0x730)` |
| Embedding gather | Launch `0x17db449` | Table `*(model+0x4f0)` and token -> `*(model+0x6c8)` |
| Embedding RMS | Launch `0x17db517`; return `0x17db51c` | In-place 2560-word BF16 row at `*(model+0x6c8)`, raw gamma `*(model+0xae8)` |
| Embedding FC | Call `0x17db543`; return `0x17db548` | Descriptor `model+0x908`, normalized row -> projection `*(model+0xb00)`; N=K=2560, M=1 |
| Hidden preparation | RMS `0x17db62d`, then FC `0x17db65e` | Native hidden residual -> four projected streams |
| Seed-add and remainder | Seed setup after hidden FC | Native e/h projection addition, layer48, history and vocabulary continuation |

For fixed embedding-table bytes, gamma, FC weights and the qualified native
arithmetic route, the count1 embedding projection is a function of the token.
Hidden residual, ABI position and head history do not enter this computation.
This conclusion is conditional on those immutable bindings; arbitrary quant
overrides or another dispatch route are outside the audited contract.

The smallest replacement would check a local cache at the embedding FC seam.
A ready hit enqueues an ordered 5120-byte device-to-device copy into the original
projection destination and skips only the original M1 launch. A miss immediately
calls the original FC. Gather, embedding RMS, hidden FC, seed-add and native
head/controller behavior remain in use. The stored pointer values refer to GPU
allocations and must not be followed with CPU memcpy.

This hit path has no Windows/WSL request, provider call or wait for cache
production. An entry becomes ready only after its background GPU upload has
completed. Lookup and publication still have costs that require measurement.
The existing paired shadow shim executes both original FCs and then waits for
the candidate; it does not implement this cache path or a useful skip mode.

## When tokens are available

At full-head entry `0x17db310`, the ABI supplies the host token array. That is
sufficient for a ready lookup, but too late to wait for NPU work on the critical
path. The next speculative token becomes known when the preceding head returns;
the following draft head may start immediately, so there is no assured trunk
overlap between consecutive draft heads.

Before target verification at `0x173b6f6`, the current token and draft IDs are
known. Background preparation can run while the target trunk verifies them.
Normal accepted-prefix replay later uses shifted tokens
`[matched drafts..., target correction]`. The correction token is unavailable
until verification finishes. This is a possible overlap window, not evidence
that an entry will be ready or used.

Accepted-prefix replay through `0x17dcc90`/`0x17dcd4f` often has count greater
than one. Count1 M1 cache qualification cannot automatically replace its batch
FC: shape, dispatch and arithmetic equivalence require separate qualification.
The native first-proposal cache can also return without a full-head invocation.
Those already avoided calls must not be counted as extra embedding-cache
savings. The [accepted-prefix audit](halogen-mtp-accepted-prefix-replay-20261004.md)
and [head ABI](halogen-mtp-full-head-state-abi-20261004.md) retain these paths.

## Producer choices and accuracy requirements

| Producer | Feasible role | Remaining requirement |
|---|---|---|
| Native GPU memoization | After an ordinary miss, retain the actual original M1 projection with an ordered GPU copy; later occurrences can hit | Qualify repeated-token stability, lookup/publication, allocation lifetime and measured net gain |
| NPU background producer | Prepare future hot-token entries while idle or while the GPU trunk works; complete upload before lookup | Qualify native embedding gather/RMS and eFC outputs, prepare token-to-normalized-row assets or retain qualified native normalized rows, and show no harmful concurrent memory-bandwidth contention |
| CPU background producer | Same cache interface, if it can supply qualified outputs sufficiently early | Qualify native RMS and FC arithmetic; ordinary NumPy/BLAS does not establish the original packed DOT2 reduction |

The retained eFC oracle fixtures use CPU-prepared embedding RMS. They do not
establish native token-table gather or native embedding RMS parity. The original
embedding RMS replay source/preparation is retained separately, and any later
root execution must supply its own qualifying receipt and input lineage before
being used to admit a producer. Capturing a qualified native normalized row for
a previously seen token can avoid reimplementing RMS for that token, but does
not prepare unseen token rows.

An NPU eFC producer must pass the distinct native-GPU comparison. Existing
original-ORT suffix references cannot substitute for that oracle. CPU
`.002/.0002` and NPU `.03/.003` gates remain frozen and distinct; neither gate
alone establishes bit parity, unchanged proposals or end-to-end acceptance.
The [FC accumulation audit](halogen-native-fc-accumulation-20261004.md) explains
why BF16 weight rounding alone does not specify the native reduction.

Native GPU memoization needs no substitute RMS or FC arithmetic: it caches an
output the original head actually produced. This gives no reason by itself to
prefer NPU production. The NPU adds value only if qualified prewarming improves
useful hit coverage or reduces measured production cost without slowing the
target workload.

## Cache identity and lifetime

Cache content must bind token ID to immutable embedding-table, gamma, FC-weight
and native engine/arithmetic identities. Runtime use must also bind the model
generation and valid GPU allocation lifetime, so pointer reuse after unloading
or resetting an engine cannot admit a stale entry. Reject changed descriptors,
unsupported counts and unqualified dispatch routes; misses remain native.

Position, slot and acceptance rollback do not change the mathematical value of
this token-only projection. They still govern the live head invocation and its
destination, and must retain their original lifecycle checks. Background
publication must not overwrite an entry still used by a GPU copy. A bounded
cache of 256 BF16 rows occupies 1,310,720 bytes before metadata; 1024 rows occupy
5,242,880 bytes. These are capacity calculations, not allocated assets.

## Modest gain ceiling and decision

Using the root-supplied standalone M1 event cost of approximately 0.153 ms and
the current 42.15 decode tok/s baseline, a toy calculation that assumes exactly
one ideal hit per committed output and eliminates the entire 0.153 ms gives
`1000 / (1000 / 42.15 - 0.153) = 42.4236 tok/s`, or approximately **0.649%**.
This is an ideal toy bound with one hit for each output, not measured speed, a live-stage
latency guarantee, or an expected cache hit rate. Standalone event brackets
include instrumentation and enqueue gaps. Actual head calls per committed
token, hit rate, lookup/D2D cost and background contention determine the result.

The cache is a plausible modest decode optimization. It has no demonstrated
prefill benefit and no proven NPU advantage over native GPU memoization.
Only a matched end-to-end workload with output/acceptance checks can establish
a real tok/s delta. No prototype, hardware work or additional test was performed
for this design.
