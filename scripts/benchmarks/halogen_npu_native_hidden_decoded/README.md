# Native H with weights decoded once during initialization

This is a distinct sibling of `halogen_npu_native_hidden`. It computes the full
original H store7/variant0 `[2560,2560]` projection of the unchanged normalized
BF16 `[4,2560]` input and emits the actual canonical BF16 `[4,2560]` output.
It preserves the original16-lane schedule: reset one16-value block per lane,
eight sequential pairs of native BF16 FP32 MACs, ten FP32 block additions to
persistent lanes, XOR8,4,2,1 reduction and final BF16 RNE. The protocol remains
the shared H-only finite up-to64 request/response protocol. E, normalization,
seed addition, head and serving lifecycle remain owned by the original engine.

The change moves the6,553,600 weight affine conversions out of every projection
and into initialization. `pack.py` reads only an explicit, SHA-pinned original
H matrix of exactly6,963,200B, checking the size before opening and limiting its
read to that size plus one byte. `numeric_reference.py` is an unchanged copy of
the reviewed offline numerical reference. Its `decode_q8_numpy` treats each
finite FP16 as an integer multiple of2^-24, computes the exact signed affine
numerator in int64, represents its fewer-than49 bits exactly in FP64, then rounds
to FP32 RNE and BF16 RNE, including signed zero. This matches the original affine
FP32 FMA then BF16 contract. It does not fit weights or use input/oracle fixtures.

The resulting6,553,600 BF16 words occupy13,107,200B. They are losslessly rearranged
into `[column8,output_group5,K_chunk10,worker4,row16,K256]` order. Every chunk is
8192B, every four-worker aggregate32768B, and every column1638400B. Tile index is
`column*20+output_group*4+worker`. Complete inverse reconstruction must equal the
decoded row-major matrix bit for bit before publication. The receipts retain the
original raw SHA, decoded row-major SHA, packed SHA, inverse decoded SHA, copied
reference source SHA, and separate one-time decode/packing durations. They do
not claim that original Q8 code/metadata bytes can be recovered from BF16 words.
The original file remains unchanged.

`kernels.cc` has no weight decoder call and no decoded scratch buffer. It reads
streamed BF16 weight words directly. All32 workers still process five16-row tiles
and ten K256 chunks per tile using one XRT launch per complete H projection.
The full8-column NPU2 dataflow queues all output DMA first, then eight whole input
copies, then streamed weights, and drains all24 completion tokens before reuse.
Weight split offsets are BF16 **word** offsets `[0,4096,8192,12288]`. Host weight
column offsets are `column*819200` words, with DMA sizes `[1,1,50,16384]` and
strides `[0,0,16384,1]`. The output join/scatter remains
`[group5,worker4,stream4,row16]` to canonical `[stream,outrow]`, sizes
`[5,4,4,16]`, strides `[64,16,2560,1]`, base `column*320` output words.

Nominal worker storage is45,312B: one20480B input, two8192B weight objects,
two128B output objects,4096B partial lanes and4096B stack. The former8192B decode
scratch is absent. Nominal linked memtile payload is87,040B. Per-call DDR traffic
is13,107,200B weights +163,840B input +20,480B output =13,291,520B. This increases
weight traffic while eliminating repeated scalar decode work; it makes no claim
of acceleration until a guarded real-H component measurement establishes it.

## Build and preparation

The existing x64 Native Tools PowerShell environment can build into a fresh folder:

```powershell
& 'C:\Users\Marcel\.codex\worktrees\npu-ready-embedding\strix-alloy-clean\scripts\benchmarks\halogen_npu_native_hidden_decoded\build.ps1' -OutDir 'C:\fresh\native-hidden-decoded-build'
```

The script compiles native XRT host, owned TCP adapter, complete generator and
native Peano BF16 kernel; emits LLVM source; links all32 cores; retains all
allocation/DMA/LLVM/ELF/linker evidence and hashes. `/Zc:__cplusplus` is retained
for installed XRT. It uses installed MLIR-AIE1.3.4 compile flags. It executes
`host.exe --inspect` only to parse artifact metadata, without constructing an
XRT device; runtime modes and adapter are not launched during the build.
No installation, model read or serving lifecycle change is part of the build.

`verify_emission.py` checks exact emitted DMA traversal (allowing only compiler
folding of contiguous dimensions), all completion drains/BO patches/syncs,
actual mapped buffer bounds/non-overlap, one whole input and exactly two BF16
weight objects per worker, absence of decode scratch and declared4096B stack.
It uses the installed target model's512KiB memtile/64KiB compute limits. Actual
linked stack use, native BF16 MAC/add rounding and real numeric correctness still
require root review. Earlier variant stack evidence must not stand in for this
new linked binary. Distinct ABI/artifact formats reject accidental original-Q8
artifacts or weight BOs in this variant.

Only after root authorizes reading the named original H extract:

```powershell
& 'C:\AI\runtimes\ironenv\Scripts\python.exe' -B .\pack.py --raw 'C:\pinned\original-H.q8' --raw-sha256 PINNED_ORIGINAL_HASH --out-dir 'C:\fresh\H-decoded-packed'
```

Outputs are `weights.bin`, `weights.abi` and `pack-receipt.json`. Decode happens
exactly once per preparation and is excluded from steady-state projection timing;
its cost is reported separately. No preparation or payload reads were performed
by the author of this source package. The synthetic tests validate full decoded
inverse packing, edge worker/row/K layouts and invalid geometry/type/nonfinite
rejection without compiler/runtime imports or original model data.

## Persistent runtime

Live `MLIR_AIE` arguments remain opcode64=3 at0x00, instruction BO at0x08, uint32
instruction **word** count at0x10, weight BO3 at0x14, input BO4 at0x1c and output
BO5 at0x24. Only exact bo3/bo4 compiler padding is accepted and left unbound.
The weight BO is now13,107,200B; input and output remain20,480B each. One device,
registered xclbin, context, kernel, four BOs and one bound `xrt::run` persist.
Weight/instruction sync occurs once. Every projection copies/syncs input and
poisoned output, starts/waits one run, syncs/reads back all output, and checks
finite BF16. Failed launches burn their call and latch. There is no chunk launch
or per-request process.

Common arguments inside the mandatory root-owned outer process/job deadline:

```text
--xclbin design.xclbin --instructions insts.bin --abi design.abi
--artifacts artifacts.abi --artifacts-sha256 PINNED_DECODED_BUILD_MANIFEST_HASH
--weights weights.bin --weights-abi weights.abi
--packed-sha256 PINNED_BF16_PACKED_HASH --raw-sha256 PINNED_ORIGINAL_7MB_HASH
--wait-ms 2000 --deadline-ms 80000
```

`--cohort` accepts exact paired input/oracle files of20,480B per call and requires
distinct input hashes. Add `--cohort-inputs FILE --cohort-oracles FILE --report FILE`
and optional `--warmups 8 --measurements 48`, total at most64. It retains every
complete transfer/launch/readback sample and checks frozen NPU rtol=.03/atol=.003;
exact word mismatches are counted separately. Failure stops subsequent launches.
Original GPU outputs are the oracle. CPU .002/.0002 gates are unchanged in the
copied numerical reference. No tolerance is widened in this variant.

`--serve` uses binary inherited stdin/stdout, sibling `../halogen_mtp_h_wire.h`,
CLI-pinned process/nonce/epoch/model/graph/original-engine SHA, exact sequence0..63,
full input/request/response binding hashes and first-request opaque model-pointer
pinning. Short cohorts close cleanly only before any byte of a next frame; partial
EOF fails. After reply63 the host remains resident until owner closes stdin.
Diagnostics are stderr only. The copied owned Windows TCP adapter provides
private IPv4/TCP_NODELAY and bounded overlapped-pipe forwarding; details are in
`TCP_ADAPTER.md`. It creates one suspended child atomically assigned to its own
kill-on-close job before exactly-once resume. No Python relay is on the hot path.

Bounded waits/watchdog cancellation do not replace the root's independent outer
deadline: XRT setup, sync, abort, teardown and process APIs can block. All useful
live-path timing must include both pipe/socket directions, HIP readiness,
readback/publication and the full head owner interval. Component microseconds
are not token rates. This package is source only until root builds/reviews it.

Apache-2.0 WITH LLVM-exception; copied setup/dataflow attribution follows the
original native package's AMD/Xilinx MLIR-AIE/AIE API/XRT references and license.
