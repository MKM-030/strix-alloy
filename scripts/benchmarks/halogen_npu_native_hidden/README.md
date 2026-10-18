# Native streamed Halogen H projection

This package computes the complete H store7/variant0 `[2560,2560]` Q8 projection
of one already normalized BF16 `[4,2560]` input. It does not normalize the four
streams independently. E, seed addition, head and serving lifecycle remain with
the original engine. Source is handed to the root owner for offline compilation,
map/numeric review and guarded component execution. This handoff does not claim
a native build, hardware correctness, acceleration or token throughput.

`kernels.cc` performs real arithmetic. `exact_decode.h` forms the exact signed
integer sum of `u8_code * finite_FP16_scale + finite_FP16_bias`, rounds once to
FP32 RNE, then to BF16 RNE. This reproduces the specified FP32 affine FMA result:
the finite half product with an unsigned8-bit code fits FP32 exactly. The integer
decoder avoids relying on scalar FP32 emulation or a target FMA runtime helper.
It preserves the FP32 rounding boundary; directly rounding the exact affine sum
to BF16 would have a different double-rounding contract. Nonfinite original
metadata is rejected before device construction. Decoder values stay FP32 normal.

Each output uses16 persistent FP32 lanes. A K256 chunk gives each lane one
contiguous16-value block; the block starts at zero and chains eight pairs of two
native BF16 elementwise MACs. Ten block results are separately added to each lane.
The final reduction performs FP32 XOR8,4,2,1 additions and BF16 RNE. This is the
explicit sequential pair candidate; it does not assert equivalence to a fused
GPU two-product dot instruction. The independent exact CPU diagnosis reproduces
both retained original-GPU A/B fixtures exactly with this schedule, but those
fixtures do not distinguish the internal pair rounding modes. AIE instruction
rounding/subnormal behavior and actual output still require native validation.
There is no BFP conversion or silent scalar substitution for native BF16 MAC.

`generate.py` emits the entire8-column NPU2 array, four compute workers per
column, each processing five16-row output tiles. Every worker receives50 packed
K256 chunks per call. Every core is finite64 calls. A single XRT launch streams
all weights; no chunk launch or repeated-batch timing divisor is used.

`pack.py` changes only byte order. Original rows contain2560 unsigned codes then
40 little-endian FP16 scale/bias pairs,2720B per row. Packed order is
`[column8,output_group5,K_chunk10,worker4,bytes4352]`. Each4352B chunk contains
4096 code bytes in `[row16,K256]` order and256 original metadata bytes in
`[row16,group4,scale/bias]` order. Tile index is `column*20+group*4+worker`.
The packer proves complete inverse bit equality and matching SHA256 before
publishing to a fresh directory. The original file remains unchanged. Its
standard-library tests use synthetic bytes and do not import compiler/device code.

Per call, DDR traffic is6,963,200B weights +163,840B input (eight whole copies)
+20,480B output =7,147,520B. Four worker outputs per column are joined in
`[group5,worker4,stream4,row16]` stream order and scattered directly to canonical
`[stream4,outrow2560]` output with sizes `[5,4,4,16]`, strides `[64,16,2560,1]`
and base `column*320`. Input FIFO depth is one on each worker, weight/output depth
two. Nominal worker allocation is45,824B: input20,480, weights8,704, output256,
FP32 lane scratch4,096, decoded BF16 scratch8,192, stack4,096. Nominal linked
memory-tile payload is56,320B. Compiler bookkeeping, bank alignment, linked code
and actual stack use require the retained allocation/linker evidence.

## Offline build

Use the existing VsDevCmd/x64 Native Tools PowerShell environment:

```powershell
& 'C:\Users\Marcel\.codex\worktrees\npu-ready-embedding\strix-alloy-clean\scripts\benchmarks\halogen_npu_native_hidden\build.ps1' -OutDir 'C:\path\to\fresh\native-hidden-build'
```

The script builds persistent MSVC host, owned Windows TCP adapter, full generator and Peano native kernel;
emits LLVM arithmetic source; compiles complete MLIR to xclbin/instructions;
retains all32 core ELFs/LLVM/linker scripts and address/DMA lowering; validates
actual source/physical DMA layouts, all24 completion drains, all24 lowered BO
patches/syncs and mapped buffer bounds/non-overlap; writes source/artifact hashes.
It executes `host.exe --inspect` solely for offline xclbin metadata parsing, with no
`xrt::device` construction; neither executable enters its runtime mode during the
build. `/Zc:__cplusplus` is necessary for installed XRT.
Installed MLIR-AIE1.3.4 uses `--aie-generate-xclbin` and
`--aie-generate-npu-insts`; the deprecated get flags are not used. Builds must
retain the generated source and receipts even on failure. It does not install
tools, read model weights, launch projection, or change the serving process.

`emission-receipt.json` proves declared allocation and DMA checks and inventories
actual linked files. It expressly marks linked stack-use review and native
numeric validation pending. Root must inspect `kernels.ll` and linked code for
native BF16 FP32 MAC/add lowering, stack consumption and lack of unexpected
helpers, and inspect instruction enable/configuration semantics before execution.
`artifacts.abi` binds xclbin/instructions/design ABI; pin its SHA256 in runtime CLI.

## Original H packing, when authorized by root

```powershell
& 'C:\AI\runtimes\ironenv\Scripts\python.exe' -B .\pack.py --raw 'C:\pinned\original-H.q8' --raw-sha256 PINNED_ORIGINAL_HASH --out-dir 'C:\fresh\H-packed'
```

Output is `weights.bin`, strict `weights.abi`, and full `pack-receipt.json` with
original, packed and inverse hashes plus packing/validation duration. Host checks
the packed hash, all finite FP16 metadata and original/inverse sidecar pins before
constructing a device. Root should independently verify pack receipts and avoid
including initialization/packing in steady-state samples without labeling it.

## Persistent host ABI and modes

`MLIR_AIE` live args are opcode64=3 at0x00, instruction BO at0x08, uint32
instruction **word** count at0x10, weights BO3 at0x14, input BO4 at0x1c, output
BO5 at0x24. Compiler bo3/bo4 padding is accepted only with exact sizes/offsets and
left unbound. The runtime sequence declares exactly three buffers. One device,
registered xclbin, context, kernel, four BOs and one bound `xrt::run` persist.
Weight and instruction BOs are synchronized once; input and poisoned output are
synchronized every call. Any failed/incomplete launch burns its call and latches.

Common runtime arguments (only inside the root-owned external process deadline):

```text
--xclbin design.xclbin --instructions insts.bin --abi design.abi
--artifacts artifacts.abi --artifacts-sha256 PINNED_BUILD_MANIFEST_HASH
--weights weights.bin --weights-abi weights.abi
--packed-sha256 PINNED_PACKED_HASH --raw-sha256 PINNED_ORIGINAL_HASH
--wait-ms 2000 --deadline-ms 80000
```

In `--cohort` mode, add `--cohort-inputs FILE --cohort-oracles FILE --report FILE`
and optionally `--warmups 8 --measurements 48`. Each file contains exactly
`warmups+measurements` canonical20480B BF16 vectors, with input hashes distinct
across all calls and original GPU oracle outputs paired by index. All calls are
verified finite. NPU rtol=.03/atol=.003 is frozen; exact-word mismatches are
reported separately. Numeric failure immediately stops further launches and
returns exit2. Report retains every launch/wait and complete copy, poison, sync,
launch, sync/readback sample. Oracle checks lie outside those intervals.

In `--serve` mode add CLI-pinned `--process-id`, `--nonce`16B hex, `--epoch`16B
hex, `--model-binding`32B hex, `--graph-binding`32B hex and `--engine-sha256`32B
hex. stdin/stdout must be inherited binary pipes. It uses the sibling shared
`../halogen_mtp_h_wire.h`: HELLO/READY framing, original engine SHA, exact
sequence0..63, full header/input/request SHA validation and complete validated
response framing. It pins the first nonzero opaque model pointer and rejects
changes. It assembles the entire response before writing, uses stdout only for
wire data, reports diagnostics/timing to stderr, and closes/latches on failure.
It admits a clean shorter cohort only when stdin closes before any byte of the
next REQUEST frame and reports the actual completed reply count0..64. Partial
header/payload EOF always fails. After reply63, it stays resident until root
closes stdin so the full head can finish with transport liveness intact; any
extra byte fails the finite session. `native_tcp_adapter.exe` provides the owned
privateIPv4 TCP listener/proxy to these pipes; see `TCP_ADAPTER.md`. Root owns
its guarded invocation and the Linux engine bridge.

The one resident watchdog cancels main-thread synchronous Windows pipe I/O at
the whole-process deadline. `run.wait()` is bounded and incomplete work aborts
only the owned run. XRT initialization, sync, masked waits, abort and destruction
can block; root's independent external process/job deadline is mandatory. Bounds
inside this executable do not claim to replace it. No error reply is emitted.

Scalar exact decode and per-lane gathers may dominate runtime. Measure this full
streamed component before pursuing the live bridge. Useful end-to-end timings
must also include both transport directions, HIP readiness/readback/publication
and the full owned head cohort. Component microseconds are not token rates.

## License and attribution

Apache-2.0 WITH LLVM-exception; `LICENSE.txt` is copied from the prior native
dispatch package's MLIR-AIE license. Dataflow/XRT patterns follow locally
installed AMD/Xilinx MLIR-AIE1.3.4 and AIE API headers. References:
[MLIR-AIE](https://github.com/Xilinx/mlir-aie),
[AIE API](https://github.com/Xilinx/aie_api), [XRT](https://github.com/Xilinx/XRT).
No model payload was used to construct this package.
