# NPU route: driver, SRAM, compact drafting and pixel representation

5 October 2026. The useful concept is a persistent native NPU component with a
small working set, or a compact token proposer whose output the original target
verifies. Tiny native fixtures, exact offline references and two-call real-H
tolerance screens now exist; steady-state acceleration and engine speedup remain
unqualified. Original-server restoration is separately evidenced below.

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
per complete projection. Both variants completed two distinct frozen A/B calls,
zero warmups: means **24.18505 ms packed / 3.5138 ms decoded**. Both pass unchanged
NPU rtol=0.03 / atol=0.003 with one BF16 word mismatch; this is not exact parity,
steady-state qualification or engine gain. Runtime initialization is separate:
33.7685 ms packed / 505.8045 ms decoded. [Initial comparison](halogen-npu-native-hidden-comparison-20261005.md).
The decoded variant removes **6,553,600 scalar affine conversions per call** by
decoding once during preparation. DDR traffic grows from 7,147,520 to
13,291,520 B, an extra **6.144 MB decimal per call**. Its separate build, placement
and all 32 linked-stack reviews pass; prepared BF16 weights round-trip exactly.
The native tolerance evidence remains bounded to the two frozen inputs.
[Original design](halogen-npu-native-hidden-next-design-20261005.md),
[decoded source package](../../scripts/benchmarks/halogen_npu_native_hidden_decoded/README.md).

The repaired offline reference now matches all 20,480 frozen original-GPU A/B
BF16 words exactly. That supersedes the earlier CPU misses on those fixtures;
it does not prove native exact AIE parity, complete-head correctness or avoided
GPU work. Later native tolerance passes are separate. [Numeric evidence](halogen-npu-hidden-numeric-20261005.md).

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

The guarded frozen real-H screens supply initial component evidence. A useful
complete replacement consumer measurement and
subsequent unchanged-output/acceptance engine A/B are required for acceleration.
Engine restoration remains a separate lifecycle task with unchanged v2 startup
floors of 44 GiB physical / 131 GiB commit and 18 GiB live reserves; this concept
does not relax recovery or establish engine acceleration.
Failed restoration receipts from 5 October 2026 remain retained. Original GPU
serving was restored ready/idle at 21:11:36 UTC. [Final-ready receipt](../../server/.local/optimization9h-20261004/native-hidden-held-restoration-v2-f346f01978f748b8a47457e7cda58889/final-ready.json).
[Admission source](../../backends/halogen-wsl2-0.16.2/scripts/memory_budget.py),
[runtime guard](../../backends/halogen-wsl2-0.16.2/scripts/service.py).

The subsequent [default-off contiguous-vector sibling](halogen-npu-native-hidden-vector-20261005.md)
now implements the lossless lane/pair layout and host input transpose. Its fresh
offline gates and two-input frozen tolerance screen passed; complete costs were
2.9699/.3556 ms including the transpose, with zero warmups and one BF16 word
mismatch. Its own report retains the later lifecycle receipts. These initial
separate-session observations do not establish a steady-state speed ratio or
change the live consumer, full-head/acceptance or engine qualification gates.
Original GPU serving was restored again ready/idle at 21:34:46 UTC after that
screen, with a separate authenticated check at 21:35:53 UTC. The
[consumer cost decision](halogen-npu-native-hidden-vector-decision-20261005.md)
keeps the current H replacement default-off and recommends no live cohort until
a distinct mechanism provides a plausible useful-cost advantage.
