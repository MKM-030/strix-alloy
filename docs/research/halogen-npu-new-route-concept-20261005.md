# NPU route: driver, SRAM, compact drafting and pixel representation

5 October 2026. The useful concept is a persistent native NPU component with a
small working set, or a compact token proposer whose output the original target
verifies. The current evidence establishes a tiny native fixture and exact
offline references; it does not establish real-H acceleration, engine speedup or
current server readiness. No hardware or system change is part of this note.

## Driver and native Windows/WSL roles

The installed Windows NPU driver already supports the demonstrated route:
MLIR-AIE compiles a finite AIE program, and a native Windows XRT host retains the
device/context/kernel/run and buffer objects, then synchronizes buffers and
submits work. This is direct compiled NPU execution through the existing driver;
it needs neither an ONNX graph nor a replacement driver. Reusing those objects
removes repeated setup, while synchronization, transport and teardown remain
real costs. [AMD native Windows guide](https://xilinx.github.io/mlir-aie/dev/buildHostWinNative/),
[XRT native APIs](https://xilinx.github.io/XRT/master/html/xrt_native_apis.html).

WSL can be the compiler environment while Windows owns NPU execution. That does
not establish an NPU device inside this WSL guest or a Windows-XRT/WSL-HIP buffer
import and fence contract. Native Linux with amdxdna/XRT is a separate platform
qualification, not a switch already proved for this Windows/WSL server. The
current H transport copies data across that boundary; shared DDR would still
use existing system memory rather than create more capacity.
[WSL compilation with a Windows host](https://xilinx.github.io/mlir-aie/dev/buildHostWin/),
[AMD Linux driver/runtime](https://github.com/amd/xdna-driver),
[retained route evidence](halogen-npu-native-route-20261005.md).

## What SRAM contributes

The full NPU2 target has 4 MiB raw distributed L2 and 2 MiB distributed L1 data
SRAM. Allocation is per tile/bank, with stacks, FIFOs and program needs; these
totals are not one free contiguous 6 MiB buffer. SRAM can retain a small matrix
or stage input/weight tiles and partial sums while DDR streams the rest.
[MLIR-AIE devices](https://xilinx.github.io/mlir-aie/dev/Devices/),
[core data memory](https://xilinx.github.io/mlir-aie/dev/programming_guide/core_data_memory/),
[MLIR-AIE NPU2 memory architecture](https://github.com/Xilinx/mlir-aie/blob/main/skills/aie-code-creator/references/architecture.md).

The measured 32-KiB integer fixture retained its local weights within one finite
active design. Its persistent complete GEMV mean was **77.183 microseconds**,
including copy/synchronization/launch/readback; it is not original-H latency or
tokens/s, nor persistence across context eviction. A complete H packed matrix
is 6,963,200 B and its decoded BF16 matrix is 13,107,200 B, so neither fits all
raw SRAM before other allocations. [Fixture and residency evidence](halogen-npu-native-route-20261005.md).

The packaged real-H prototype uses 32 workers, streamed weights and one launch
per complete projection; it remains unmeasured. Its distinct decoded source
variant removes **6,553,600 scalar affine conversions per call** by decoding
once during preparation. Weight traffic grows from 6,963,200 to 13,107,200 B;
specified total DDR traffic grows from 7,147,520 to 13,291,520 B, an extra
**6.144 MB decimal per call**. This trades decoder work for bandwidth; no speed
claim follows. Its separate build and placement checks now pass; all 32 linked
stack paths are bounded at 128 B, and all 6,553,600 prepared BF16 weight words
round-trip exactly. Native numeric and latency review are still outstanding.
[Original design](halogen-npu-native-hidden-next-design-20261005.md),
[decoded source package](../../scripts/benchmarks/halogen_npu_native_hidden_decoded/README.md).

The repaired offline reference now matches all 20,480 frozen original-GPU A/B
BF16 words exactly. That supersedes the earlier CPU misses on those fixtures;
it does not prove native AIE arithmetic, complete-head correctness or avoided
GPU work. [Numeric evidence](halogen-npu-hidden-numeric-20261005.md).

## A compact model can learn proposals

A separate small sequence model or bounded n-gram predictor could learn
conditional token proposals from target-confirmed sequences. It can be trained
or updated independently and use compact weights; whether it fits useful SRAM
tiles and beats verification/transport cost must be measured. Proposed tokens
are committed only after original-target verification. Greedy decoding needs
consecutive target-argmax agreement; sampling needs the correct acceptance and
probability correction, not a confidence threshold.
[Speculative decoding algorithm](https://proceedings.mlr.press/v202/leviathan23a.html).

The inspected Halogen 0.16.2 documented surface exposes builtin MTP/prompt lookup
but no external draft-block, accepted-prefix and target-state rollback
transaction. A fast proposer alone therefore cannot be inserted as a qualified
drafter. The missing transaction must be implemented and verified before
end-to-end acceptance-matched speed testing; repeated ordinary HTTP prefix
queries do not supply it. [Pinned Halogen flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md),
[integration audit](halogen-mtp-public-integration-feasibility-20261004.md).

## Learned PLE weights as pixels

The **47.684-GiB** `layers.1.ple.ngram_embedding.weight` is a learned FP8 feature
table: 320,001,536 rows of 160 bytes plus one global scale. It is separate from
exact prompt-prefix lookup, which proposes copies of tokens already in the
request context. PLE row bytes are trained features, not a dictionary of exact
next-token answers. [HGN FP8 table format](https://raw.githubusercontent.com/jtsylve/hgn-spec/main/STORAGE.md#fp8g-fp8-table-with-a-global-scale),
[Halogen prompt lookup](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md).

One byte can be represented as one grayscale pixel and reconstructed exactly
with a lossless codec and preserved indexing/scale. The image arrangement itself
saves no information; hashed row order gives no established spatial image
structure. Lossy pixels, sharpening or a neural image decoder discard or predict
values. They cannot guarantee recovery of arbitrary original trained weights
unless exact residual information is retained. An approximate learned decoder
would be a new model requiring quality qualification, not an exact replacement.

The retained byte-aligned indexed Huffman experiment round-tripped all **8,192
sampled rows** exactly and saved **13.240926% net**, including row offsets,
checksums, code lengths and global scale. It missed the selected 20% exact
saving screen. This sample does not establish whole-table compression, native
decoder speed or live random-row benefit. Pixel packing should face the same
exact reconstruction, index overhead and complete lookup-cost measurements.
[Sample results](halogen-npu-native-route-20261005.json),
[compression interpretation](halogen-npu-native-route-20261005.md).

Review the complete replacement hook, wire and arithmetic contract before a
guarded real-H component window. A useful complete consumer measurement and
subsequent unchanged-output/acceptance engine A/B are required for acceleration.
Engine restoration remains a separate lifecycle task with unchanged v2 startup
floors of 44 GiB physical / 131 GiB commit and 18 GiB live reserves; this concept
does not relax recovery or certify readiness.
[Admission source](../../backends/halogen-wsl2-0.16.2/scripts/memory_budget.py),
[runtime guard](../../backends/halogen-wsl2-0.16.2/scripts/service.py).
