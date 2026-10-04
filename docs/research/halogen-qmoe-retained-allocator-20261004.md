# Retained Light allocator-session candidate — 4 October 2026

**Compiled but never invoked.** This is a separate opt-in source candidate,
not a proven access-violation repair, NPU execution, complete MTP implementation
or speed gain. It was prepared after the nine-hour hardware window ended;
no provider session, inference call or real-bank conversion was performed.
Current matched stock remains 1661.0181 PP-only / 47.0600 MTP decode tok/s /
60% acceptance, in separate 8K PP/TG cohorts.

## Source-backed change

The preserved [failed helper](../../scripts/benchmarks/halogen_qmoe_session_allocator.c)
obtains the allocator from its actual QMoEBf session. Official OGA v0.14.0
instead initializes a separate holder using its embedded 96-byte Constant
graph and obtains `Cpu` / `OrtDeviceAllocator` / device0 / default-memory
allocation from that session before creating the decoder session. The holder
outlives its allocated buffers. This difference is established in source;
its role in the observed first-call AV is not. [OGA initialization](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/models/model.cpp#L343-L417).

The new [native source](../../scripts/benchmarks/halogen_qmoe_retained_allocator.c)
uses public ORT1.29 CAPI and the same pinned Light registration/bootstrap
contract. Actual QMoEBf options are prepared first. The holder then receives
fresh default options, the same `model_root`, zero provider-option pairs,
the pinned custom-op library and ERROR log severity. It does not inherit
QMoEBf's external-data/token-backend/dynamic-expert settings, thread limits,
profiling or disabled CPU fallback. The Constant graph is not run. Allocator
acquisition precedes actual-session creation; only the actual strict QMoEBf
session receives `RunWithBinding`. [Provider setup](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/ryzenai/session_options.cpp#L6-L13),
[device interface](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/ryzenai/interface.cpp).

Normal cleanup releases bindings and values, the actual session, allocator,
memory info, holder session, both option sets, provider registration,
environment and ORT module. A fault can bypass native cleanup, as in the
preserved earlier attempt. The new holder is local to one bounded invocation;
OGA retains its holder globally across models. Its environment CPU-arena
registration and optional provider shutdown are not reproduced here.
Full OGA equivalence remains unproved.

## ABI, outputs and evidence

The separate exported function is `qmoe_retained_allocator_run`. Its
[Python hook](../../scripts/benchmarks/halogen_qmoe_retained_allocator_invoke.py)
uses receipt schema2, size88, QPC-frequency offset64 and tick-array offset72.
Session-creation attempts and successes are distinct. Holder creation and
release have separate fields. The C compile-time checks and Python class
layout agree. Synthetic admission, full MTP and speed gain remain separate
claims; `complete_mtp_proven` and `speed_gain_established` remain false.

Both Python hooks now hash only validated outputs copied into their receipt
buffer. Native `calls_completed` precedes zero validation and copy: hashing
that many slots could emit a sentinel hash when validation fails after a
returned call. The scoped pure-Python reproducer failed before the correction
and passed afterward, also confirming the hash for a validated/copied slot.
It evaluates the actual serializer expression; it does not load the DLL,
create an ORT session or call the NPU. Historical raw receipts, the original
native C hash and its built DLL remain unchanged.

[Source/build evidence](halogen-qmoe-retained-allocator-20261004.json) records
the new source, wrapper and DLL hashes; pinned API-header hashes; graph-byte
identity; AST/layout checks; compile exit0 and zero runtime attempts/returns.
The original C source remains SHA256
`acd9d442a460158f0ae8bf204a55db67e1390e8aab2a0d5ce8be247ad4d496af`.
Existing MSVC built with `/TC /W4 /WX /O2 /MD /LD`; no warnings were suppressed.
The embedded graph matches the downloaded v0.14.0 upstream array byte for byte.
`dumpbin /exports` confirms the distinct function without loading the DLL.

The unchanged historical guard still pins the historical candidate. This new
hook is not wired to production or to an automatic runner. Any future native
attempt needs its own reviewed source/DLL pins and receipts within the
existing exclusive owned-process and memory-reserve contract. Compilation
does not establish bounded provider resource use, supported expert geometry,
valid outputs, residency, latency, accepted tokens or Flash-Next integration.

Even successful synthetic admission would leave the full target work
unfinished. The checked public Halogen engine has no documented external
Flash-Next drafter/verification/state-transaction contract; independent NPU
services are a different interface. [Integration assessment](halogen-laya-jev-sidecar-feasibility-20261004.md).

## Prepared invocation; extension pending

Separate local guard/probe sources have now been prepared under
`server/.local/optimization9h-20261004`, with the native/source/header pins and
the existing frozen graph/ORT-stage contract. They require
`--allow-post-window-admission` in both entry points; missing-flag checks
returned guard exit1 and probe exit2 without creating a report or initializing
a native session. The exact proposed argument vector and final source hashes
are retained in `retained-allocator-runner-preparation.json`; it is a
preparation record, not an inference result. No post-window extension has
been received and no native admission was launched.

The new guard retains ownership attached to constructor exceptions, records
closure/final-idle/final-reserve failures independently, pins `server/winjob.py`
and holds a shared latch through pending closure of the same child. That latch
coordinates cooperating retained-session guards only; the historical guards
remain unchanged and root must exclude concurrent historical launches.
Lifecycle changes received source review and AST parsing, not runtime
qualification. After a caught native exception, the probe leaves unavailable
native counters null and preserves stdout/fault evidence. Its outer schema1
is distinct from native schema2; strict no-CPU-fallback applies to the actual
QMoEBf session, while the holder uses defaults and empty EP options.

The proposed attempt retains 22-GiB initial and 18-GiB monitored physical/commit
reserve and the 90-second native-child limit. Successful synthetic admission
would still not prove full NPU MTP, residency, quality or throughput. A new
hardware execution requires extension of the user's original nine-hour window.
