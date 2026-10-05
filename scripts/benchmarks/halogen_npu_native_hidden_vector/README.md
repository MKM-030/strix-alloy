# Default-off native H paired-vector sibling

This source package copies `halogen_npu_native_hidden_decoded` into a distinct
sibling. No controller, backend profile, engine hook, old source package, or
runtime route enables it. Its build and runtime require explicit owner commands.
It is source-only until root runs the focused tests, offline build and linked
review, then authorizes a finite real-input screen. Device benefit is unmeasured.

The full original H store7/variant0 projection remains [4,2560] BF16 input to
[4,2560] BF16 output, with the same sequential two-MAC sixteen-lane schedule,
eight pairs per K256 block, ten separate FP32 block adds, XOR8/4/2/1 reduction
and final BF16 RNE. The GPU dot2 instruction's internal rounding is unresolved;
this package does not claim bit-exact fused GPU dot parity. The copied exact
numeric reference and BF16 rounding helper are unchanged.

## Word-only layout

Outer streamed weights remain [column8,group5,Kchunk10,worker4]. Each8192-byte
chunk changes from [row16,K256] to [row16,pair8,component2,lane16]:

```text
Wp[row,pair,component,lane] = W[row,lane*16 + pair*2 + component]
Xp[stream,kchunk,pair,component,lane]
  = Xcanonical[stream,kchunk*256 + lane*16 + pair*2 + component]
```

The kernel loads32 contiguous BF16 words, extracts two16-lane halves, and reuses
one weight pair across four independently ordered accumulators. No scalar hot
lane gather or weight affine decode remains. Output/partial layout, reset,
finish, finite64 calls,32 workers,five groups,ten Kchunks and all DMA geometry
remain unchanged. The explicit scalar XOR-lane assembly in finish is retained.

The host accepts canonical wire/cohort bytes and keeps their digest binding.
It transposes10,240 little-endian BF16 words directly into the existing input BO
without float conversion or a uint16-alignment assumption about source bytes.
The complete timer starts before this transpose. Reports mark
`complete_includes_host_input_transpose=true`; complete statistics are named
`complete_input_transpose_poison_sync_launch_wait_output_sync_readback`.

Weight BO remains13,107,200B, input/output20,480B each, chunk8192B, aggregate32768B,
column1,638,400B, partial4096B, declared stack4096B and nominal worker45,312B.
DDR traffic remains13,291,520B/call. New four-accumulator register pressure needs
actual compiler/linked inspection. Emission verification requires all96 worker
input/weight buffers to be64-byte aligned for the contiguous512-bit loads.

## Prepared payload conversion

`pack.py` reads only an explicitly pinned prepared decoded13,107,200-byte source
and its bounded decoded weight ABI. It has no original-Q8 argument or affine
conversion import. Source format/payload/raw/decoded/inverse SHA pins must match.
It reconstructs row-major decoded words, verifies their SHA, applies the new
permutation and proves complete inverse equality before publishing new files.
The raw SHA is provenance; no original file is opened.

```powershell
& 'C:\AI\runtimes\ironenv\Scripts\python.exe' -B .\pack.py `
  --decoded-packed 'C:\pinned\decoded\weights.bin' `
  --decoded-weights-abi 'C:\pinned\decoded\weights.abi' `
  --decoded-packed-sha256 PINNED_DECODED_PAYLOAD_SHA `
  --raw-sha256 PINNED_ORIGINAL_RAW_SHA --out-dir 'C:\fresh\vector-packed'
```

Receipts retain source payload/ABI hashes, decoded row-major/inverse SHA, raw SHA,
new packed SHA, copied numeric-reference SHA and separate read/unpack/pack costs.
Design, source schedule, build, emission, artifacts and weights have unique
`halogen-native-hidden-vector-*` format tags. Sidecars explicitly bind
`weight_layout=row16,pair8,component2,lane16`,
`input_layout=stream4,Kchunk10,pair8,component2,lane16` and64-byte alignment;
design also binds canonical external wire layout. Same-sized old artifacts or
payloads are rejected by the new host.

## Owner validation

Exactly three synthetic tests cover full inverse/source reconstruction,
independent weight lane/pair coordinates plus64-byte alignment, and exhaustive
canonical input permutation including signed zero. They import no compiler,
runtime or model. Root runs them once after source review:

```powershell
& 'C:\AI\runtimes\ironenv\Scripts\python.exe' -B .\test_pack.py
```

`build.ps1 -OutDir C:\fresh\vector-build` retains the decoded build's installed
MLIR-AIE1.3.4/XRT/MSVC/Peano flags, `/Zc:__cplusplus`, no-fast-math and
ffp-contract=off; it executes only device-free `host.exe --inspect`. It preserves
source/artifact, allocation, DMA, LLVM, ELF and linker receipts. Build emission
proof does not establish MAC lowering, spills, linked stack extent, or numeric
correctness: root must inspect the new actual linked binary before hardware.

Runtime common flags and finite canonical H-only protocol remain as documented
in copied `TCP_ADAPTER.md`: persistent XRT objects and owned adapter, root-owned
outer job deadline, weights/instructions synced once, input/output sync per call,
unchanged .03/.003 frozen gate and separate exact-word mismatch counts. No default
engine integration or token-rate claim is part of this package. Full useful
comparison must include input readiness, transpose, all transport/copies/sync,
publication and the actual skipped-original-H consumer interval.

Design and source counts: `docs/research/halogen-npu-native-hidden-vector-plan-20261005.md`.
Apache-2.0 WITH LLVM-exception; copied AMD/Xilinx MLIR-AIE/AIE API/XRT attribution
and the original numerical source provenance are retained.
