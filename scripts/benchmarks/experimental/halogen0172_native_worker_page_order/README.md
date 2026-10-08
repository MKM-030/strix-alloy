# Halogen 0.17.2 native-worker page ordering

This experimental source snapshot targets only the Linux x86-64 Halogen
**0.17.2** `flash_serve` executable, exactly 26,178,504 bytes, with SHA-256
`ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`.
The four attachment sites check their exact native instruction bytes before
patching. A version label alone is insufficient.

The package is **off by default**. The constructor attaches only when
`PLE0172_NATIVE_WORKER_PAGE_ORDER=1` is explicitly set for that exact executable.
Leave the variable unset to disable it; another value, including `0`, aborts an
attempted attachment to `flash_serve` with exit 79.

## Scope

The native worker retains its original token reservations, scalar ID arithmetic
and native ID stores. After each token's 16 IDs exist, selected workers skip the
original raw row-copy block. The last ID producer prepares a source-page
schedule from the completed original ID vector. The same native workers claim
disjoint source pages and scatter exact raw bytes into original token/head
destination order. Every successful phase return observes all completed copies.
The original worker completion epilogue, native waits/joins, H2D, GPU unpack,
RMS and FC remain in the native flow.

Selection happens once before native thread start. It requires a nonnull native
output, 256–8192 tokens (4096–131072 rows), the actual native count of 1–256
workers, native stride 160/encoding 0, valid native allocations and a qualified
selected HGN mapping/header/tensor directory. Scratch is capped at 6 MiB. Warm
output, small decode windows and unqualified contexts retain the original path
before any copy is skipped. Stride 90/encoding 1 is excluded.

| Site | Role | Selected continuation |
| --- | --- | --- |
| `0x1801426` | Select context/generation before native threads start | Original replay at `0x180142d` |
| `0x1865ab4` | Skip only original raw copies after all 16 native IDs exist | `0x1865791` with restored native `rbp`/`rcx` |
| `0x1865d72` | Post-ID page phase before original completion epilogue | Original replay at `0x1865d78` |
| `0x17eec5b` | Require complete matching generation after native joins | Original replay at `0x17eec62`, before H2D |

The assembly saves all live general registers, flags, x87, MXCSR and XMM state.
Build the dispatchers without AVX/AVX2/AVX512: this exact binding does not preserve
live upper YMM/ZMM state. The adapter follows native context/mapping/raw-buffer
owners; it does not establish a new independent ownership lease.

## Files and provenance

The five production inputs are `native_detour_0172.cpp`, `native_patch_0172.h`,
`native_seams_0172.S`, `page_phase_0172.h` and `page_segment_scheduler.h`.
The three focused fixture sources are `binding_fixture.cpp` and
`native_seams_cpu_fixture_0172.cpp`/`.S`.

`source-provenance.json` records each original private source path, byte count
and SHA-256, its public copy's byte count and SHA-256, and the exact relocation
change. All files are verbatim copies except `page_phase_0172.h`, whose scheduler
include is changed to the local `page_segment_scheduler.h`. The manifest also
identifies the original private build receipt and artifact by hash. No shared
object or fixture executable is included in this directory.

## CPU build and fixture commands

Run these from this directory on Linux x86-64 with C++20, POSIX threads, and
OpenSSL development headers/library already available. Commands write generated
binaries outside the source package.

```sh
g++ -std=c++20 -O2 -Wall -Wextra -Werror \
  -mno-avx -mno-avx2 -mno-avx512f -fPIC -shared -pthread \
  native_detour_0172.cpp native_seams_0172.S \
  -o /tmp/libple0172_native_worker_page_order.so -ldl -lcrypto

g++ -std=c++20 -O2 -Wall -Wextra -Werror \
  -mno-avx -mno-avx2 -mno-avx512f -pthread \
  binding_fixture.cpp native_seams_0172.S \
  -o /tmp/ple0172_binding_fixture -ldl -lcrypto
env -u PLE0172_NATIVE_WORKER_PAGE_ORDER -u LD_PRELOAD /tmp/ple0172_binding_fixture

g++ -std=c++20 -O2 -Wall -Wextra -Werror \
  -mno-avx -mno-avx2 -mno-avx512f -fno-omit-frame-pointer -no-pie \
  native_seams_cpu_fixture_0172.cpp native_seams_cpu_fixture_0172.S \
  native_seams_0172.S -o /tmp/ple0172_native_seams_cpu_fixture
env -u PLE0172_NATIVE_WORKER_PAGE_ORDER -u LD_PRELOAD /tmp/ple0172_native_seams_cpu_fixture
```

The binding fixture exercises synthetic HGN mapping qualification, split
protections, unreadable gaps, an 8192-token/64-worker raw copy, and selected
cancellation/exception exits. The assembly fixture exercises all four wrappers,
both native stack alignments, register edits, flags/floating-point state and the
original completion CMP branches. These fixtures use synthetic CPU data; their
output cannot establish serving coverage or performance.

## Runtime receipt and abort restoration

Runtime experiments belong to the authorized root's existing normal lifecycle
and its private receipt-bound launcher. That launcher validates pinned engine,
backend, normal controller/service, profiles, source inventory, build artifact
and independently supplied receipt/launcher seals before admitting a candidate.
Its checkout/profile paths are intentional private bindings, so the launcher is
not published as a reusable interface here. The relocated public sources have
different paths and a different page-phase header hash: an original private
receipt must not be reused to authorize an artifact rebuilt from this package.
Such a run requires a fresh root-sealed receipt and normal-lifecycle admission.

Once any original copy is skipped, cancellation, invalid IDs, owner drift,
selected C++ unwind, phase failure, incomplete consumer state or expiration of
the bounded selected window must abort the process with **exit 79 before H2D**.
There is no selected fallback to original copying with an exhausted ID cursor.
After exit 79, the authorized root must use the normal controller's stop/join and
cleanup path, restore the sealed stock configuration with the candidate enable
and preload removed, and verify stock service health before resuming requests.
Do not recover by continuing the failed context or treating its partial raw
output as complete.

Coverage, correctness and performance results will be documented in the
[native-worker comparison report](../../../../docs/benchmarks/halogen0172-native-worker-page-order-20261008.md).
This source package makes no benchmark result claim.
