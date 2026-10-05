# Original Q4C selected-row conversion and gather oracle

The small oracle directly invokes the original Halogen 0.16.2 GPU conversion
shaders and original embedding gather. Root executed the reviewed component
successfully without loading or replacing the large server. Both original
converters and their actual-ID private-table gathers exactly matched the selected
CPU reference. The executed evidence and narrow qualification are recorded below.

The host function at `0x17edf00` is a tensor loader. Its store5/variant2 branch
copies packed bytes to a device allocation and calls the dispatcher at
`0x17d2e50`; it does not expose a reusable CPU decoder. Calling that host routine
would require the engine's executable and registration/global machinery. Direct
HIP module invocation of the pinned original shaders avoids that dependency.

The fixed engine is 26,052,768 bytes with SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
Its embedded codeobject starts at byte331,776, spans17,704,408 bytes, and has SHA256
`45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83`.
The harness hashes both complete files and compares every codeobject byte with
that engine region before loading the HIP module.

The sealed checkpoint receipt selects token14367 from `embed_tokens.weight`,
store5, variant2, dimensions `[248320,2560]`, offset322,560, size357,580,864.
Only three unchanged checkpoint windows are needed:

| Plane | Original file offset | Bytes | Rebased offset | SHA256 |
| --- | ---: | ---: | ---: | --- |
| Codebook | 322560 | 64 | 0 | `1f2755c994ae6ea3d4a24a5cc2b8066de0971b07eacd76a05c5e111cba8d3679` |
| Selected codes | 18712384 | 1280 | 64 | `47b6702d51297b13cc90632f2f746d42b0c5fc97d06fcf778dbad225aac8cbcb` |
| Selected scales | 320470944 | 160 | 1344 | `79cc173820638d74f37a9340782a92e4d620b8a53cff138d17c7ebebeaafeabb` |

The resulting1504-byte one-row native pack has row count1, width2560, code
offset64, scale offset1344 and scale stride160. Original full-table extent and
offset arithmetic is recomputed by the preparer. No CPU decoding or arithmetic
transformation creates this pack.

The default aligned route when overrides are absent is
`_ZN7halogen12_GLOBAL__N_114k_deq_q4cp_v8uILi2ELb0EEEvPKhPtjjllllNS0_5DeqCbE`,
host identity `0x18d7358`, registration call `0x1851670`. The loader's null
optional codebook argument chooses the false specialization and a zero64-byte
by-value `DeqCb`. At `0x17d32fd..0x17d333f`, grid x is
`min(65535,ceil(total_blocks/(256*2)))`. At `0x17d399b`, block x remains256.
The unroll factor changes work per workgroup; it is not a512-thread block.
For a one-row width2560 pack, blocks per row and total blocks are both320, so
the launch is grid1/block256/default stream/shared0.

| Vector public argument | Offset | Bytes | One-row value |
| --- | ---: | ---: | --- |
| Packed input pointer | 0 | 8 | Harness `hipMalloc` pointer |
| BF16 output pointer | 8 | 8 | Harness `hipMalloc` pointer |
| Blocks per row | 16 | 4 | 320 |
| Total blocks | 20 | 4 | 320 |
| Original width | 24 | 8 | 2560 |
| Codes offset | 32 | 8 | 64 |
| Scales offset | 40 | 8 | 1344 |
| Scale stride | 48 | 8 | 160 |
| Optional codebook | 56 | 64 | All zero |

Retained metadata declares static LDS64, kernarg376/alignment8, wave32, and a
maximum256-thread group. HIP supplies hidden dispatch arguments through the
ordinary module API. The original scalar sibling
`_ZN7halogen12_GLOBAL__N_110k_deq_q4cpEPKhPtlllll` is also replayed with its
seven arguments and grid1/block256 to expose any selected-row vector/scalar
disagreement.

After each conversion, a device-to-device copy writes its5120-byte output into
row14367 of a real private14368-row `hipMalloc` table. That allocation is
73,564,160 bytes and the row begins at73,559,040. The original
`_ZN7halogen12_GLOBAL__N_114k_embed_gatherEPKtPKiPt` reads actual ID14367 from a
separate device ID allocation and gathers that row with grid1/block256. The
harness neither borrows the colleague server's table nor places a pointer
outside a claimed allocation. Five successful allocations have total payload
73,575,908 bytes, excluding runtime/codeobject overhead; root's process-level
reserve/admission/deadline guard remains necessary.

Every converter and gather output is retained even if exact comparison fails.
Each of2560 BF16 words must agree for converter versus the unchanged CPU row,
gather versus converter, and gather versus CPU row. The CPU row is explicitly
a reconstruction reference, SHA256
`af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374`;
it is never labelled native output before the GPU oracle supplies that evidence.
Cleanup, successful synchronization, immutable file rechecks and output export
are part of the passing receipt. No tolerance adjustment is available.

New sources are `scripts/benchmarks/halogen0162_q4c_row_oracle.c` and
`scripts/benchmarks/halogen0162_q4c_row_oracle_prepare.py`. The C source includes
the frozen RMS scaffold through a renamed entry point; that entry is never
called. Its compile-time scaffold pin must equal
`7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8`, and root's
compile envelope must separately hash the harness, included source and binary.

Prepare-only runs on Windows using sealed JSON and source text. Root-only export
runs on Linux so exact native `fstat` can match checkpoint size/device/inode and
nanosecond timestamps. Mirrored JSON paths are accepted only with their frozen
hashes. Export reads1504 checkpoint bytes plus the5120-byte CPU reference,
rechecks source/JSON/native identity, then creates fresh pack/reference/receipt
files exclusively. It does not rehash the66.7GB checkpoint; whole-checkpoint
identity is retained lineage and selected-window hashes are independently
verified.

Root extracted both original shaders from the pinned codeobject. The v8u2false
text is retained in
`server/.local/optimization9h-20261004/q4c-shader-text-f4600cd441bd44988ac17b1a12f2aaf7/shader-stdout.txt`,
SHA256 `2ff007085d2fd74b916eca7002fce8ccee2723636d540613dccb5d85cda89e55`.
The correct scalar text is retained in
`server/.local/optimization9h-20261004/q4c-scalar-text-a19d9dd422904994b59752907508c620/q4c-scalar-text-stdout.txt`,
SHA256 `63cf1d40c4d7fafc5eccd98014fdea7cd36ce2aa446425a2a107337c233cc9b7`.

Static rebasing review is complete. Vector entry `0x26b600` copies16 FP32
codebook words into LDS. For valid group `g`, row is `floor(g/320)` and column
is `8*(g%320)`. Its code load starts at
`input+code_offset+row*(width/2)+column/2` and reads4bytes; its FP16 scale load
starts at `input+scale_offset+row*stride+2*floor(column/32)` and reads2bytes.
Its BF16 store starts at `output+2*(row*width+column)` and writes16bytes. In this
selected-row dispatch, valid groups0..319 use row0, code reads stay in
`[64,1344)`, scale reads stay in `[1344,1504)`, and stores stay in `[0,5120)`.
Partial-group masks before the tail's loads and stores reject groups>=320.
The hidden-grid increment advances512groups and exits; the false specialization
does not load the optional `DeqCb`.

Scalar entry `0x219700` uses workgroup x as row and advances each lane's column
by the hidden group size256. With row0 and columns0..2559, its one-byte code
loads, two-byte FP16 scale loads, four-byte codebook lookups and two-byte BF16
stores remain inside the same bounds. It combines the FP16 scale and FP32
codebook through mix-FMA and stores BF16 RNE. The vector widens FP16 scale,
multiplies in FP32 and stores BF16 RNE. The exact runtime gate decides whether
any scalar/vector rounding or signed-zero difference exists.

Host launch and ABI were independently source-audited by a peer. Root later
compiled with GCC `-Werror` and executed the completed window recorded below.
Python AST and source whitespace checks passed. No checkpoint/engine/codeobject/
tensor payload, compiler, provider, GPU, NPU or server operation was executed by
this preparation agent. Root's
first prepare-only attempt exposed the known Windows `lstat`/`fstat` ctime
disagreement. The metadata reader now binds shared size/device/inode/mtime/birth
time while checking pathname ctime and handle ctime stability separately. The
Linux native checkpoint size/device/inode/mtime/ctime identity gate is unchanged.

The passing run qualifies this selected row's original conversion and actual
gather from the harness's own allocation. It does not prove original full-table
loader provenance, the colleague server's live allocation, other vocabulary
rows, full-D/head parity, acceptance, or a speed benefit.

Root executed the GPU component on 2026-10-05 in the original pinned image
`ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a`.
The owned window is retained at
`server/.local/optimization9h-20261004/q4c-row-owned-44352a0fc0df41a1922d7800403a90f0`.
Its outer `result.json` SHA256 is
`83f4d91641fbeb85020632d07866baf1fc3105c12863d728ac1f8029bfc29f32`;
the bound native `result/replay/replay.json` SHA256 is
`8fc12102cacb42989120b73b92bcc536e3b3a477bcabbb96b3d83265b6e8b40d`.
Independent text/JSON review confirmed the receipt binding, passing flags,
exact comparisons, counters, allocation extent, cleanup and false broader claims.
This reviewer did not open the four output payloads; root independently verified
their complete 5120-byte hashes.

| Executed boundary | Recorded result |
| --- | --- |
| Original v8u2false conversion | All 2560 BF16 words exactly match the pinned CPU reference |
| Original gather after v8u2false conversion | Actual ID 14367; exact match to converter and reference |
| Original scalar conversion | All 2560 BF16 words exactly match the pinned CPU reference |
| Original gather after scalar conversion | Actual ID 14367; exact match to converter and reference |
| Retained output files | `vector-converted.u16`, `vector-gathered.u16`, `scalar-converted.u16`, `scalar-gathered.u16` |
| SHA256 of each 5120-byte output | `af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374` |
| Native operations | Four attempted/successful launches, four successful synchronizations, 12 copies, five allocations/frees, one table memset, one module load/unload |
| Numerical result | Zero converter/reference, gather/converter, gather/reference or nonfinite-word failures in both modes |
| Native cleanup | Zero HIP cleanup or file-close errors; all immutable files rechecked; four outputs written |
| Outer cleanup | Owned container removed; owned job and read-only controller handle closed; monitors stopped; ownership latch released; no cleanup pending |
| Host reserve | Minimum physical 27.016361 GiB; commit headroom 119.605923 GiB; 22 GiB admission and 18 GiB continuous floor |
| Original colleague | Ready/idle controller PID 24904 and original CID preserved; health completed 4/cancelled 0 unchanged |

The source and artifact pins for this completed window are:

| Binding | SHA256 |
| --- | --- |
| C harness | `f09f3d1e54adcf08c809ca175f8cb59a76b346df585887fe784fad0432de5d95` |
| Preparer | `bf168a9c4960496c6820bd575a7266df7a17eab49897543c5926650637e83a21` |
| Reviewed launcher | `39606732a8fc226711f1337a5daac2a83669bbc09d46c75282790fad3c1af4d2` |
| Compiled binary | `05d5290aecc7ba149b0643a6f384ab4b0465d1b11e11d550bd66177a9bb10c69` |
| Frozen config | `2e0e52c830d3ae1e7df83365e7800e30f31ab772d3a9793859d01bae2cf75225` |
| Metadata plan | `5814aced81640b368bddbb3b66143abd7974f226012d162bb1c47a48149494bf` |
| Native export receipt | `078cfe341edbc8f07bb97ee1ef30796e953d91ab86f2ce31b22bd260f2b35cbc` |
| Unchanged 1504-byte native pack | `846e0416dee1d61ec954039f22e249d13254555a9a55a37e95f03f410a64a368` |
| Installed stock HIP runtime | `6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5` |

This is GPU component evidence for the single selected checkpoint row in the
rebased native layout and its original gather from a private allocation. Original
full-table loader qualification, live model allocation qualification, parity for
other rows, full-D/head qualification, acceptance and speed claims remain false.
No NPU was used in this window, and no end-to-end performance benefit was measured.
