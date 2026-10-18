# Native NPU dispatch probe

This source probes one native XRT dispatch with persistent device, hardware context,
kernel, instruction/input/output BOs and one reusable `xrt::run`. It uses synthetic
integer data only. It does not implement a token-generation path. Only the root
hardware/lifecycle owner may build and run it after independent source review.

`control` copies input elements 0..63 to output with signed widening. `gemv-vector`
computes a row-major 64 by 256 integer GEMV using eight 32-lane `acc32` MACs and an
exact i32 reduction per row. `gemv-scalar` is a separately selected, explicitly
labeled fallback; the build never silently substitutes it for the vector mode.
Control and GEMV both DMA one i16[256] input (512 B) and one i32[64] output (256 B)
per dispatch. There is no batched R=8/32 work or division of repeated-launch time.

GEMV's 32 KiB synthetic weight array is an initialized compute-tile `aie.buffer`
on tile (0,2) of `npu2_1col`. The array is absent in control mode. The finite core
loop consumes at most 64 vectors and produces at most 64 results. Host defaults
are 8 warmups plus 48 measurements (56 calls); CLI rejects totals greater than
64. Each call changes input, including a unique first-element call marker,
poisons all output elements, synchronizes the poison to device, and verifies
every output exactly against an int64 CPU reference. No mailbox, forever worker,
autorestart or loop around run construction is used.

The nominal GEMV tile payload is 32,768 B weights + 1,024 B input FIFO + 512 B
output FIFO + 4,096 B declared stack = 38,400 B. The emitted allocation/linker map
must establish actual bank placement, alignment and stack fit before execution.
The synthetic bound is |output| <= 22,696, so conversion and reduction require no
rounding or saturation. Model weights are never read.

## Build only

Use an existing x64 MSVC Native Tools PowerShell environment. The script checks
installed paths, builds into a fresh directory, retains compiler intermediates,
records source/artifact SHA256 hashes, and restores its process-local environment.
It does not install tools, alter global environment, or launch `host.exe`.

```powershell
& .\build.ps1 -OutDir 'C:\path\to\fresh\native-dispatch-build'
# Optional, separate scalar fallback build:
& .\build.ps1 -OutDir 'C:\path\to\fresh\native-dispatch-scalar' -Modes 'gemv-scalar'
```

Installed defaults are Python/MLIR-AIE 1.3.4 in `C:\AI\runtimes\ironenv`,
LLVM-AIE/Peano in that environment's `Lib\site-packages\llvm-aie`, and XRT SDK in
`C:\Xilinx\XRT`. Generator imports only compiler dialect APIs; it never opens an
XRT device. The generator rejects a wheel whose public version differs from
1.3.4. The rolling source tree is attribution/reference material, not an import
path or compiler replacement.

The equivalent minimal commands, from a fresh mode-specific directory with
the same process environment as the script, are:

```powershell
$taskSource = 'C:\Users\Marcel\.codex\worktrees\npu-ready-embedding\strix-alloy-clean\scripts\benchmarks\halogen_npu_native_dispatch'
$taskMlir = 'C:\AI\runtimes\ironenv\Lib\site-packages\mlir_aie'
$taskPeano = 'C:\AI\runtimes\ironenv\Lib\site-packages\llvm-aie'
& 'C:\AI\runtimes\ironenv\Scripts\python.exe' "$taskSource\generate.py" --mode gemv-vector --mlir design.mlir --abi design.abi
& "$taskPeano\bin\clang++.exe" --target=aie2p-none-unknown-elf -O2 -std=c++20 `
  -D__AIE_API_AIE_ADF_HPP__ -DDISPATCH_ENABLE_VECTOR=1 "-I$taskMlir\include" "-I$taskSource" `
  -ffunction-sections -fdata-sections -fstack-size-section -c "$taskSource\kernels.cc" -o kernels.o
& "$taskMlir\bin\aiecc.exe" --aie-generate-xclbin --xclbin-name=design.xclbin `
  --aie-generate-npu-insts --npu-insts-name=insts.bin --xclbin-kernel-name=MLIR_AIE `
  --no-xchesscc --no-xbridge --no-compile-host `
  "--peano=$taskPeano" --tmpdir=intermediates --dump-intermediates design.mlir
cl.exe /nologo /std:c++17 /Zc:__cplusplus /EHsc /O2 /I'C:\Xilinx\XRT\include' "$taskSource\host.cpp" `
  /Fe:host.exe /link /LIBPATH:'C:\Xilinx\XRT\lib' xrt_coreutil.lib
```

For control or scalar, change the generator mode and omit
`-DDISPATCH_ENABLE_VECTOR=1`; the scalar/control translation unit excludes AIE
vector headers and the vector function. `link_with="kernels.o"` is attached to
the external function declaration, as required by installed 1.3.4; it is not
attached to the `core` decorator.

## ABI and timing contract

The exact XRT kernel name is `MLIR_AIE`. Host inspects xclbin metadata before
opening the device and fails on incompatible live argument names, sizes, offsets
or indices. The ABI is:

| Index | Name | Bound value | Size/offset |
| --- | --- | --- | --- |
| 0 | opcode | uint64 value 3 | 8 B / 0x00 |
| 1 | instr | cacheable instruction BO | 8 B / 0x08 |
| 2 | ninstr | uint32 instruction **word count** | 4 B / 0x10 |
| 3 | bo0 | host-only 512 B input BO | 8 B / 0x14 |
| 4 | bo1 | host-only 256 B output BO | 8 B / 0x1c |

Compiler metadata can append `bo2`..`bo4` padding slots at successive 8 B offsets.
The host validates and records them and leaves them unbound. It does not add
generic wrapper dummy control/trace arguments. The runtime sequence declares
exactly two buffers, input then output. The instruction BO is synchronized once
at initialization. Runtime DMA waits consume both input and output completion
tokens before reusing BD IDs on the next launch. Required input/output BO
synchronizations remain in every call.

Initialization includes artifact reads/validation, device/context/kernel creation,
BO allocation/map, instruction copy/sync, run construction and argument binding;
it is reported separately from dispatch samples. Each measured sample records
`run.start()` through bounded `run.wait()` and the complete interval from input
copy/output poisoning through input/poison sync, launch/wait, output sync and
readback copy. Input/reference construction and exact verification lie outside
the complete interval. Verification time is recorded separately. Warmups undergo
the same verification but are excluded from p50/p95/mean/min/max statistics.
Percentiles use linear interpolation at q*(n-1); JSON preserves every sample.

## Root-owned execution and review

Before execution, review generated MLIR, xclbin argument metadata, retained tile
allocation/linker maps, and instruction sequence against the source/ABI and
build-receipt hashes. The design has not been compiled or run as part of this
source handoff. Vector overload legality, dialect lowering, allocated memory and
the installed NPU driver/XRT binary compatibility remain unverified until the
root-owned build and probe. The installed Core API's function-level link option
and the experimental xclbin header path are already reflected in source.

The initial program/core enable/reset semantics of the emitted instruction
sequence must be inspected: this is a persistent host-object dispatch floor
probe, not proof that every dispatch avoids configuration or reload. The host
conservatively permits only 64 total calls in one cohort regardless of replay
semantics. A new cohort requires a new process/context; do not reuse the same
finite core beyond its budget.

The root must enforce an external process/job deadline (for example 90 seconds)
and exclusive owned-device lifecycle before invoking the following example.
Its child process must resolve the installed XRT runtime DLLs through the normal
installed runtime or a child-process-only PATH containing `C:\Xilinx\XRT`.
Do not execute it directly outside that guard:

```powershell
& 'C:\path\to\native-dispatch-build\host.exe' `
  --xclbin 'C:\path\to\native-dispatch-build\control\design.xclbin' `
  --instructions 'C:\path\to\native-dispatch-build\control\insts.bin' `
  --abi 'C:\path\to\native-dispatch-build\control\design.abi' `
  --output 'C:\path\to\control-result.json' --warmups 8 --measurements 48 `
  --wait-ms 500 --deadline-ms 20000
```

The host uses `run.wait(timeout)` and a steady-clock overall deadline, requiring
`ERT_CMD_STATE_COMPLETED`. On in-flight failure it attempts to abort only its
owned run. XRT documents that wait timeouts can be masked and abort is blocking;
BO sync, initialization and teardown can also block, so in-process bounds do not
replace the root's external deadline. Repeat the root-owned guarded process with
the GEMV artifact paths for the second cohort. Component timings are reported
in microseconds only and must not be presented as token rates.

## License and attribution

Source is provided under Apache-2.0 WITH LLVM-exception; `LICENSE.txt` is the
MLIR-AIE license text copied from the locally installed reference source tree.
Setup/lowering patterns are adapted from AMD/Xilinx's MLIR-AIE project, especially
`test/npu-xrt/add_one_cpp_aiecc/test.cpp` and
`test/npu-xrt/add_one_func_link_with_peano/aie.mlir` (copyright 2026 Advanced Micro
Devices, Inc., same license). AIE vector operations follow the AIE API and
MLIR-AIE linalg/conv/reduction examples. No FLM artifact or model payload is used.

Upstream references: [MLIR-AIE](https://github.com/Xilinx/mlir-aie),
[AIE API](https://github.com/Xilinx/aie_api),
[XRT](https://github.com/Xilinx/XRT). Exact local dialect API sources are
`mlir_aie\python\aie\dialects\aie.py` and `aiex.py` in the 1.3.4 installation.
