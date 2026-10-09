# HC6 register-remap redirect: source and export contract

2026-10-09. Source-only preparation. No compilation, test expansion, HIP/module loading, hardware access, API request, public Git operation or serving-state mutation was performed here. Root owns build, launch, qualification, export and normal stop.

## Pins and arming

`redirect.c` targets Linux x86-64 using the sealed installed HIP declarations. The default is stock pass-through. To arm the redirect, all four environment variables must be present and valid:

| Variable | Required value |
| --- | --- |
| `HG0172_HC6_REMAP_CODE` | `/candidate/hc6-register-remap.hsaco` |
| `HG0172_HC6_REMAP_SHA` | `39053af36ed652892f7082af4eca5cd153b593260448b3c91a67f277cd0f1259` |
| `HG0172_HC6_REMAP_ENGINE_SHA` | `ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913` |
| `HG0172_HC6_REMAP_STATS` | An unused `/tmp/hc6-remap-<run>.bin` path with no additional slash |

No separate enable flag is required. Partial/mismatched configuration disables delegation. Stats creation uses `O_EXCL`, `O_NOFOLLOW`, mode0600, a regular-file check and fixed256-byte length. An existing stats file is not overwritten. Without configuration there is no stats file and no observer HIP call.

The constructor checks `/proc/self/exe` resolves exactly to `/usr/local/bin/flash_serve`, verifies that the fixed engine file inode matches the running image, reads exactly26,178,504 bytes and verifies the hard-coded engine SHA. SHA256 resolves dynamically from installed `/usr/lib/x86_64-linux-gnu/libcrypto.so.3`; no direct crypto link or subprocess is required. Candidate code is exactly17,765,424 bytes and the hard-coded candidate SHA above. Both reads use `O_NOFOLLOW`, `fstat` before/after and an anonymous private copy made read-only before hashing/loading. File-backed contents cannot change the loaded private copy. Parent directories and runtime library identity remain launcher-owned assumptions; `O_NOFOLLOW` guards the leaf rather than every parent component.

The root launcher must independently pin the shim source/library, wrapper, code object and engine; those manifest checks are separate from the shim's runtime checks. The original engine/code-object inputs remain unchanged.

## Exact dispatch scope

The only intercepted API is bare `hipLaunchKernel`. An eligible launch must have:

- The original process PID, qualified main-image base and function address `base + 0x18f4778`.
- Return caller `base + 0x180e5ec`.
- Grid `(256,1,1)`, block `(256,1,1)`, dynamic shared bytes0, original streamNULL and a non-NULL argument-vector pointer.
- Current device0 and a successful capture query reporting None, immediately before initialization/dispatch and again after initialization before candidate dispatch.

The argument vector is never dereferenced by the shim. Device/tensor/counter/output memory is never inspected or altered by host shim code. Kernel semantics remain the patched native code object's responsibility. NULL/legacy/per-thread-default identities are not substituted. `_spt`, module launch, other descriptors/callers/shapes and other devices follow stock.

The first eligible launch may lazily initialize the module and then attempt the candidate on that same invocation. Optional HIP targets are resolved before arming; only that eligible path calls `hipModuleLoadData` and `hipModuleGetFunction`. The exact function name is:

```text
_ZN7halogen12_GLOBAL__N_112k_hc6_fused3ILi3EEEvPtPKtPKfS4_iNS0_5LqGrpES2_liPKhS4_S2_PfPyySB_y
```

The standalone gfx1151 code object's explicit17-argument and hidden kernarg metadata are unchanged: kernarg680 bytes, alignment8, explicit arguments ending at offset424. `hipModuleLaunchKernel` receives the original `void **args`, exact grid/block, original stream, shared0 and `extra=NULL`. The native module API handles normal argument packing and hidden parameters; the shim creates no custom argument buffer.

Initialization is attempted at most once. A trylock allows concurrent/reentrant work to pass through stock while initialization is in progress. No lock serializes candidate launches after module publication. A failure before any candidate attempt delegates once to stock. After a candidate is attempted, its exact return status and target `errno` are returned; it is never retried through stock. A candidate error permanently disables later delegation. Original stock calls likewise preserve their return and target `errno`. The mandatory stock launch target must exist in the installed runtime; an impossible missing target exits127 rather than fabricating a HIP result.

Module, immutable code copy, crypto handle and stats mapping remain until normal process exit. There are no HIP destructor calls, module unloads, callbacks, synchronizations or per-launch timing/file I/O.

## Stats wire format

The file is exactly256 bytes, little endian. Header: Python `struct.Struct('<8sIIQ')`, size24, with magic `b'HGHC6R01'`, version1, byte count256 and engine PID. The following29 words use `struct.Struct('<29Q')`. Signed statuses/devices occupy two's-complement int64 values; decode words10–17 as signed int64. Initial status/device values are−1 (“not called/unknown”). All other words are unsigned counters/state values.

| Word | Meaning |
| ---: | --- |
| 0 | Owned-process hook calls |
| 1 | Exact descriptor/caller/geometry hits, including stock fallback |
| 2 | Candidate launch attempts; incremented before the single native module call |
| 3 | Stock launch calls |
| 4 | Owned-process calls outside the exact eligibility scope |
| 5 | Eligible nested/initializing/trylock-busy fallback |
| 6 | Nonzero candidate launch returns |
| 7 | Nonzero stock launch returns |
| 8 | State:0 disabled,1 armed,2 initializing,3 ready,4 failed |
| 9 | Failure reason, enumerated below |
| 10 /11 | Last initialization module-load / function-lookup status |
| 12 /13 | Last candidate / stock launch status |
| 14 /15 | Last device-query status / device ID |
| 16 /17 | Last capture-query status / capture state |
| 18 /19 | Module loaded / exact function resolved flags |
| 20 /21 | Engine SHA verified / candidate SHA verified flags |
| 22 | Initialization attempts |
| 23 | Delegation disabled after candidate error flag |
| 24 | Candidate bytes read |
| 25 | Eligible stock fallback calls |
| 26–28 | Reserved zero |

Failure reasons:0 none,1 configuration,2 stats setup,3 crypto symbol/library,4 engine file/identity,5 engine hash,6 main image/base,7 optional HIP symbols,8 candidate file,9 candidate hash,10 module loading,11 function lookup,12 candidate launch error. Device/capture eligibility failure leaves the armed/ready state intact and falls back to stock; words14–17 explain that decision.

These are atomic individual fields, not a transactional snapshot. At an established idle point before normal stop, root should read the file twice and retain identical copies with header/PID/file/hash checks. Do not interpret a read taken during launch activity as a closed receipt. For a stable successful run, check `hook_calls == attempts + stock_calls`, `hook_calls == eligible + ineligible`, `eligible == attempts + eligible_stock_fallback`, `init_attempts == 1`, `state == 3`, both image/code flags and module/function flags equal1, both error counters zero and every relevant HIP status zero. Candidate attempts/hits must be nonzero. Require bytes17,765,424 and source/runtime pins. Stock control without these env variables should have zero candidate attempts and no candidate module.

Do not claim submitted work has finished merely from these counters or successful module destruction; the shim performs no completion synchronization. Export requires the parent's established request/lifecycle boundary.

## Independent route assessment and limits

The route is source-feasible for this bounded experiment: it preserves the known17 explicit argument slots and native code/hidden metadata while changing only which module function the exact eligible dispatch uses. Its selection is stricter than descriptor identity alone. The candidate's14 changed bytes and resource claims are documented independently in `patch-receipt.json`; this shim does not prove their instruction equivalence or effective occupancy.

The parent's CPU build passed `-Wall -Wextra -Werror`; source SHA256 `892db21c72294589fdcbbb3bd85fcab86a9e79586573d7d392fab3bfe7c51832` and library SHA256 `bb7b2e7baf6281de6fc4bb23ee41bb6d4a41f4505fd3c1b797da9cf11ac16c35` match `build.json` and the current files. This source is frozen. Runtime qualification remains the parent's responsibility. Loading a standalone native code object creates a separate HIP module and may change loader, hidden-parameter, global/constant placement, dispatch and resource behavior compared with the engine's registered function. The known metadata and unchanged argument vector make the route plausible, but do not establish equivalence. Root must require successful initialization/launch statuses, correct candidate hit counts and native output/counter/guard parity before performance interpretation. A stock-native code object through the same module route would help distinguish route effects from register-remap effects if that distinction becomes necessary.

HIP initialization/device/capture/module APIs execute on the engine thread and can change HIP last-error state. Saving return values and `errno` does not preserve every error-path semantic. A capture-status check also leaves a race with concurrent capture transitions; the controlled window requires established absence of such transitions. Publication prevents partial initialization reuse, but already admitted concurrent candidate calls cannot be cancelled if another candidate fails. The retained engine evidence observed a single host producer; the shim does not manufacture that guarantee.

First-hit CPU hash/copy/module initialization adds warmup overhead, and per-hit device/capture checks add host work. The code has no per-launch event bracket and no GPU busy timeline. VGPR rounding and theoretical10→12 waves/SIMD are candidate hypotheses; actual residency, arithmetic correctness and serving gain require parent-owned qualification. The earlier instrumented HC6 score is not a removable compute budget and cannot predict this candidate's speedup.
