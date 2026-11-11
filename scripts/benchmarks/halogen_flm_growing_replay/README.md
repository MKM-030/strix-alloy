# Growing FLM raw-ID replay component

This package contains the source of the finite NPU replay component and its
CPU-tested authority protocol. It is default-off. It provides no live IPC,
Windows/WSL publication, resident NPU worker or Halogen integration. Native MTP
acceptance, arrival before target demand, NPU-prefill tok/s, NPU-decode tok/s
and full-engine speed benefit remain unqualified.

## Measured component scope

The [11 November 2026 component result](../../../docs/benchmarks/halogen0201-growing-npu-20261111.md)
used the retained typed FLM 1.0.7 Qwen3.5-0.8B engine. The candidate and a direct
sequential reference ran in separate fresh native processes. All **32,001,030
BF16 values** match exactly across 129 states: one complete logits row of
248,070 vocabulary values at each state, with no relaxed tolerances.

The 512-ID seed took 425.0998 ms. The mean authoritative one-ID append took
22.3904 ms. These Windows QPC operation times include library processing and
CPU logits ownership/argmax; row-file writes are separate. They are not pure
NPU kernel timings and must not be converted into measured Halogen tok/s.
Offline next-ID agreement was 66/128 = 51.56%, which is not native acceptance.
The teacher sequence came from one 8,192-token document family and the paired
2048 target warmup, distinct from the promoted paired 8192 serving trajectory.

The new growing strategy seeds the exact last 512 authoritative prompt IDs
once, then appends only the 128 recorded target IDs through local context 640.
`ready_one()` returns one ID from already owned logits before the next teacher
ID is supplied. It performs no speculative forward, seed rebuild, checkpoint,
restore or retained-window eviction. The reference performs the identical
clear/seed/sequential teacher sequence without proposal calls. This result
does not repair or reinterpret the older sequential-versus-full-prefill test.

## Source layout

- `growing_bridge.hpp` reuses the unchanged [original typed bridge](../halogen_flm_raw_id_bridge/bridge.cpp)
  for complete BF16 ownership, finite checks and lowest-ID greedy ties.
- `replay_host.cpp` is the bounded Windows AMD64 native replay host. It records
  all owned values, exact IDs and actual native/in-process host QPC endpoints.
- `protocol.py` and the unchanged `token_feedback.py` dependency implement the
  default-off authority controller. Its native backend/transport binding is not
  implemented by this package. Receiver arrival and target need remain null.
- `replay_tools.py` provides CPU-only input validation, the exact full-value
  comparator and a build recipe. Its default invocation only prints a recipe.
- `pe_preflight.py` reads PE bytes without loading code. Payload imports are
  checked; Windows API-set contracts and internal OS dependency trees retain
  explicit separate status. A payload pass does not claim complete OS namespace
  closure, dynamic plugin coverage or behavioral ABI compatibility.

The CPU suite uses generated fixtures and requires no compiler, model, DLL,
device, API or private replay data:

```powershell
python -B -m unittest discover -s scripts/benchmarks/halogen_flm_growing_replay -p 'test_*.py' -v
```

It runs 39 tests: 17 authority-protocol, 11 replay and 11 static-PE tests.

## Native build and execution boundary

Root's existing controlled build/lifecycle tools own native work. No build or
native invocation occurs during Python import or the CPU suite. Build recipes
write binary/object outputs only below `server/.local`; the default directory
is `server/.local/halogen-flm-growing-replay/build-v1`. A public source-tree
binary output path is rejected.

```powershell
python -B scripts/benchmarks/halogen_flm_growing_replay/replay_tools.py
```

The recipe preserves the original successful 1.0.7 build options, including
MSVC AMD64 C++20, `/Zc:__cplusplus`, `/MD`, `/O2`, `/fp:precise` and
`DISABLE_ABI_CHECK=1`. `FLM_USE_HRX` must remain undefined. The actual XRT SDK
guard in `xrt/detail/abi.h` omits `version-slim.h` and initializes
`xrt::detail::abi.major/minor/code` to zero when that option is defined. This
inherited version/schema sentinel behavior does not prove the by-value C++
`LM_Config`, STL/JSON or buffer ABI. Matching public headers/import libraries
and actual loaded module identities are still required.

The retained model directory is
`C:/AI/models/halogen-proposer-qwen35-08b-1d16e5e`; the xclbin bundle root is
`C:/AI/src/FastFlowLM-zip/FastFlowLM-1.0.7/src`, the parent of `xclbins`.
The retained portable DLL directory is
`C:/AI/runtimes/flm-1.0.7-npu-probe/portable`. Models, runtimes, proprietary
binaries, input captures and replay outputs are not included in this source
package. Verify their exact hashes and the compiled EXE's static payload
imports before any native invocation. Windows import linking can load DLLs
before `main`, even for `--help` or invalid arguments.

The finite executable interface is unchanged:

```text
growing-replay.exe --run candidate MODEL_DIR BUNDLE_ROOT INPUT.json CANDIDATE.json
growing-replay.exe --run reference MODEL_DIR BUNDLE_ROOT INPUT.json REFERENCE.json
```

Use separate fresh processes sequentially, the same sealed input, unique
outputs and normal ownership/memory monitoring. Do not automatically repeat a
failed run. The existing policy requires 22 GiB physical/commit entry headroom
and retains 18 GiB during execution. Keep the normal GPU server ready afterwards.

The offline comparator retains the original zero-different-BF16-word criterion:

```powershell
python -B scripts/benchmarks/halogen_flm_growing_replay/replay_tools.py --compare CANDIDATE.json REFERENCE.json --output FRESH_COMPARISON.json
```

## Measured binary provenance and relocation

The measured executable was built from the private frozen preparation under
`server/.local/halogen-update-20261110/primary0201`. This canonical source copy
changes only include/import paths, repository-root resolution and private
build-output paths. It preserves computation, scheduling and equality criteria.
An unchanged authority dependency is included locally so CPU tests do not depend
on private preparation directories. Frozen inputs, binaries and receipts remain
in place. This relocation is not a new hardware measurement.

| Measured private artifact | SHA256 |
| --- | --- |
| `growing-native-build-v1/growing-replay.exe` | `830f6cb17628a82372c78b3b2a0fbc5843f3b9bf9a55ccc4c4e74f89ca64770d` |
| `growing-native-replay-prep/replay_host.cpp` | `e7f51d029afc59ff7bd660c6e96a5bc1c71826325b73ce630c0125068b2e25c1` |
| `growing-raw-proposer-prep/growing_bridge.hpp` | `9a3640c340588738d79991d3a185200bc8c46a8bab60e535d1e08fbb4536e4c6` |
| `growing-native-replay-prep/input-natural8192.json` | `7ca5117fc7570b079fe2eba777220f1acc389601db2849233b7c67d22ae9a7dd` |
| `growing-native-replay-prep/preparation-v2.json` | `dad5a916f861468a4bd3a9613d3e11d7e327e6b21150b4cc1ee8e0943d038da8` |
| `growing-native-replay-v1/comparison.json` | `43f6e5e7565a4c28a30dcff2c7220f08ba27d812371fd994320cf7b1d7c270c9` |

The measured Qwen DLL SHA256 is
`d77388dcd21fcd7422005d0f780a044142d525e3afaafef3bcb9e980b8c18501`;
the preserved current System32 XRT SHA256 is
`d0dce13280a0d668b497d4fcabdcb43f1a7353e466af3acabd98c6df7607ed8e`.
Do not install or downgrade a driver to reproduce historical bytes silently.
Root compiled the canonical source with the same pinned toolchain and libraries.
Its `.text`, `.data`, `.pdata` and `.reloc` bytes match the measured executable.
The complete files differ only at COFF and debug-directory timestamps; `.rdata`
contains the mirrored debug timestamp. All 39 canonical CPU tests pass. This is
a source-relocation/build check, with no extra NPU invocation.
[Machine-readable comparison](../../../docs/benchmarks/halogen0201-growing-npu-source-equivalence-20261111.json).
