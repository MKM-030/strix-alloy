# QMoEBf session allocator: RMM acquired, first call faults

Date: 2026-10-04. This report consolidates saved root-owned attempts. No new
native execution, build, import, device call, bank read, or package rehash was
performed for this report. Evidence hashes are in the sibling
`halogen-qmoe-session-allocator-20261004.json`.

**Result:** the public ORT CAPI path acquired the Light session's `RMM`
allocator, but the corrected helper faulted during its first inference call.
It returned no output. These attempts establish no NPU throughput, Prefill or
Decode improvement, MTP acceptance improvement, or complete MTP support.

## Scope and allocator contract

The frozen synthetic zero-bank graph contains one AMD Light `QMoEBf` node,
512 experts/top10, BF16 `[1,2560]` activation/output and FLOAT `[1,512]` router.
CPU fallback and automatic acquisition were disabled. This is isolated
admission work, not inference with the real Qwen weights.

OGA retains a separate trivial session to obtain and keep its device allocator
alive. For RyzenAI it requests `Cpu`, `OrtDeviceAllocator`, device 0 and default
memory, then uses that allocator for buffers with shared CPU/device addresses.
[OGA allocator initialization](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/models/model.cpp#L354-L417),
[RyzenAI buffer allocation](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/ryzenai/interface.cpp#L25-L40).

The native helper uses public CAPI29 to obtain an allocator from the actual
QMoEBf session, allocate both inputs and an explicit output, bind inputs after
filling each fixture, synchronize inputs before running and outputs before
readback, and release values/allocator before session/provider/environment.
Equivalence to OGA's separate persistent trivial-session initialization remains
unproved.

The first helper added a requirement that the returned allocator name be
`Cpu`. Root removed that requirement after source comparison: `CreateAllocator`
wraps the session allocator; ORT looks it up by `OrtDevice`, and OGA does not
compare the returned name. A request named `Cpu` can therefore return `RMM`.
[ORT CAPI allocator lookup](https://github.com/microsoft/onnxruntime/blob/v1.29.0/onnxruntime/core/session/allocator_adapters.cc#L214-L223),
[session allocator registration and device lookup](https://github.com/microsoft/onnxruntime/blob/v1.29.0/onnxruntime/core/framework/session_state.cc#L120-L146).

## Saved attempts

All receipt directories are under `server/.local/optimization9h-20261004/`.

| Receipt directory | Outcome | Inference attempts / returns |
|---|---|---:|
| `qmoe-light-admission-db32fa0ec39a4c92850036df59844d1b` | Python strict session initialized in 115.2467 ms; `HOST_ACCESSIBLE` memory info was absent. Failed at `synthetic_call_0_prepare`. | 0 / 0 |
| `qmoe-light-admission-1c9baae117d84816ab28050abaae2482` | Native strict session and allocator acquired; the extra allocator-name check rejected it. Returned allocator name was not recorded. | 0 / 0 |
| `qmoe-light-admission-9436f2f0f523473c874705172cfb035a` | Corrected helper logs `name=RMM type=0 mem=0 device=0`, then `synthetic_call_0_invoke`; no return marker. | 1 / 0 |

The latest ctypes call raises
`OSError: exception: access violation reading 0x000004A88F029680`.
Its native receipt was never returned. Outer `call_count:0`,
`completed_calls:0` and `session_creations:0` are initial defaults and do not
override the native stdout markers. The initial helper's output hashes cover
unexecuted sentinel buffers. The latest 182.1987 ms value is elapsed failed
admission host time, not inference timing.

Root subsequently preserved the corrected C source as
`scripts/benchmarks/halogen_qmoe_session_allocator.c` and the invocation wrapper
as `scripts/benchmarks/halogen_qmoe_session_allocator_invoke.py`. The wrapper's
follow-up serialization change records output hashes/timings only for
completed calls. Root reports source review and AST parsing of that change,
without another execution. The raw receipts above describe the earlier
observed runs; they are not results from the revised wrapper.

## Fault and cleanup limits

The latest fault record reports read AV `0xc0000005`, RIP
`0x00007ffbda7ca541`, fault address `0x000004a88f029680` and
`module_lookup:unknown`. The collector's 56-module snapshot predates provider
loading. This record cannot establish the faulting module or caller, nor that
it is the earlier XRT null-BO fault documented in
`halogen-qmoe-xrt-fault-20261004.md`.

The first native helper returned through C cleanup: values/session were
released and provider unregistration completed. The corrected helper did not
return through native cleanup (`native_cleanup_normal_return:false`). ctypes
caught the access violation, allowing the Python collector to stop, DLL search
directory handles to close and bootstrap shutdown to complete. These Python
actions do not prove native allocator/session/provider cleanup. Every parent
guard recorded child exit 1 and owned-job closure.

| Attempt | Parent guard minimum physical bytes | Parent guard minimum commit headroom bytes |
|---|---:|---:|
| HOST_ACCESSIBLE | 47,460,294,656 | 213,449,003,008 |
| Initial native name check | 46,919,348,224 | 213,229,412,352 |
| Corrected RMM helper | 46,459,703,296 | 212,530,659,328 |

These are guard-reported minima, not global minima. The child reports lower
physical minima of 44.1602, 43.6439 and 43.2922 GiB respectively. Every guard
also verified the complete pinned ORT1.29/API29 stage after its attempt
(630 files, 45,280,440 bytes).

No valid output, completed-call timing, placement attribution, real-bank
admission or speed gain was produced. Further executions are stopped; the
saved failure is the result of this allocator candidate.

The retained [native C source](../../scripts/benchmarks/halogen_qmoe_session_allocator.c)
matches the corrected executed candidate and compiled with existing MSVC
`/TC /W4 /WX /O2 /MD /LD`. It needs the pinned official ORT1.29 headers and
the caller's exclusive owned-process guard; it is not connected to production
Halogen inference. The retained
[invocation hook](../../scripts/benchmarks/halogen_qmoe_session_allocator_invoke.py)
has a subsequent serialization-only correction: timing/output-hash entries
are emitted only for completed calls. That hook's syntax was parsed without
native imports; no runtime rerun is claimed for the correction. Original
attempt receipts and the rejected helper's sentinel hashes remain preserved.
