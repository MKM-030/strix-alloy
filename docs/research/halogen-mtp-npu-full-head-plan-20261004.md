# Halogen v2 complete MTP head on NPU: implementation plan

There is no runnable, qualified full-head NPU graph in the retained work. The
existing expert graphs cover only routed MLP arithmetic. A complete head must
also implement input transforms, three hyperconnection mixers, indexed
attention with persistent history, shared MLP, continuation publication and the
248,320-way output projection. This plan specifies those stages without
performing new weight reads, export, provider initialization or hardware work.

Keep the native target/controller/verifier authoritative. Initially replace
the complete head at `0x17db310` for the qualified greedy kind1 path; retain
native target commit and explicit accepted-prefix replay. Resolve the current
root-owned QMoE provider fault before a whole-head admission. The 22-GiB
admission and continuous 18-GiB physical/commit floors remain unchanged.

## Sources and arithmetic qualifications

Engine SHA256 is
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
The [state ABI](halogen-mtp-full-head-state-abi-20261004.md) and
[accepted replay receipt](halogen-mtp-accepted-prefix-replay-20261004.md) give
native call sites and lifecycle. Static evidence is retained in
`server/.local/optimization9h-20261004/mtp-route-static-20261004/`.
Current geometry/encoding comes from
`C:\AI\halogen-mtp-npu\v2-metadata-20261004\mtp-metadata.json` and the
[31-tensor standalone manifest](halogen-mtp-standalone-manifest-20261002.json).
The older w4b geometry must not supply v2 dense encodings: 18 v2 dense matrices
are q8g64 (store7/variant0), ten tensors are BF16, and two routed tensors plus
the scalar shared gate are q4c (store5/variant2).

The [official config](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/main/config.json)
specifies hidden size 2560, four streams, rank 320, one MTP full-attention block,
24 query/two KV heads of dimension 256, an indexer with four 128-wide heads,
compression ratio 4 and budget 2048, 512 experts/top10/intermediate width 640,
vocabulary 248320, epsilon 1e-6 and theta 10,000,000. Partial rotary factor .25
implies 64 attention rotary features. Native indexer rotary width needs explicit
qualification: the local Transformers reference reuses the attention cosine/
sine tables, so blindly applying .25 to indexer width 128 is not justified.
Interleaved MRoPE sections are 11/11/10. These identify the intended topology,
not native bit-level arithmetic.

Read-only topology references are the local Transformers
`models/qwen4_exp/modeling_qwen4_exp.py` (RMSNorm lines 163–183, indexer 684–792,
attention 830–914, MLP 915–1013, HC 1014–1049) and llama.cpp
`src/models/qwen4exp.cpp` (MTP lines 282–388). Transformers ignores `mtp.*`.
The llama.cpp MTP path deliberately uses dense attention and its full-model
converter substitutes the trunk final mixer; neither is an equivalent native
Halogen indexed-head exporter unchanged. Use the actual dedicated
`mtp.hyper_connection_mixer.*` weights.

Native input mode is a material contract. One-time initialization
`0x17dc190..0x17dc284` reads `HALOGEN_MTP_WIRE` at RVA `0x2266a`, takes its
first byte when present and otherwise selects ASCII **D** (`0x17dc26d`). A
parent-authorized bounded read of the pinned local ELF's headers and 128 string
bytes resolved that name at file offset `0x2266a`; no model payload was read.
For D, the hidden norm width is 10240 with one group (`0x17db5a8..0x17db5b0`),
`fc_hidden` runs 4 x count rows of width 2560 (`0x17db636..0x17db65e`), and
`k_hyper_seed_add` combines it with the embedding projection
(`0x17dba4b`). A uses a different input pointer; other modes use grouped
norm with four groups and `k_hc_fold`, with B selecting a different fold scalar.
Do not infer the runtime mode from its default or silently select another mode.
Public RMSNorm uses FP32 normalization and zero-centered gamma `1+weight`;
whether HGN norm payloads already fold this offset remains a qualification
item. The full-head ABI establishes raw u16 residual storage; its numeric
interpretation and every required intermediate rounding must be proved.

## Complete stage contracts

All matrix shapes below are stored **[out,in]**. `C` is the ABI row count and
`H` is the four-stream continuation `[C,4,2560]`.

| Stage | Computation and exact shapes | Result/state |
|---|---|---|
| Token/residual preparation, D | Shared embedding gather `[248320,2560]`; embedding RMS `[2560]`, then `fc_embedding [2560,2560]`. Whole-row residual RMS `[10240]`; reshape four streams and apply `fc_hidden [2560,2560]` to each. Add the same projected embedding to each stream. | Initial `H [C,4,2560]`. |
| Attention HC | Grouped RMS `[10240]` with group width 2560; down `[320,10240]`, SiLU after division by 4; up `[10240,320]`, sigmoid; weighted mean over four normalized streams. Injection `[4,10240]`, `2*sigmoid(projection/4)`. | Mixed attention input `[C,2560]`, injection `[C,4]`, retained `H`. |
| Attention projections | Q `[12288,2560]`; reshape `[C,24,512]` and split each head into Q/gate halves of width 256. K/V each `[512,2560]` -> `[C,2,256]`. Q/K RMS weights `[256]`; positional rotation of Q/K. | Q `[C,24,256]`, gate `[C,24,256]`; append position-tagged K/V. |
| Indexer/select | QK `[640,2560]` -> Q `[C,4,128]`, raw K `[C,128]`; Q RMS `[128]` and rotation. Complete each group of four visible raw keys by FP32 mean, cast, K RMS `[128]` and rotation at block start. Score sums four ReLU query/key dots divided by sqrt(128); select up to 512 complete blocks and expand their four tokens plus a causal tail of at most 3. | Selection `[C,2051]` with invalid padding; pooled-key history and up to three raw carry rows. Native pooling/tie/visibility arithmetic needs equivalence checks. |
| Indexed GQA and combine | Gather selected K/V; causal attention with 24 Q/two KV heads (12 Q per KV), scale 1/sqrt(256). Multiply `[C,24,256]` output by sigmoid gate; flatten to 6144 and apply O `[2560,6144]`. Add injection-scaled result to each retained stream. | Updated `H [C,4,2560]`. |
| MLP HC | Same HC operator shapes as attention, with its separate norm/down/up/injection weights. | MLP input `[C,2560]`, injection `[C,4]`. |
| Routed plus shared MLP | Router BF16 `[512,2560]`; FP32 softmax, top10, normalized selected coefficients. Routed gate/up `[512,1280,2560]` splits into two 640-wide halves; SiLU(gate)*up; down `[512,2560,640]`, weighted sum. Shared gate/up `[640,2560]`, down `[2560,640]`, scalar gate `[1,2560]` with sigmoid. Add shared/routed outputs and inject per stream. | Continuation `H [C,4,2560]`. All 512 expert identities must work; fixed IDs 0–9 are insufficient. |
| Final HC and vocabulary | Dedicated final norm `[10240]`, down `[320,10240]`, up `[10240,320]`, weighted mean without injection. Apply shared output `[248320,2560]` to the last row, then native-compatible greedy argmax. | Last-row token; compatible logits if sampled/cache reuse is supported. Publish continuation for all C rows. |

The HC formulas above are the public topology reference, not a claim that an
unqualified FP32 ONNX composition duplicates the native fused BF16 kernels.
True full NPU execution requires strict NPU placement of norm/nonlinearities,
top-k/select, gathers, pooling, attention, both MLP branches and vocabulary
projection. CPU state control is acceptable; computing indexer/attention on
CPU or the native GPU defines a hybrid stepping implementation. Every extra
cross-platform cut adds dispatch/copy cost and needs its own measured scope.

## Weight preparation and reuse

| Existing asset | Reusable scope / gap |
|---|---|
| `C:\AI\halogen-mtp-npu\v2-dense-mlp-20261004\dense-weights.npz` | Real v2 router and four shared arrays; 24,913,920 decoded bytes, NPZ SHA256 `e1103b576f60a5fbaf1059abd26b37d4bdf967c091f79fc80a8cee0bcae441f3`. Receipt binds checkpoint SHA256 `71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687` and exact header/table identity. |
| `C:\AI\halogen-mtp-npu\top10-routing-20261004\top10.onnx.data` | 196,608,000 FP32 bytes for IDs 0–9. Their decoded equality to v2 is established; this is a fixed routed slice. |
| `C:\AI\halogen-mtp-npu\v2-live-bf16-gather-offline-20261004\v2-live-bf16-gather-top10.onnx.data` | 157,286,400 bytes for 16 live-route experts, with BF16-rounded weights. Strict NPU placement failed; it is neither an exact full bank nor a usable full head. |
| Root-owned real QMoE graph/contract under `server/.local/optimization9h-20261004/qmoe-pack-admission-5306a9a57ecd44d79255fce2cc89378b/` | Latest packed routed-bank candidate. Current QMoE execution fault diagnosis remains separate and unresolved here; no provider qualification is inherited. |
| Older `mtp_fc_hidden.npy`, `qproj_rows0_4.npy`, `expert0_*.npy` | Partial assets without verified current-v2 lineage in this inspection; cannot complete attention/HC/head. |

No complete decoded attention/HC/shared-embedding/output-head assets were
found in the inspected retained receipts. The 31-tensor standalone HGN is
1,523,566,720 bytes and contains only `mtp.*`, excluding both shared matrices.
Their exact current-v2 metadata/encoding must be pinned separately before
preparation. One FP32 vocabulary matrix alone is 2,542,796,800 bytes; config
does not tie embedding and output weights, so do not reuse one as the other.

Extend bounded readers rather than exporting the whole checkpoint or using
`hgn_extract_mtp.py` unchanged. Reuse the integrity binding in
`halogen_npu_v2_sparse.py`; its q4c decoder reads bounded codebook/code/scale
windows. Reuse `halogen_npu_v2_dense_mlp.py` q8g64 layout (u8 code * FP16
scale + FP16 bias per 64) through a bounded row-slice interface. Stream dense
and vocabulary tiles to external data with per-range hashes, byte limits and
before/after source identity. `halogen_mtp_extract.py` streams only `mtp.*`
and does not solve the shared-weight gap. Do not expand all 512 experts merely
to repack them: FP32 routed weights total 9.375 GiB (BF16 4.6875 GiB), before
provider copies, scales, graph and scratch.

## History, native verification and transport

Own private history per model/slot/reset epoch, with logical positions and
checkpoints for K/V, pooled keys, pool phase/carry, continuation and cached
proposal tags. For capacity 262144, BF16 private K/V would total 512 MiB;
65536 pooled 128-wide BF16 rows add 16 MiB, excluding transaction copies and
provider storage. Native pooled capacity/FD ownership remains unresolved;
private storage avoids that dependency only if its initialization and history
semantics are defined.

Treat each full-head ABI `(position,C)` as rewind to the known prefix at
`position`, restore its pool-boundary checkpoint, then append C recomputed
rows. Reject unknown prefixes. At target base P, a cached first proposal
already represents head row P-1; offset 1 writes P. Native verification commits
`k=a+1` target rows. Normal accepted replay rewinds to P and recomputes rows
`P..P+k-1` using accepted target residuals and shifted tokens
`[draft1,...,draft_a,correction]`, returning the next cached proposal. EOS and
adaptive suppression can skip replay. Qualify reset, suppression/resumption,
all pool phases, partial acceptance and multirow/bootstrap paths. The existing
24-case synthetic schedule check proves only its positional ledger/grouping.

With the retained wrapper, read raw residuals from `model+0x6d0`, publish all C
continuation rows there and set `model+0x5c=C`; a token-only result is
insufficient. Greedy scope must invalidate incompatible native logits tags
`+0x60/+0x64`; sampled use needs compatible logits/sampling. Target commit
at `0x17def00` and replay at `0x17dcc90` remain native. An EP failure after
private advancement needs proven native reset/replay before GPU fallback or a
clean abort of the owned request, not a GPU call with stale head history.

A persistent Windows NPU host needs a versioned, bounded transport carrying
tokens, position, slot/epoch, raw residual rows, continuation and result.
Scalar input+output residual traffic is 40,960 bytes; 8192-row bootstrap is
160 MiB in plus 160 MiB out. No HIP-to-Windows-EP zero-copy import is established.
Keep local attention/cache state inside that host to avoid per-stage WSL cuts.

## Small implementation sequence and promotion gate

The separate [complete-MLP quality publication source](halogen-mtp-quality-publication-source-20261004.md)
now supplies a disabled-by-default, bounded detour for the shortest eventual
acceptance check. Native MLP runs once before any explicit candidate replaces
its complete output; all native head state and verification remain in use.
That source is unbuilt and requires root-owned transport/runtime qualification.
It can evaluate a partial offload before constructing the full private head,
but its doubled MLP execution cannot establish a speedup.

1. Pin shared-weight metadata and actual runtime mode/norm convention; make a
   canonical decoded stage reference with explicit casts, positions and ties.
2. Prepare bounded dense/shared vocabulary assets and the complete routed bank,
   preserving real-v2 lineage. Resolve the root-owned QMoE fault first.
3. Qualify the actual missing operator shapes and strict NPU placement, then
   assemble the stage contracts above. Record provider partitions and all
   local dispatch/copy costs rather than calling a partially placed graph full
   NPU. Start with count1 and then qualify replay/bootstrap batches.
4. Add private history rewind plus the native full-head transport/publication
   adapter. Retain the native greedy verifier/output controller and qualify
   reset, skipped replay, failure recovery and every acceptance/pool case.
5. Use root-owned guarded matched runs to compare draft proposals, acceptance,
   PP/decode, complete head latency and cleanup before any promotion.

The instrumented native count1 head mean is 3.32356 ms (73 calls), including
input transforms, layer48, vocabulary projection, argmax and synchronization;
it excludes 42 multirow calls. This is an approximate complete replacement
budget, not an uninstrumented guarantee. Native MLP's separate mean is
0.404612 ms. The fixed-top10 initializer-backed NPU expert graph already costs
1.504985 ms before transport/shared/router/attention/head work. These results
do not establish full-head feasibility or speedup.

Extra INT4 requantization has no demonstrated route to higher draft acceptance.
V2 already raises 18 dense MTP tensors to q8g64, while routed q4c is a
non-affine codebook encoding whose nibbles cannot simply be copied as affine
INT4. Requantization adds error and can change routing, attention selection
and vocabulary ranking. The retained complete-MLP comparison already has
maximum errors .00838/.00879 and 1453/1432 final BF16 bit mismatches; BF16 ABI
also does not promise exact BF16 NPU arithmetic. Approximate proposals remain
valid candidates for native verification, but only matched acceptance and
latency measurements can establish whether the tradeoff helps. No acceptance
improvement follows from smaller weights or a routed subgraph's own gate.
