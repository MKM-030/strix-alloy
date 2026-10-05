# Bounded original Q4C and embedding RMS arithmetic oracle

The new sibling extends the producer's two native arithmetic checks to an exact
explicit list of 1..64 original token IDs. It uses the retained original vector
and scalar Q4C shaders on the producer's rebased selected-row pack, then invokes
the retained original count1 RMS shader on every native vector output row.
It adds no table allocation, gather, model loader, FC, NPU or live integration.
The original one-row oracle, preparer, controller and frozen RMS scaffold remain
unchanged. Historical receipts and their qualification flags remain unchanged.

Root subsequently built and executed the exact64-row component. Both original
Q4C converters matched all64 sealed raw BF16 rows exactly. The combined accuracy
window failed its exact RMS gate: token28651, row index7, differed in two BF16
words, with first mismatch at column1193. The other63 normalized rows matched
exactly. This qualifies the selected64 rows' raw conversion boundary only;
the combined window and its all64 RMS gate remain failed. No exact-parity
receipt or qualification flag is rewritten.

The new sources are
`scripts/benchmarks/halogen0162_q4c_multirow_oracle.c` and
`scripts/benchmarks/halogen0162_q4c_multirow_oracle_prepare.py`.
Their source hashes at handoff are:

| Source | SHA256 |
| --- | --- |
| Multirow C harness | `d1da5ea77fc4ed66f05a1fa03f34aaa1607f8c944a5e0da3b4e8b2a9278cab56` |
| Metadata-only preparer | `e32c9b4c3612fc25827ead683765160167b84371f6c7241fa3723162da0bcbd9` |
| Included frozen RMS scaffold | `7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8` |
| Existing producer source | `56ebe190cdbdc47a50b6c6930172cb6cf274f04995276100c4c8537325ee1da5` |
| Unchanged existing one-row C harness | `f09f3d1e54adcf08c809ca175f8cb59a76b346df585887fe784fad0432de5d95` |
| Root-reviewed multirow owned runner | `0e37acb63a8f8378b65d3baf2f539b16ea32181e1653df33e81f4a17c9cbc9f5` |
| Separate CPU tree diagnostic | `ff635c3f295a7044dd388aa9699146c3f752e74c393fcc2dea7af1d02a479185` |
| Explicit portable CPU tree helper | `4ed6f25305c0ef714a85af2977a094b936b433d0912b781dbc46fab7e2e8f02a` |
| Thin offline native-tree RMS adapter | `1c15e38755af53f107c40863f17251197118c404e6ead6aa470d911b06e5caa6` |

This preparation agent read source and ordinary research text, parsed the new
Python source with `ast.parse`, checked new-source trailing whitespace and
rehash-bound the listed sources. It executed no preparer, payload read,
compiler, provider, device, server or process-control work. Compilation and
numerical validation are unverified at this handoff and belong to root.
That statement records the initial source-only handoff; the later root execution
is recorded below. The preparation agent's subsequent investigation read JSON
receipts, source and retained shader text only, with no tensor payload reads,
native/provider window, new tests or sealed-producer modification.

## Metadata contract and binary ABI

Root supplies the preparer, harness, producer, producer-plan and `complete.json`
hashes plus an explicit original token list. The preparer reuses the pinned
producer's metadata-only validation against the four original JSON receipts.
It checks the plan/completion generation and sequence, exact token order,
selected original-window metadata and observed hashes, candidate file names,
extents, references and false broader gates. It opens no candidate tensor or
checkpoint file. Root must still bind the completed fixture directory and its
sealed receipt to the owned runtime envelope.

An exclusive fresh directory receives `oracle-manifest.bin` and
`oracle-plan.json`. The binary uses explicit little-endian integer serialization;
it is never a dump of a native C structure. It has exactly `200 + 132*N` bytes,
so its maximum is 8648 bytes.

| Header field | Offset | Bytes |
| --- | ---: | ---: |
| Magic `HGMROW1` followed by NUL | 0 | 8 |
| Selected row count, unsigned32 | 8 | 4 |
| Width2560, unsigned32 | 12 | 4 |
| Nonzero generation bytes | 16 | 16 |
| Sequence, unsigned64, at most `INT64_MAX` | 32 | 8 |
| Completion receipt SHA256 bytes | 40 | 32 |
| Producer plan SHA256 bytes | 72 | 32 |
| Producer source SHA256 bytes | 104 | 32 |
| Selected native pack SHA256 bytes | 136 | 32 |
| Original token-order file SHA256 bytes | 168 | 32 |

Each132-byte row record starts at `200+132*index`. It contains original token
unsigned32 at0, then raw reference, normalized reference, selected code window
and selected scale window SHA256 bytes at4/36/68/100. Tokens must be unique,
in `[0,248320)` and match `tokens.i32` exactly. Candidate reference paths are
generated from the sealed index/token as `%03zu-token%u-raw.u16` and
`%03zu-token%u-norm.u16`; arbitrary path records are not accepted.

The native harness additionally checks the unchanged codebook and raw gamma
against their original independent pins. It verifies each selected code/scale
window inside the rebased pack against the sealed producer window record.
Original file-offset and native checkpoint identity lineage remain in the
separately root-sealed producer plan/completion receipts. The harness does not
open or rehash the checkpoint.

## Original launches and bounded memory

For `N` selected rows, the pack remains
`[codebook64][N*codes1280][N*scales160]`, with width2560, code offset64,
scale offset `64+1280*N` and scale stride160. No tensor arithmetic is performed
by the native host source.

The original scalar Q4C shader runs first, with row countN and gridN/block256.
The original default aligned `k_deq_q4cp_v8u<2,false>` runs second, with
blocks-per-row320, total-blocks `320*N`, grid `ceil(320*N/512)` and block256.
Its optional64-byte codebook argument is zero, matching the frozen one-row
route. Public argument types and offsets are unchanged. HIP supplies hidden ABI
arguments through the ordinary module API. Both full converter outputs are
copied back and compared word for word with each sealed CPU raw BF16 row.

The original grouped RMS shader then receives each native vector row pointer,
the unchanged raw BF16 gamma pointer, the same row pointer as output, width2560
and groups1. Each call uses grid1/block256/default stream/dynamic shared0,
preserving the retained original count1 embedding ABI and input/output alias.
The candidate's unchanged whole-row CPU RMS supplies a separately sealed exact
normalized BF16 reference. The original kernel supplies its own reduction,
native reciprocal square root, epsilon, FP32 operations and BF16 RNE store.
No CPU formula, tolerance adjustment or arithmetic fitting is added.

The three successful device allocations are only pack, all converted rows and
raw gamma: `64+1440*N+5120*N+5120` bytes, maximum425024 bytes. Every row pointer
stays inside the successful converted-row allocation. This bound excludes HIP,
codeobject and process overhead; it does not replace root's reserve guard.

The report schema is `halogen0162.q4c-multirow-original-kernel-oracle.v1`.
Success requires exactly `N+2` attempted/successful launches and synchronizations,
`N+6` copies, three allocations/frees, one module load/unload, zero native/file
cleanup errors, all immutable inputs rechecked, three exported files and no
BF16 mismatches or nonfinite values. At64 rows these are66 launches,
66 synchronizations and70 copies.

Outputs are `vector-raw.u16`, `scalar-raw.u16` and `vector-native-norm.u16`, each
`5120*N` bytes on success. Complete converter outputs and every RMS row actually
copied back are retained even on numerical mismatch. A runtime failure partway
through RMS retains only its copied prefix and explicitly records its extent.
Each row receipt binds original token, reference/native hashes, copy flags,
mismatch counts, first mismatch indices and nonfinite counts. No tolerance gate
is available. Root must verify all actual output extents/hashes and the outer
owned-window cleanup receipt before using the native report as evidence.

## Root-only execution handoff

Metadata-only preparation takes:

```text
python halogen0162_q4c_multirow_oracle_prepare.py
  --source-sha256 REVIEWED_PREPARER_SHA
  --harness-sha256 REVIEWED_C_SHA
  --producer-sha256 REVIEWED_PRODUCER_SHA
  --producer-plan ABSOLUTE_PRODUCER_PLAN_JSON
  --producer-plan-sha256 ROOT_SEALED_PLAN_SHA
  --complete ABSOLUTE_CANDIDATE_COMPLETE_JSON
  --complete-sha256 ROOT_SEALED_COMPLETION_SHA
  --assets ABSOLUTE_FOUR_RECEIPT_DIRECTORY
  --tokens EXACT_EXPLICIT_ORIGINAL_TOKEN_LIST
  --out ABSOLUTE_FRESH_MANIFEST_DIRECTORY
```

Root hashes the emitted manifest and plan independently. Build in the retained
original Linux image with the reviewed HIP headers, the C source and frozen
scaffold adjacent, and the frozen scaffold compile pin:

```text
gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__ -I<reviewed HIP include>
  -DQ4C_MULTIROW_BUILD_SCAFFOLD_SHA=\"7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8\"
  halogen0162_q4c_multirow_oracle.c -ldl -lcrypto -o <fresh reviewed binary>
```

Native CLI has exactly eight arguments after the executable:

```text
replay ENGINE HSACO HIP_LIBRARY HIP_SHA
  CANDIDATES_DIRECTORY MANIFEST_BIN MANIFEST_SHA FRESH_OUTPUT_DIRECTORY
```

The existing one-row owned controller cannot run this sibling unchanged: it
hardcodes the old binary/plan/export schema and argument list. Root's sibling
envelope must retain its exact UUID ownership, original ready/idle controller
identity preservation, read-only mounts, stock HIP/DXG bindings, exclusive GPU
latch, 22GiB admission/18GiB continuous physical-and-commit reserve, owned process
deadline and exact-ID cleanup. Read-only mounts should bind this reviewed binary,
C source/scaffold, original engine/codeobject, manifest/plan and completed
candidate directory. No model mount, provider or NPU session is required.
Do not run the arithmetic window concurrently with an engine benchmark.

A passing native receipt qualifies only these explicitly sealed selected rows'
Q4C/raw and count1 RMS arithmetic. The receipt's narrow qualification fields
depend on the complete passing run. Original full-table loader, general table,
live allocation/generation/publication, batch FC skipping, full-D/head,
NPU/fabric-clock overlap, acceptance and speed qualification remain false.
Neither the manifest generation bytes nor the synthetic producer schedule prove
that a live model generation supplied or consumed these rows.

## Executed64-row result and retained failure

Root's owned window is
`server/.local/optimization9h-20261004/q4c-multirow-owned-35bf1b51d916442b8101605ab80b6dcc`.
The component ran at 2026-10-05 04:27:25..04:27:28 UTC in the same pinned original
image. Its native `result/replay/replay.json` SHA256 is
`3470a7754bfc54d5e8406e7b95f4cf21b18e0fbfd5d251b0bb47cdf106ccc867`.
The outer `result.json` SHA256 is
`133515b2402cf044c3086c6f5d3548e5508bcaca147ad45cb23f9aff8618c826`.
The native error is `exact-BF16-word-gate`; both native and outer `passed` remain
false and the native process exited1. The immutable native report conservatively
ties both `selected_rows_raw_parity_qualified` and
`selected_rows_RMS_parity_qualified` to that combined result, so both remain
false there. The narrower raw-only evidence below is a separately reviewed
component conclusion, not a change to that report.

| Boundary or guard | Retained result |
| --- | --- |
| Original vector Q4C conversion | All64 rows, all2560 BF16 words per row exact; zero mismatches/nonfinite values |
| Original scalar Q4C conversion | All64 rows, all2560 BF16 words per row exact; zero mismatches/nonfinite values |
| Both raw aggregate outputs | 327680 bytes each; SHA256 `e893e05cfcea3960605fcfc2d5aaad96222aaa750b81ceb507787801c78ab6ca` |
| Original count1 RMS |63 exact rows; row7/token28651 has2 word mismatches; first1193; no nonfinite values |
| Row7 candidate normalized SHA256 | `21c13d5d3aea4d6da4a3ec7519a632a8982bf3118fb738b4c5fe9d84f7233fe7` |
| Row7 original native normalized SHA256 | `a074217b5446f996cda728361d4fa3a6d61e03fd6c4fdc42b9dd965b8a5d7032` |
| Native operations |66 successful launches/synchronizations,70 copies,3 allocations/frees,1 module load/unload |
| Native export/rechecks/cleanup | All64 rows copied,3 files exported, all immutable files rechecked; zero HIP/file-close errors |
| Outer cleanup | Exact owned container removed, job closed, monitors stopped, controller handle closed, shared ownership latch released; no cleanup pending |
| Original colleague | Preserved; no contamination or guard errors |
| Host reserve | Minimum physical26.086758 GiB, commit118.948708 GiB; 22/18 GiB guard retained |

The exact selected token order is the sealed producer plan's list: token14367
followed by `k*4093 mod248320` for `k=1..63`. The producer plan SHA256 is
`cfbf862eaea8c3e3b9e65f7136664fc03bea55cff063dadb6e7ec67b3136f6a7`;
completed candidate receipt SHA256 is
`0cbdf9b414840b7c2a3ed1be079faef5d68e3770e836c1be99251332e8dfb563`.
Oracle plan and manifest SHA256 are respectively
`6bb50efd586b9d484d644bafee676d4bd1e9064a551c271fe384e934486bf23e` and
`c98eefb53bf7c6b1b0476dde1a365ad153da41db35501ec8069c890a3c7f24e4`.
The reviewed root-built binary SHA256 is
`c159ff52b902ab2ff9b480fe01cd3bb1de5b0e276569722501d5c9214afa90c6`.

The sibling owned runner is
`scripts/benchmarks/halogen0162_q4c_multirow_owned_run.py`. It retains the original
controller's read-only process handle, ready/idle/health counters, and22/18 GiB
continuous guard. It additionally checks backend controller24960/run
`babc627cdc474863b0aa8b2104297d4c` and its fresh heartbeat. It uses the same
`q4c-row-owned.lock` to exclude the old and new Q4C windows, streamed hashes for
large runtime artifacts, read-only input mounts and exact UUID/CID cleanup.
Its config schema is `halogen0162.q4c-multirow-owned-config.v1`, with exact keys
`schema`, `image`, `colleague_cid`, `controller`, `health`, `binary`, `oracle`,
and `complete_sha256`. `binary` has `native_path`/`sha256`; `oracle` has
`directory`/`plan_sha256`/`manifest_sha256`. The actual64 producer plan and
candidate directory are fixed in this runner. It admits only this accuracy
window and records broader/live/table/FC/NPU/speed gates false.

## Generic RMS arithmetic discrepancy; sealed producer preserved

The sealed producer invokes `halogen_npu_v2_d_prepare.py:rms_bf16`, which computes
separate FP32 squares, `np.mean` across the contiguous whole row, FP32
`reciprocal(sqrt(mean+epsilon))`, then the two native-order FP32 products and
BF16 RNE. Its source explicitly leaves native reduction/rsq bit parity
unqualified. Agreement on frozen A/B did not establish equivalence on every
new raw row.

The retained original shader text is
`server/.local/optimization9h-20261004/mtp-route-static-20261004/k-rmsnorm-grouped-gfx1151-disassembly.txt`,
SHA256 `dbd3c9ea1e560f13aad9156fb7867bfe441872b8591ee87b6fc2d15d1b2bba95`.
At `0x22d348`, each of256 lanes accumulates its strided inputs with FP32 square
FMA: lane `j` consumes columns `j,j+256,...,j+2304`. At
`0x22d5c0..0x22d5e0`, LDS reduction adds lane pairs in the fixed descending
strides128,64,32,16,8,4,2,1. The FP32 mean division ends at `0x22d414`, epsilon
bits `0x358637bd` are added at `0x22d42c`, and `v_rsq_f32` executes at
`0x22d468`. Two FP32 products at `0x22d508`/`0x22d518` precede the same BF16
RNE store sequence at `0x22d530..0x22d544`.

Those two implementations have different reduction order and reciprocal-square-
root instructions. This is a verified arithmetic contract discrepancy. Source
and output JSON alone cannot establish whether reduction rounding, native rsq
rounding, or both caused the two final BF16 differences in token28651. No
intermediate numerical attribution is claimed by this source-only review.

A generic CPU-reduction proposal would use256 lane accumulators, consume ten
stride256 terms in original order, and apply the same128-to1 halving tree before
unchanged width division, epsilon, product order and BF16 boundary. It still
needs independent proof of native `v_rsq_f32` semantics; replacing the reduction
alone does not establish exact normalized-row parity. The sealed producer, CPU
references, native oracle, source pins, receipts and tolerance values remain
unchanged. Useful GPU/NPU overlap and a speed benefit remain unqualified, and
no additional native/provider RMS window runs during the long engine benchmark.

Root subsequently checked the retained native outputs against the original
unchanged CPU tolerance `rtol=.002, atol=.0002`, and both differing values failed
that screen as well:

| Zero-based column | Original native | Existing CPU candidate | Absolute error | Original allowed error |
| --- | ---: | ---: | ---: | ---: |
|1193|0.2041015625|0.205078125|0.0009765625|0.000608203125|
|1477|0.408203125|0.41015625|0.001953125|0.00101640625|

The broader NPU tolerance does not satisfy this separate CPU gate. The failed
exact BF16 receipt and original CPU admission gate both remain failed. No
tolerance loosening or row-specific arithmetic fitting is proposed.

Root requested a separate CPU-only reduction diagnostic, supplied as
`scripts/benchmarks/halogen0162_embedding_rms_cpu_tree.py`; it does not edit or
adopt the sealed producer. Its pure function
`rms_bf16_words(raw_words, raw_gamma_words)` takes two copied tuples/lists of
exactly2560 finite unsigned16 BF16 words and returns2560 normalized words plus
metadata containing the sum/mean/epsilon/inverse FP32 bit patterns. It has only
standard-library `math`/`struct` imports, requires Python>=3.13 `math.fma`, and
performs no file, model, provider, device or process work.

The diagnostic fixes the lane count, ten stride256 terms and128-to1 reduction
tree from the retained shader. It rounds every FMA/tree/division/epsilon/product
boundary to FP32 with explicit `struct` serialization, applies epsilon bits
`0x358637bd`, the original two-product order, and BF16 RNE. It rejects input
domains whose nonzero BF16 squares are subnormal or inexact in FP32, avoiding an
unreviewed claim about native denormal handling. Its inverse is uniformly one
FP32 rounding of CPU `1/sqrt(mean+epsilon)`. It accepts no token ID, column,
observed native output, calibration, fitted value or tolerance argument.
The native `v_rsq_f32` bit semantics remain explicitly unqualified.

Only Python AST parsing was performed by this preparation agent; it did not
execute the function or read the supplied row tensors. Root can compare this
uniform CPU diagnostic against all retained64 original native rows without
starting a new GPU/provider window. Its source and outputs have a separate
diagnostic scope. No adoption into the sealed producer, exact-native parity,
live integration, GPU/NPU overlap or speed benefit is claimed here.

Root subsequently executed the uniform `math.fma` CPU diagnostic against all64
retained original native rows. All163840 normalized BF16 words matched exactly,
with zero word differences and zero violations of the original CPU tolerance.
The supplemental receipt is retained beside the failed native window as
`cpu-tree-original-tolerance.json`, SHA256
`233d5c97c85e1e923956b50401a1ba091159438ec1f3f79a17b89626ec5f5711`.
This qualifies that CPU rule's output accuracy for the exact64 supplied rows
and unchanged raw gamma. It does not establish the general bit implementation
of native `v_rsq_f32`, and the original producer/failed receipt remain unchanged.
The successful rule changes both the reduction schedule and reciprocal-square-
root rounding path uniformly; it does not isolate their individual effects.

## Explicit portable offline adapter

The original `math.fma` diagnostic and its executed source pin remain unchanged.
For Python3.12 execution, the new separate helper
`scripts/benchmarks/halogen0162_embedding_rms_cpu_tree_portable.py` preserves the
same exact-square input-domain check, strided lane order, halving tree, FP32
boundaries, one-round CPU reciprocal square root, gamma products and BF16 RNE.
The caller must explicitly pass `accumulation="portable_exact_square"`. Within
that checked domain, each BF16 square is exact in FP32; the portable binary64
product plus FP32 partial, followed by FP32 rounding, reproduces the reviewed
square-FMA accumulation boundary. The helper takes no native output or fitting
parameter. Portable execution and new candidate generation were not performed
by the preparation agent at this handoff.

The thin sibling
`scripts/benchmarks/halogen_mtp_early_token_native_rms_producer.py` consumes an
existing sealed original producer plan and requires explicit `--native-rms`.
It reuses the original producer's metadata validation, strict bounded native
checkpoint windows, Q4C decoder, BF16 helpers, stable split and exclusive writes.
Only its uniform CPU normalization comes from the separately pinned portable
helper. Captured helper source bytes are SHA-bound before execution, and all
sources/metadata/native checkpoint identity are rechecked before completion.
It does not duplicate or edit the original producer's planning framework.

The adapter reads the same bounded selected codebook/codes/scales/raw gamma,
emits the same five per-token candidate files plus pack/gamma/token-order files,
and writes a fresh `complete.json` last. The concise completion schema is
`halogen0162.early-token-native-rms-candidates.v1`, binding adapter/original-
producer/portable-helper/original-plan hashes, generation/sequence, exact token
order, per-row raw/normalized hashes, source windows and output-file hashes.
Original plan and candidate receipts are preserved. Native arbitrary-row,
full-table/live/publication/FC/NPU/overlap/speed gates remain unadmitted, and CPU
and NPU tolerances retain their original values.

Root-only CLI uses the existing original plan rather than creating another plan:

```text
python halogen_mtp_early_token_native_rms_producer.py --native-rms
  --source-sha256 1c15e38755af53f107c40863f17251197118c404e6ead6aa470d911b06e5caa6
  --plan ABSOLUTE_EXISTING_ORIGINAL_PRODUCER_PLAN
  --plan-sha256 ROOT_SEALED_ORIGINAL_PLAN_SHA
  --generation-hex SAME_SEALED_GENERATION --sequence SAME_SEQUENCE
  --assets ABSOLUTE_FOUR_RECEIPT_DIRECTORY
  --checkpoint ABSOLUTE_ORIGINAL_LINUX_CHECKPOINT
  --out ABSOLUTE_FRESH_CANDIDATE_DIRECTORY
```

The original BLAS/OpenMP thread variables must all be1 before Python starts,
and the unchanged original numerical helpers require NumPy2.5.3. Root owns
CPU-only production, original22/18 GiB reserve admission and output validation.
This adapter opens no FC/hidden tensor, provider or device and implements no live
publication, NPU execution or speed claim. Both new Python sources were parsed
with `ast.parse`; their payload functions were not executed by this preparation
agent. No further tests or native/provider window was started by it.

Root then executed the portable helper on Python3.12 against the same64 retained
native rows. All163840 normalized BF16 words again matched exactly, with zero
word differences and zero violations of the original CPU tolerance. Its receipt
is `cpu-tree-portable-original-tolerance.json` beside the retained native window,
SHA256 `e217c62ba6f1aaf44f25135b2430f8966abbf61123b440174d5895c01d5b5e8e`.
The CPU-only check maintained the18 GiB reserve, with reported minimum physical
21.486 GiB and approximately114.33 GiB commit headroom.

The portable helper's uniform arithmetic correction is therefore verified for
these exact64 supplied raw/gamma rows. The thin adapter with source pin
`1c15e38755af53f107c40863f17251197118c404e6ead6aa470d911b06e5caa6`
has not executed checkpoint production at this report update: the separate
22 GiB production-admission threshold is not currently met. No new candidate
receipt from that adapter is claimed. The tested helper result supplies an
accuracy correction within its recorded64-row scope; it establishes no arbitrary
native `v_rsq` equivalence, active NPU benefit, useful overlap, live publication,
full-engine speed gain or broader admission.
