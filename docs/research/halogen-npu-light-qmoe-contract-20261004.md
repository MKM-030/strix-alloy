# Light QMoEBf construction and packing contract

Date: 2026-10-04. Source-only investigation; no provider/device enumeration,
session creation, conversion execution, checkpoint decoding, compilation or
hardware launch was performed.

## Result

There is now a concrete AMD 1.8 export and conversion contract for building
`com.ryzenai::QMoEBf` with persistent, routed expert weights. It is substantially
more useful than the installed DLL's operator-name strings. The contract is
**not yet sufficient to qualify Halogen's 512-expert/top10/2560/640 MTP MoE**:
the installed Light runtime's expert/top-k/activation limits, compatible packed
kernel inventory, and SDK-to-WinML version mapping remain unverified. The
packing callable is not installed in the searched local runtimes.

The public converter supplies genuine source for INT4 input formatting, tile
packing, expert ordering and `.pb.bin` metadata. No guessed node should be
created from binary strings. No complete-head prototype was prepared.

## Primary sources and receipts

1. [AMD's GPT-OSS NPU article, March 16, 2026](https://www.amd.com/en/developer/resources/technical-articles/2026/accelerating-gpt-oss-20b-on-amd-ryzen-ai-npus.html)
   documents BF16 activations, INT4 expert weights, CPU routing/grouping and
   selected expert linear work on the NPU. Setting both
   `hybrid_opt_qmoe_dynamic_experts` and `hybrid_opt_qmoe_num_dynamic_layers` to
   `"0"` keeps all expert weights resident in memory. Its GPT-OSS example is
   32 experts/top4; its dynamic-loading settings are not target512/top10
   support evidence. "Resident in memory" does not establish on-chip NPU SRAM
   residency or an absence of host/device copies.
2. [AMD 1.8 hybrid OGA documentation](https://ryzenai.docs.amd.com/projects/WinML/en/stable/hybrid_oga.html)
   links the official package index. The older
   [AMD conversion flow](https://ryzenai.docs.amd.com/en/1.3/hybrid_oga.html)
   names `onnx_utils partition` and `postprocess hybrid_llm`, and the resulting
   ONNX, weights and protobuf sidecars.
3. [Official AMD ryzenai-onnx-utils 1.8.0 wheel](https://pypi.amd.com/ryzenai_llm/1.8.0/windows/simple/ryzenai-onnx-utils/ryzenai_onnx_utils-1.8.0-py3-none-win_amd64.whl)
   is 998,177 bytes. Whole-wheel SHA256:
   `48a6e544d81208f8fecb9a5e1b5249da7bd1ee7ab212f093039e5f80085a6fd1`.
   It was inspected as ZIP source, without installing or importing its code.
4. [Official AMD Dynamic Dispatch 1.8.0 wheel](https://pypi.amd.com/ryzenai_llm/1.8.0/windows/simple/ryzenai-dynamic-dispatch/ryzenai_dynamic_dispatch-1.8.0-py3-none-win_amd64.whl)
   is 747,736,247 bytes. The index advertises SHA256
   `8988620998c23a0d1a71bf2ced9a5287bc6641133ad38b67900fa4c546e7a8e4`;
   that whole-wheel hash was **not recomputed**. Only HTTP206 ranges for ZIP
   metadata and selected C++ source entries were fetched: 171,554 bytes in the
   first extraction and 146,906 in the second. Entry CRC32 values were verified.
   No native library or transaction binary was downloaded or executed.
5. [Official AMD GPT-OSS 1.8 export](https://huggingface.co/amd/gpt-oss-20B_eager_rai_1.8.0_npu_16K/resolve/bcbb238a3e7e1c11fcac9850bde957e34eb51ebd/model_npu_eager.onnx),
   pinned at `bcbb238a3e7e1c11fcac9850bde957e34eb51ebd`, is 305,470 bytes.
   Graph SHA256:
   `5d8a66e1ddd734af22c2f0da56ee60a48a688113d3e7cb9ed25b6135528b6beb`.
   Only graph metadata was parsed using ONNX; no external weight blobs were
   fetched. It contains 24 `com.ryzenai::QMoEBf` nodes, domain opset1.

Source entries and their hashes are retained under the new ignored directory
`server/.local/optimization9h-20261004/qmoe-source-only/`. Receipts are
`onnx-utils-receipt.json`, `receipt.json` and `dd-extra-receipt.json`.
The most important source paths inside the wheels are:

| Package | Source path | What it establishes |
|---|---|---|
| ONNX Utils | `passes/normalize_qmoe.py` | Original input slots, INT4 zero-point defaults and block limits |
| ONNX Utils | `passes/llm/eager/qmoe.py` | BF16 activation wrapping; FLOAT/BFLOAT16 router acceptance in the conversion pass |
| ONNX Utils | `passes/llm/add_npu_weights/qmoe.py` | Empty original constants, added packed input and derived attributes |
| ONNX Utils | `transform/hybrid_llm.py:427` | Per-expert arrays, packer invocation and combined expert stride |
| ONNX Utils | `passes/llm/jit.py:136` | Offloaded packed weights, alignment and metadata binding |
| ONNX Utils | `proto/external_data_pb2.py` | Actual serialized external-data protobuf descriptor |
| Dynamic Dispatch | `ops/ops_common/matmulnbits_pack_const.cpp:75` | Python packing return values |
| Dynamic Dispatch | `ops/ops_common/matmulnbits_pack_impl.cpp:29` | Low/high nibble order, integer offset, transposes and offline packing |
| Dynamic Dispatch | `ops/ops_common/attributes.hpp:94` | Attribute translation, block32/128 and max_m4096 |
| Dynamic Dispatch | `ops/llm_ops/mladfmatmulbias/mladfmatmulbias.cpp:158` | XRT disabled for the packer; offline export avoids BO creation |
| Dynamic Dispatch | `ops/llm_ops/mladfmatmulbias/matmulbias_tiling/matmulbias_tiling.cpp:136` | Exact or enclosing compiled K/N shape selection |

Dynamic Dispatch sources reside under
`ryzenai_dynamic_dispatch/include/ryzenai/dynamic_dispatch/` in its wheel;
ONNX Utils paths reside under `ryzenai_onnx_utils/`.

## Current 1.8 input and attribute construction

The source converter normalizes the original QMoE to exactly14 inputs and one
output. It then adds one packed input at index14. These are zero-based slots:

| Slot | Original meaning | Exported QMoEBf representation |
|---:|---|---|
| 0 | Activation | BF16 input |
| 1 | Router values | FLOAT or BFLOAT16 accepted by eager pass; example uses BF16 |
| 2,3,4 | FC1 weights, scales, bias | Same-dtype `[0]` empty initializers |
| 5,6,7 | FC2 weights, scales, bias | Same-dtype `[0]` empty initializers |
| 8,9,10 | Optional FC3 weights, scales, bias | Empty optional names in the supported two-FC export |
| 11,12,13 | FC1,FC2,FC3 zero points | Empty initializers or optional names after packing |
| 14 | Added combined expert weights | INT8 flat tensor; becomes `[0]` after provider sidecar offload |

`npu_only=True` changes the operation type to `QMoEBf`. The pass copies the
original attributes, then adds `num_experts`, `num_fc`, and, for each FC,
`packed_expert_sz_FC*`, `k_FC*`, `n_FC*`, `block_size_FC*`. These values come
from the source arrays and packer result; packed byte sizes must not be guessed.
The example additionally records `mladf_version="v2"`.

The 1.8 example first node is `/model/layers.0/moe/QMoE_24_0`. Its attributes are:

| Attribute | Observed value |
|---|---:|
| `activation_type` | `swiglu` |
| `activation_alpha`, `activation_beta`, `swiglu_limit` | 1.7020000219345093, 1.0, 7.0 |
| `swiglu_fusion`, `expert_weight_bits`, `block_size` | 1,4,32 |
| `k`, `normalize_routing_weights`, `use_sparse_mixer` | 4,1,0 |
| `num_experts`, `num_fc` | 32,2 |
| `k_FC1`, `n_FC1`, `block_size_FC1` | 2880,5760,32 |
| `k_FC2`, `n_FC2`, `block_size_FC2` | 2880,2880,32 |
| `packed_expert_sz_FC1`, `packed_expert_sz_FC2` | 10598400,5326848 bytes |

The router reshape is absorbed by the converter: its kernel treats the last
dimension as expert count and flattens leading dimensions. The graph carries
reshape provenance attributes; this does not establish every possible input
rank for the installed runtime.

### Two FCs and activation policy

The current AMD packer explicitly asserts **exactly two layers: gate_up and
down**. Although its loop and attribute writer include optional FC3 handling,
the final assertion rejects three nonempty FC matrices. Do not read that
scaffolding as supported `num_fc=3`.

Halogen's existing source builder uses concatenated `[gate; up]` rows and
`silu(gate)*up`. The AMD graph is the GPT-OSS interleaved SwiGLU example with
different alpha/beta/clipping. The source conversion pass copies those
attributes; it does not supply the QMoEBf runtime implementation or establish
which standard-SwiGLU settings and row layout it actually executes. A row
reorder is a construction requirement if interleaved fusion is required.
Dynamic Dispatch's separate `wts_interleaved` gate/up option is **not enabled
by this QMoE preprocessing pass** and must not be confused with the QMoE
activation-layout attribute.

## Exact source-array and offline packing contract

For each expert and FC, the converter supplies:

- weights: UINT8, logical `[N,K/2]`, low nibble for even K and high nibble for
  odd K;
- scales: FLOAT32 `[N,K/block_size]`; per-channel `[N]` scales are repeated
  into block32 scales by the converter;
- zero points: UINT8 `[N,ceil(ceil(K/block_size)/2)]`, low nibble for the first
  block in each byte;
- bias: FLOAT32 `[N]`; zero arrays must still be supplied to this source path.

For a missing original zero-point tensor, normalization creates packed `0x88`
values. The converter requires `expert_weight_bits=4`; attribute translation
requires block32 or block128. A three-dimensional scale array determines its
own block size from `K/scale_K`; use a supported divisor and compatible shapes.

The callable is
`ryzenai_dynamic_dispatch.matmulnbits.matmulnbits_pack_const_float32(weights,
bias, scales, zero_points, Attributes)`. Per expert, the source sets:
`K`, `N`, `lora=False`, `mladf_version`, `asymmetric_quant=True`,
`bias_en=any(bias)` and `block_size`. `Attributes.build_attr()` translates
`mladf_version` to `op_version`, block size to `group_size`, and defaults
`max_m=4096`, `default_shape=1`. Current common source accepts versions
`v2`, `aie4_v1`, `flat`; use the real1.8 `v2` example rather than the stale
default `v1` branch.

The C++ formatter transposes input weights to `[K,N]` INT8, applying
`nibble-8` for **both weights and zero points**, then transposes scales to
`[K/block_size,N]`. In1.8 the earlier v2 exception to this offset is commented
out. It creates the matmul operator with `load_xrt=false` and exports constants
with `is_online=false`; that path returns host bytes without creating XRT BOs.
This is source evidence about this packer, not permission to invoke it during
the source-only investigation.

The return tuple is `(packed_uint8_array, total_bytes, padded_K, padded_N)`.
Tile packing and BF16 metadata conversions are implemented in the retained
`matmulbias_weights_*` sources. The ONNX Utils caller records original K/N and
discards the returned padded dimensions; matching runtime shape selection is
therefore material. Defaults permit weight padding. The compiled kernel
inventory, selected version and group size decide the enclosing shape; source
does not promise arbitrary K/N kernels.

For each expert e,1.8 combines:

`packed_FC1[e] || packed_FC2[e] || zero_padding`

where padding makes each combined expert stride a multiple of65536 bytes.
`packed_expert_sz_FC2` includes that tail padding. Experts remain in index
order0..E-1. The resulting flat INT8 initializer name ends in
`.gate_up_down.packed.qexperts`.

Halogen q4c variant2 is not ordinary affine INT4 storage. The frozen decoder
source uses a16-entry FLOAT32 codebook and FP16 scale per32 K values:
`weight=codebook[nibble]*scale`. Its low/high nibble order agrees with the
packer, but copying codes as `nibble-8` need not preserve weights. Later
conversion must either establish an affine codebook mapping or approximately
requantize bounded decoded rows into this INT4 contract. No checkpoint header
or payload was decoded here. Approximate draft arithmetic is acceptable when
native target verification preserves final output correctness; internal FP32
MLP equality is not the acceptance criterion.

## Provider sidecar contract and residency

`jit.py` constructs a protobuf Header, writes packed bytes to `<stem>.bin`,
and serializes its metadata to `<stem>.pb.bin`. Offloaded QMoE regions begin
at65536-byte-aligned file offsets. Packed initializers are replaced by `[0]`
tensors so normal ONNX loading does not load a second copy. The metadata binds
by **node name**, with `Operator.data` ordered over eligible packed constants;
it is not a normal ONNX `external_data` initializer binding.

Recovered descriptor fields and tag numbers:

| Message | Fields |
|---|---|
| `Tensor` | `offset:uint64=1`, `size:uint64=2`, `shape:repeated int64=3`, `data_type:int32=4` |
| `Operator` | `op_type:string=1`, `data:repeated Tensor=2` |
| `Layer` | `offset:uint64=1`, `size:uint64=2`, `operators:repeated string=3` |
| `OpMetadata` | `max_npu_buffer_size:uint64=1`, `first:string=2`, `last:string=3` |
| `ExternalData` | `filename:string=1`, `npu:bool=2`, `gpu:bool=3`, `embedding:bool=4`, `qmoe:bool=5` |
| `Header` | `operators:map<string,Operator>=1`, `op_metadata:map<string,OpMetadata>=2`, `layers:repeated Layer=3`, `external_data:ExternalData=4` |

The original AMD resident export config supplies the provider option
`external_data_file="GPT-OSS-npu.pb.bin"`, token backend `"npu"`, and the two
zero-valued dynamic-loading settings. QMoE offload is separately marked by
`external_data.qmoe`; `external_data.npu` represents JIT NPU offload. These
flags are not interchangeable evidence of resident selected expert BOs.

## Older export and compatibility boundary

The earlier official
[GPT-OSS export](https://huggingface.co/amd/gpt-oss-20b-onnx-ryzenai-npu/resolve/dc9ddd198af20e2fa2337186a84fea4cfd799528/GPT-OSS-npu.onnx)
at `dc9ddd198af20e2fa2337186a84fea4cfd799528` is281,714 bytes, SHA256
`063a528e9fe5d5331b417b1e839b920bfd548f951ba1e5b4b5dc4b00bc14b3b2`.
It instead has11 original slots plus **two** packed expert initializers at
11,12; its FC1/FC2 sizes are10600448/5300224, and it has no `mladf_version`
attribute. This is an actual version difference, not a universal13-input
schema. Do not mix its graph interface with1.8 packed bytes.

Installed Light DLL SHA256 remains
`ccc3bd0c2a8f519f9cd5fb112491785918810819f80c804302f717d2a93456ec`,
Windows package `MicrosoftCorporationII.WinML.AMD.NPU.EP.1.8_1.8.75.0_x64__8wekyb3d8bbwe`.
An official compatibility mapping to the Python SDK1.8.0 graph/sidecar ABI was
not recovered.

## Target512/top10 status and next preparation gate

| Requirement | Evidence/status |
|---|---|
| 512 persistent experts | Converter loops over arbitrary array E and adds `num_experts=E`; no Python512 rejection. QMoEBf runtime bound and persistent buffer ownership are missing. |
| Top10 selected at runtime | `k` is copied without a Python top10 rejection; public export proves top4. Installed runtime limit, router selection/aggregation semantics and tie policy are missing. |
| Width2560, intermediate640 | Source arrays would be FC1 `[512,1280,1280]` packed and FC2 `[512,2560,320]` packed. Logical FC1 K/N=2560/1280; FC2=640/2560. All K values divide32 and128. Matching compiled enclosing shapes and safe runtime cropping remain unverified. |
| Two-FC standard SiLU gate/up | Two FCs satisfy packing assertion; gate/up row reorder and installed activation behavior still require evidence. Separate FC3 is rejected by the current AMD conversion path. |
| q4c repack | Exact source codebook/block contract known; affine mapping or approximate requantization decision is still needed. No payload was read. |
| Local offline packing dependency | `ryzenai_dynamic_dispatch`/packer not found under `C:/AI/runtimes`, including the Light environment. No package was installed. |
| Full MTP draft/target integration | Unchanged: native target verification, state handling, final output equality and measured acceptance/round-trip throughput are still required. |

Before any graph construction, obtain the matched SDK/WinML ABI contract and
installed compiled K/N inventory for the chosen version/group size, plus
512/top10 and activation support evidence. The recovered source makes an
official offline packer a concrete dependency rather than a guessed format.
Its install/build would be separate authorized work; no installation occurred.

A later CPU-only preparation can stream one expert at a time, pack FC1 then
FC2, append aligned bytes directly to disk, and write the exact Header and
15-slot graph. Avoid calling the stock whole-layer pass, which retains all
packed expert arrays and concatenates them into another full buffer. One
logical expert has4,915,200 weights: FP32 decoding is18.75MiB, raw nibble
storage2.34375MiB, block32 FLOAT32 scales0.5859375MiB and packed zero points
0.0732421875MiB. All512 raw nibble weights total1.171875GiB; full FP32 expansion
would be4.6875GiB. Padding and packer/library resource memory are additional
and cannot be bounded numerically until the actual compiled shapes are known.
The future design should reject per-expert padded outputs over64MiB and use
one short-lived CPU worker at a time with a256MiB incremental-memory cap;
these are proposed enforced ceilings, **not measured peaks**. Dependency
loading must be measured independently before accepting that cap.

The existing22GiB admission/18GiB continuous floors and Light guard remain
frozen. Any later native timing gate is owned by the root agent. A successful
EP attribution alone will still not prove internal NPU placement or a useful
draft path.

## Frozen artifact verification

Read-only hash checks still match:

- Light probe: `401ea8c9c83758568f19b7e07e3bf128b2d194d79fc01861355b53ca0ad89100`.
- Light guard: `0a29d7ef6c7c286de19dea19084e2413af6b97bdcd8dad35af5163e08b14cedc`.
- Previous route report: `01361ef1b0b6b5a8f254de303f0da195e9c01ce496dd013e124357ca87f24a3d`.
- q4c decoder: `fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce`.

No alternative-provider test was added and no existing artifact was edited.
