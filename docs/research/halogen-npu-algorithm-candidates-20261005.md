# NPU algorithm candidates for the current Halogen engine — 5 October 2026

**Decision: no useful NPU candidate is presently admitted.** None of the three
mechanisms below establishes faster processing of the same Halogen
Qwen3.8-Flash-Next input or faster verified decoding. The NPU does not add a
separate large GPU memory pool. Exact compression could increase effective
capacity only by storing fewer real bytes and reconstructing them cheaply;
another copy of a table or a prepared result consumes the same system memory.

The closest concrete implementation opportunity is a **whole count1 embedding
branch cache**, which skips gather, RMS and FC together on a ready hit. Its
first control should use original GPU-produced projections, so a branch fixture
can establish whether the consumer can save real work before adding a producer.
Merely prewarming the already losing M1 FC cache with the NPU is not justified.
There is no implemented compressed-LUT consumer. A synthetic byte/DMA diagnostic
would not repair that missing integration and is not recommended as the next
task. The Windows integer/DMA findings below describe capability boundaries only.

This assessment read research/source documents and primary public sources.
It opened no checkpoint/tensor payload, registered no provider, ran no device
query or inference, changed no server/profile/clock/runtime, and staged or
committed nothing. Root owns any later guarded execution. The existing engine
must remain open after that work. The prior Rulith SSD/pregather portability
audit is retained without being repeated.

## Retained facts and limits

The current regular profile has arena 8192 and context capacity 262144. The
retained newest stock control used **8192 actual input / 128 output tokens**:
1277.138669 prefill tok/s, 41.280099 MTP decode tok/s and 60% acceptance
(207/345). Capacity is not an occupied260K-input measurement. All these windows
were GPU-only; the NPU-on token-rate delta remains **unmeasured**, not zero.
[Practical placement decision](halogen-useful-npu-decision-20261005.md).

The synchronous paired projection remains slower: GPU host bracket0.487170 ms
versus NPU session1.850025 ms, before transport/integration. The hidden branch
still lacks the complete accuracy qualification needed for live replacement.
The separate count1 embedding graph passes the original frozen NPU screen
`rtol=.03, atol=.003` on A/B, but changes858/847 native BF16 words. Its
0.9674 ms session and2.104775 ms diagnostic call have different scopes from the
paired GPU measurement; they are not a matched embedding-only engine A/B.
Cold NPU initialization was24.386s. No latency is converted into measured
tok/s. [Embedding component](halogen-npu-early-embedding-component-20261005.md).

The newer uniform CPU RMS rule matches **all 163840 normalized BF16 words on
the selected 64 rows** exactly, under the unchanged `.002/.0002` CPU gate.
This supersedes the older two-row limitation for these selected rows only.
It does not prove arbitrary-row reciprocal-square-root semantics, live table
allocation lineage, NPU RMS, new-row NPU FC, full-head proposals, or acceptance.
The original failed 64-row candidate receipt remains failed.
[64-row oracle and CPU correction](halogen-q4c-multirow-oracle-20261005.md).

The already executed GPU cache controls supply no useful benefit. In the
original-gather variant, hits took0.341134 ms host time versus0.322974 ms
original, and misses0.488103 ms versus0.336505 ms original. Faster arithmetic
alone cannot cover an interface that costs more than the work it skips.
[Original-gather cache replay](halogen-embedding-gather-cache-replay-20261005.md).

## What Windows support actually establishes

AMD Ryzen AI 1.8 documents Strix Halo support and groups it with STX; its
compatibility table covers NLP BF16 and OGA LLM models there. This does not
qualify an arbitrary integer codec or the installed EP build.
[AMD release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html).
The retained installed WinML package is
`MicrosoftCorporationII.WinML.AMD.NPU.EP.1.8_1.8.75.0_x64__8wekyb3d8bbwe`;
the local Light EP audit records its separate admission failures.
[Local provider audit](halogen-npu-light-ep-route-20261004.md).

| Operation / route | Primary documentation | Present local conclusion |
|---|---|---|
| `BitShift`, `BitwiseAnd/Not/Or/Xor`, `Cast` | Ryzen AI 1.8 lists broad BF16 and XINT8 graph coverage, with configuration exceptions | A published name is not proof of uint8/uint16 preservation or NPU placement in this package |
| `Gather`, `GatherElements` | The table lists Gather under BF16 and GatherElements under BF16/A16W8/A8W8 | It does not establish a dynamically indexed raw uint8 LUT bank |
| Lossless compression/decompression | No generic byte codec is listed | Build an explicit integer graph/kernel; do not interpret ONNX `Compress` as a codec |
| VitisAI partitioning | Supported subgraphs run on NPU; other subgraphs run on CPU | Disable CPU fallback and inspect dynamic output placement and execution profile |

The operator table explicitly limits its claim to broad coverage, allowing
unsupported configurations. Existing FP32 bank20, BF16 bank16 and BF16
row-Gather candidates failed strict placement with zero NPU inference calls.
Repackaging them as compression does not remove that boundary.
[AMD operator table](https://ryzenai.docs.amd.com/en/latest/ops_support.html),
[AMD partitioning reference](https://ryzenai.docs.amd.com/en/latest/modelrun.html),
[retained candidate inventory](halogen-npu-candidate-inventory-20261004.md).

ONNX `BitwiseAnd` starts at opset 18 and specifies integer types. `BitShift-11`
specifies unsigned integer types. Thus an exact-byte graph should state its
opset and uint types explicitly; AMD's recommended opset 17 is not a blanket
proof that an opset 18 codec works. ONNX `Compress` selects elements using a
boolean condition; it is not reversible data compression.
[BitwiseAnd schema](https://onnx.ai/onnx/operators/onnx__BitwiseAnd.html),
[BitShift schema](https://onnx.ai/onnx/operators/onnx__BitShift.html),
[Compress schema](https://onnx.ai/onnx/operators/onnx__Compress.html).

Native Windows MLIR-AIR supports custom NPU programs and identifies Strix Halo
as `npu2`, core architecture `aie2p`; its example path uses XRT. It requires a
matching XRT SDK and Python ABI, independently of the current WinML setup.
MLIR-AIE documents bitwise operations on8/16/32-bit integer vectors. These are
primary evidence for a custom integer implementation route, not evidence that
this toolchain is installed or qualified here.
[Windows MLIR-AIR guide](https://xilinx.github.io/mlir-air/dev/buildingRyzenWin/),
[AIE vector bitwise operations](https://xilinx.github.io/mlir-aie/dev/AIEVecDialect/).

## DMA, physical bytes and the Windows/WSL boundary

AMD describes up to128 GB unified system memory on395, with up to96 GB assignable
to graphics. Its NPU zero-copy discussion describes CPU/NPU access to the same
physical memory. NPU local tile memories are staging resources in the cited
custom-kernel flow, not a newly available47.7 GiB store.
[395 memory description](https://www.amd.com/en/blogs/2025/amd-ryzen-ai-max-395-processor-breakthrough-ai-.html),
[AMD CPU/NPU zero-copy explanation](https://www.amd.com/en/developer/resources/technical-articles/2026/upscale-everything-super-resolution-across-amd-hardware-.html).

MLIR-AIE's passthrough-DMA design moves external-memory data through a shim and
compute-tile DMA without modifying it. That separates data movement from
arithmetic in the design. It is not a random gather, SSD read engine,
GPU-memory export API, or Windows-to-WSL shared allocation.
[Primary DMA design](https://github.com/Xilinx/mlir-aie/blob/main/programming_examples/basic/passthrough_dmas/README.md).

Do not confuse tile DMA with XRT's generic buffer-to-buffer KDMA copy. XRT source
throws `KDMA not supported on windows` in `copy_bo_with_kdma()`. A Triton-XDNA
maintainer explains that its `map`/host `memcpy`/`sync` launcher does not invoke
that path, and reports Windows validation of the npu2 ELF route. A successful
sync neither proves a DMA copy nor proves that all NPU transfers are CPU copies.
[XRT source](https://github.com/Xilinx/XRT/blob/master/src/runtime_src/core/common/api/xrt_kernel.cpp),
[upstream maintainer explanation](https://github.com/amd/Triton-XDNA/issues/88).

ORT ordinarily copies CPU inputs to the target and outputs back to CPU unless
appropriate device buffers are bound. I/O binding can avoid some copies with
supported allocations; its generic API does not establish importing a WSL HIP
pointer into this Windows NPU EP. No inspected source supplies that interoperability
contract here. Budget Windows preparation, EP input/output, IPC, WSL receipt,
HIP upload and the publication event separately.
[ORT I/O binding](https://onnxruntime.ai/docs/performance/tune-performance/iobinding.html).

| Data | Exact logical bytes | Accounting implication |
|---|---:|---|
| Current n-gram lookup tensor |51,200,245,764| SSD-backed mapped source; not proof all bytes are physically resident |
| One n-gram row |160| Already FP8/global-scale storage; cold access can fault1–2 filesystem pages |
| One count1 embedding BF16 row |5120| Different table and pipeline from the n-gram LUT |
|64 BF16 rows in one raw, normalized, or projection bank |327,680| Keeping all three banks uses983,040 bytes before metadata |
|64 pairs of widened FLOAT high/residual inputs |1,310,720| Producer/provider scratch consumes more than a BF16 bank |

For the LUT,320001536 possible rows imply2,560,012,288 bytes for one uint64
offset per row, before lengths, dictionaries and alignment. A global byte offset
into a51.2 GB image cannot fit in uint32; smaller shard-relative directories need
their own specified format. Compare **actual resident physical bytes and commit**,
including source file-cache pages and Windows/WSL/provider/scratch copies. Merely
reducing a logical file size or duplicating OS-cached pages is not extra GPU
capacity. [Audited LUT layout](halogen-cpu-ssd-opportunities-20261004.md).

## Three candidates

### 1. Exact LUT-row codec or predictive row gather

The useful mechanism would store an exact compact row/block representation,
resolve the actual row IDs, decode selected bytes once, and deliver the original
160-byte FP8 rows to the unchanged consumer. A concrete falsifiable seed is a
16-symbol byte dictionary plus80 packed nibble indices for a160-byte row:
96payload bytes instead of160, **only if that row really contains at most16
distinct bytes**. Headers/directories/fallback rows reduce the saving. No payload
entropy or qualifying-row fraction was measured; the40% payload arithmetic is
not a claim about these learned weights. More INT4 quantization would change
weights and is not this codec.

Static lookup evidence places actual row IDs on the CPU only after the existing
device-to-host copy at `0x17d7aa6`, followed by mapped-source `memcpy`. At that
point a decoder is on the critical path unless an earlier producer has the same
exact IDs. Prompt tokens being known does not establish a qualified host
implementation of the n-gram indexer. Predicted rows can only populate a private
cache; misses must use the original bytes without waiting. The prior Rulith
audit establishes no Halogen next-chunk producer/consumer scheduler hook.
[Lookup dataflow](halogen-cpu-ssd-opportunities-20261004.md),
[retained pregather portability finding](halogen-update-checkpoint-20261005-0859.md).

The codec needs exact byte equality, original order, scale bits, model epoch and
range validation. Approximate floats, tolerant comparisons or a matching
fingerprint cannot replace a complete byte comparison. A strict provider graph
would need integer unpacking and dictionary selection; Gather's present failures
are a substantial obstruction. A custom AIE kernel is a separate possible route.

**Disposition:** no present useful candidate. Necessary falsification:
`C + directory + retained-source-residency + scratch < current-residency` and
`row-read + decode + all-copies + publication < original row-ready latency`
at the consumer. If source residency is retained unchanged, effective-capacity
claims fail. If required operations land on CPU, an NPU decoder claim fails.
A DMA passthrough may relieve a CPU thread only after its entire launch/transfer
path beats native CPU copying; it adds read/write traffic to the shared bus.

### 2. Amortized immutable embedding/normalization preparation

For fixed native embedding bytes, gamma and arithmetic epoch, the count1
embedding branch depends on token ID. This permits preparation before the head,
in a root-qualified isolated window without concurrent GPU work. The selected 64
exact CPU raw/RMS rows now give a bounded input basis. A normalized-row cache
could avoid gather/RMS; a projected-row cache could additionally avoid eFC.
NPU normalization itself is unqualified, so the CPU exact RMS producer must
remain distinct from the NPU FC producer.

Known prompt IDs or pre-verification drafts provide early information. Target
correction/bonus IDs remain unknown until the target returns, and consecutive
draft heads have no guaranteed overlap window. Outputs are usable only after
same-epoch GPU upload and completion-event publication. Count>1 still needs
batch/mixed-row qualification. A ready miss returns immediately to native.
[Early schedule](halogen-npu-early-token-schedule-20261005.md).

This is useful memoization in principle, not NPU-specific memory. CPU exact
preparation or original GPU memoization can feed the same cache. The64 rows'
NPU FC and full head have not passed; the earlier A/B screen cannot qualify
them. A large all-vocabulary BF16 bank would occupy1,271,398,400 bytes per stage,
with no measured hit coverage. Excluding preparation from warmed timing can
show amortization, but must not hide its cold wall time or extra memory.

The missing consumer is specific. A new Count1/wireD branch shim could decide a
ready hit from host token/model generation before the gather at `0x17db449`;
enqueue one ordered5120-byte D2D copy to `*(model+0xb00)`; and suppress exactly
the selected embedding gather, embedding RMS at `0x17db517`, and embedding FC
at `0x17db543`. Hidden preparation/FC, seed-add, layer48 and controller state
would execute normally. The current cache decides at the FC seam and cannot
perform this. A new branch fixture must first prove the skipped normalized
buffer has no later consumer on this route, compare complete branch outputs,
and exercise hit, miss, pending, generation retirement and unsupported count.
Copy failure after a possible partial write must fail stop; it cannot retry the
native branch as if no write occurred. Original GPU capture is the exact first
producer control. NPU prewarm is a later producer variant only after that
consumer wins and full-head quality passes.
[Audited branch/seed dataflow](halogen-mtp-d-projection-integration-20261004.md),
[current FC-only consumer contract](halogen-mtp-embedding-cache-contract-20261005.md).

**Disposition:** concrete whole-branch implementation opportunity, but no
presently useful NPU placement. Compare whole gather/RMS/FC removal against an
exact native CPU/GPU prewarm control, not only the already losing FC-only cache.
The source dataflow makes this testable; it does not supply a measured gain or
proof that skipping the raw/normalized buffer is harmless. Required
gate is `max(0, producer-latency - actual-lead-time) + lookup/publication-cost
< skipped-native-work`; for isolated prewarm also report preparation cost per
actually served request. Unqualified concurrent fabric hold/readback prevents
assuming ongoing GPU/NPU production can overlap safely. No supported hold was
established by this research.

### 3. Accurate sidecar or external draft gating

A narrowly qualified NPU classifier can avoid an entire auxiliary Qwen request;
that can improve task wall time. It does not accelerate processing of an
unchanged Flash prompt. Halogen's published decision/embedding/rerank/moderation
services select another model by request; their native Linux NPU contract is
not Windows responder or Flash proposal-injection proof. The published contract
also records shared memory-bus/power contention during concurrent operation.
[Pinned Halogen NPU contract](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md).

A drafter can preserve target output quality only with the correct target
verification/commit or sampling correction; classifier confidence cannot safely
skip verification. The speculative-decoding paper establishes that algorithm,
not a Flash-Next-compatible NPU draft head. The public Halogen benchmark supplies
native `serial`/`mtp`, with no separate draft checkpoint. Existing integration
research found no external feature/proposal/state-commit API.
[Speculative-decoding paper](https://arxiv.org/abs/2211.17192),
[pinned serving client](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/tools/bench-serving.py),
[local integration audit](halogen-laya-jev-sidecar-feasibility-20261004.md).

**Disposition:** no presently useful target drafter or gating candidate. Require
held-out task accuracy for routing, or complete verifier-compatible proposals
and state rollback for drafting. For decoding the necessary condition is
`total round wall / actual committed tokens < matched stock MTP ms/token`.
Include IPC, target verification, rejection, rollback and target slowdown;
acceptance percentage or standalone NPU tokens/s is insufficient. The current
41.280099 tok/s stock amortizes to about24.2247 ms/token, solely as arithmetic
for that cohort, not a new drafter timing.

## Next implementation decision and final speed gate

Do not run a synthetic DMA or codec gate merely to make the NPU active. There
is no compressed-LUT consumer to test, no measured real-row compressibility,
and no qualified Windows/WSL allocation-sharing contract. A generic integer
operator success would not establish any of these requirements.

If development continues, the whole-branch consumer in candidate2 is the only
concrete small implementation opportunity found here. First implement its
original-GPU-output branch fixture and measure the complete gather+RMS+FC path
against the ready-hit D2D path. Do not initialize an NPU for that control. Stop
if a realistic hit mix cannot recover lookup/copy/miss/publication cost, or if
the skipped buffers have another required consumer. Only a positive consumer
result justifies an NPU producer, and that producer must beat native prewarming
including preparation cost. This is a new consumer design, not a recommendation
to repeat the prior FC-only or gather-only cache replay.

Actual speed admission still requires a separate root-owned engine experiment
that executes a candidate path. Preserve the same checkpoint/request hashes,
actual8192/128 tokens, arena/context/cache/sampling/MTP depth and reserve
controls; retain stock bookends and at least three measured requests. Compare
engine prefill/decode plus complete request wall, identical greedy output,
proposed/accepted counts, row hits/misses, skipped calls, publication readiness,
transfers and real memory high-water marks. Startup/prewarm and warmed service
must be reported separately. Any attempted concurrency first needs a supported
held fabric state and readback; component success supplies neither that gate nor
a causal tok/s result. Preserve the existing22/18 GiB admission/reserve guards
and restore the original ready/open server after an owned window.

For now all three NPU tok/s deltas remain unmeasured. The justified action is
to retain the original GPU inference path and avoid representing NPU utilization,
DMA capability, compressed logical bytes, or exact selected-row RMS as an
already useful acceleration.
