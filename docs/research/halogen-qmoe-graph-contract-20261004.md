# Halogen QMoEBf graph and resident-bank candidate

The public builder `scripts/benchmarks/halogen_qmoe_graph.py` constructs exactly one `com.ryzenai::QMoEBf` node, domain opset1, and an official AMD Header sidecar against a completed external bank. It imports ONNX/protobuf only for static serialization/checking. It does not import DynamicDispatch or ONNX Runtime, invoke a provider/device, pack weights, decode a model, or read/hash the bank payload. This is a runtime candidate, not a qualified NPU draft.

Root's two guarded Light candidate versions completed with zero calls each.
At 05:59 UTC, QMoEBf was not registered. At 06:03 UTC, explicit custom-op
registration from the same pinned DLL resolved that first gate, but ORT 1.25.2
rejected custom-op version27 during initialization. These are distinct
registration and API-compatibility failures; neither tests 512-expert/top10
execution support. Cleanup passed in both. No NPU latency, numerical result,
residency, acceptance or speed gain exists.

## Exact source and pack pins

The retained [official AMD ONNX Utils1.8.0 wheel](https://pypi.amd.com/ryzenai_llm/1.8.0/windows/simple/ryzenai-onnx-utils/ryzenai_onnx_utils-1.8.0-py3-none-win_amd64.whl) SHA256 is `48a6e544d81208f8fecb9a5e1b5249da7bd1ee7ab212f093039e5f80085a6fd1`. Sources under `server/.local/optimization9h-20261004/qmoe-source-only/` establish:

| Source | Contract |
|---|---|
| `ryzenai_onnx_utils__transform__hybrid_llm.py:480` | Two FCs, expert index order, FC1 then FC2, 65536-byte expert stride, tail included in FC2 size; original K/N attributes retained |
| `ryzenai_onnx_utils__passes__llm__add_npu_weights__qmoe.py:78` | Original14 inputs emptied as same-dtype `[0]` initializers, one packed input appended, derived per-FC attributes, `npu_only=True` -> QMoEBf |
| `ryzenai_onnx_utils__passes__llm__eager__qmoe.py:29` | BF16 activation/output, FLOAT or BFLOAT16 router accepted |
| `ryzenai_onnx_utils__passes__llm__jit.py:136` | Packed input offloaded to bank, replaced by INT8[0], metadata bound by node name, QMoE mmap alignment |
| `ryzenai_onnx_utils__proto__external_data_pb2.py` | Exact serialized Header schema; source SHA256 `11535c7348e169fd16fbda6da598281f8ee68b190f491b2e426358216f450d33` |

The builder extracts the serialized protobuf descriptor from that pinned Python source using AST, without importing/executing the AMD module. Google protobuf constructs and serializes the official message class.

The complete staged [AMD DD1.8.0 wheel](https://pypi.amd.com/ryzenai_llm/1.8.0/windows/simple/ryzenai-dynamic-dispatch/ryzenai_dynamic_dispatch-1.8.0-py3-none-win_amd64.whl) SHA256 is `8988620998c23a0d1a71bf2ced9a5287bc6641133ad38b67900fa4c546e7a8e4`. Native packer pin: `38814ad69d2233758b76bf82db922f2e674c0d01aace756ace066135cbf4aaab`. Root's completed owned offline packing receipt is `server/.local/optimization9h-20261004/qmoe-pack-admission-5306a9a57ecd44d79255fce2cc89378b/pack.json`; this builder did not execute that packer.

## Bank geometry and memory

| Region per expert | Logical K/N | Packer padded K/N | Bytes |
|---|---|---|---:|
| FC1 gate/up | 2560/1280 | 2560/2560 | 4,198,400 |
| FC2 down | 640/2560 | 768/3072 | 1,597,440 |
| FC2 tail | — | 64KiB expert alignment | 36,864 |
| Combined expert stride | — | — | 5,832,704 |

`packed_expert_sz_FC1=4198400`; `packed_expert_sz_FC2=1634304`, including the tail. The node's `k_FC1/n_FC1` and `k_FC2/n_FC2` remain the logical dimensions. Substituting padded dimensions would differ from the official converter.

The512 bank is **2,986,344,448 bytes =2.78125GiB**. Its expert e starts at `e*5832704`; FC2 starts another4198400 bytes into the expert. The completed synthetic bank SHA256 is `05283a60ce7858fdfa93d46ce84e86a5a38d5bbe46631e8571d2ff632890365f`. The builder validates receipt geometry and file size and records the owned digest; it deliberately does not reread the3GiB payload. The original raw sum without expert tails is18MiB smaller and is not the converter's bank layout. Runtime allocations and process memory are additional and unmeasured here.

## Graph, attributes, and sidecar

Graph inputs are `x:BFLOAT16[1,2560]` and `router:FLOAT[1,512]`; output is `y:BFLOAT16[1,2560]`. There are no Cast nodes. Router values are supplied by the caller; top-k/aggregation semantics remain a runtime qualification item.

| Slot | Input |
|---:|---|
| 0,1 | x, router |
| 2,3,4 | Empty UINT8 FC1 weights, FLOAT scales, FLOAT bias |
| 5,6,7 | Empty UINT8 FC2 weights, FLOAT scales, FLOAT bias |
| 8,9,10 | Empty optional names for FC3 |
| 11,12 | Empty UINT8 FC1/FC2 zero points |
| 13 | Empty optional FC3 zero-point name |
| 14 | Empty INT8[0] initializer ending `.gate_up_down.packed.qexperts` |

Attributes: `num_experts=512`, `k=10`, `num_fc=2`, `expert_weight_bits=4`, `block_size=block_size_FC1=block_size_FC2=32`, `mladf_version="v2"`, logical K/N and the packed sizes above, `normalize_routing_weights=1`, `use_sparse_mixer=0`.

The proposed standard-SwiGLU profile is `activation_type="swiglu"`, `swiglu_fusion=1`, `activation_alpha=1.0`, `activation_beta=0.0`, `swiglu_limit=3.4028234663852886e38` (largest finite FLOAT32), with interleaved gate/up rows. This is intended to express SiLU(gate)*up without a practical clipping limit, **not proof that installed QMoEBf implements those semantics**. The converter only copies these activation attributes. Synthetic zero weights cannot verify gate/up ordering or activation arithmetic. A nonzero fixture and later native target verification must measure suitability; internal MLP FP32 parity is not required for an approximate draft.

The Header uses `operators[node.name].data[0] = {offset:0,size:2986344448,shape:[2986344448],data_type:3}` (INT8). `external_data.filename` is the sibling bank basename; `qmoe=true`, `npu/gpu/embedding=false`, reflecting QMoE offload with JIT disabled. `op_metadata["QMoEBf"]` first/last equal the node name and max NPU buffer size is0. One Layer records the node with zero offset/size, matching the converter's JIT accounting: `save_qmoe` does not add bank bytes to Layer.size. This is AMD provider metadata, not standard ONNX external_data.

[AMD's pinned1.8 export configuration](https://huggingface.co/amd/gpt-oss-20B_eager_rai_1.8.0_npu_16K/resolve/bcbb238a3e7e1c11fcac9850bde957e34eb51ebd/genai_config.json) supplies `external_data_file`, **`hybrid_opt_token_backend="npu"`**, and both `hybrid_opt_qmoe_dynamic_experts="0"` and `hybrid_opt_qmoe_num_dynamic_layers="0"`. [AMD's memory-strategy article](https://www.amd.com/en/developer/resources/technical-articles/2026/accelerating-gpt-oss-20b-on-amd-ryzen-ai-npus.html) describes both zero settings as keeping expert weights resident in memory. These options do not prove this512/top10 candidate's runtime support, NPU placement, BO ownership, SRAM residency, or lack of copies.

## Execution and manifest contract

Run static construction with an ONNX/protobuf-capable Python, placing output next to the bank:

```powershell
& C:/AI/runtimes/winml-npu/Scripts/python.exe -B scripts/benchmarks/halogen_qmoe_graph.py `
  --pack-receipt server/.local/optimization9h-20261004/qmoe-pack-admission-5306a9a57ecd44d79255fce2cc89378b/pack.json `
  --proto-source server/.local/optimization9h-20261004/qmoe-source-only/ryzenai_onnx_utils__proto__external_data_pb2.py `
  --output server/.local/optimization9h-20261004/qmoe-pack-admission-5306a9a57ecd44d79255fce2cc89378b/halogen-qmoe-512-top10.onnx
```

The builder refuses to overwrite outputs and writes `.onnx`, `.pb.bin`, and `.contract.json`. Manifest schema `halogen_qmoe_graph_v1` contains flat graph/header paths and SHA256 fields; bank path/bytes/owned SHA256; builder/protobuf/receipt pins; geometry; exact node inputs/attributes; I/O; and candidate provider options. `bank_hash_verified_by_builder=false` distinguishes stat/receipt validation from root's bank hashing. `activation_semantics_verified`, `shape_padding_execution_verified`, `sdk_light_abi_verified`, `provider_inference`, `full_mtp`, `acceptance_qualified`, and `speed_gain` remain false. The manifest's own SHA is supplied separately when pinned by a probe.

Targeted static checks established alignment and >2GiB protobuf values, one15-slot node, empty initializers, exact BF16/FLOAT/BF16 shapes, official Header round-trip and rejection of an unaligned receipt. Those static checks invoked no provider or inference. The subsequent root-owned strict Light attempt is recorded below; neither low nor high expert IDs reached execution. A successful all-zero output would only test admission and bounded zero-output behavior. Repeated identical zero experts cannot distinguish correct routing/addressing from stale or misrouted choices, so routing and addressing remain unqualified. Standard-SwiGLU arithmetic, real q4c requantization quality, complete-head state handling, acceptance, and speed also remain unqualified.

## Guarded strict Light admission — 05:59 UTC / 07:59 Berlin

The pinned ORT 1.25.2 runtime validated graph/header/manifest, source and helper
pins, the installed Light DLL and all twelve files in its verified complete
copy. It initialized WinML, registered `RyzenAILightExecutionProvider` and
selected exactly one advertised Light NPU device. CPU fallback and automatic
acquisition were disabled. The candidate supplied the frozen header through
`external_data_file`, `hybrid_opt_token_backend="npu"`, and both zero-valued
dynamic-loading options documented above.

The single session-creation attempt failed at `strict_session_admission`:

```text
Fatal error: com.ryzenai:QMoEBf(-1) is not a registered function/op
```

`call_count=0`, `completed_calls=0`, and the call list is empty. The recorded
1.8323 ms is elapsed host time for the failed session construction; it is not
NPU kernel latency or an inference benchmark. No numerical or profile
attribution gate was reached. The retained profile file is empty; stderr also
records `Init provider bridge failed` and that no model was loaded for profiling.
Those diagnostics do not isolate a registration mechanism or establish an
unsupported 512/top10 geometry. This first receipt supplies no fallback or
inference result. The changed candidate below added explicit custom-op
registration and reached a distinct compatibility gate.

Cleanup records session/device/options released before unregistration,
provider unregistration, DLL-directory closure and bootstrap shutdown all
successful, with no cleanup errors. Root's guard records child exit1 and
`owned_job_closed=true`. Child physical/commit headroom minima were
48.145805 / 202.801899 GiB; guard-observed minima were 48.172482 / 202.823715 GiB.
Both observation scopes held the 18-GiB floor. The failed receipt is retained
without replacement. Full live NPU MTP remains incomplete, and the latest
stock baseline remains 1768.47 PP-only / 46.355 MTP decode / 60% acceptance.
No new end-to-end gain is qualified.

Artifacts are under
`server/.local/optimization9h-20261004/qmoe-light-admission-d8498f570cb943099e06eb261e3fd30a`.
The launched probe source pin is
`36f8e56491748a7620664919272ca14c9712a2b798b0c35fa3364a3364c44819`;
Light DLL pin is
`ccc3bd0c2a8f519f9cd5fb112491785918810819f80c804302f717d2a93456ec`.
The [nine-hour evidence JSON](../benchmarks/halogen9h-optimization-20261004.json)
retains source/artifact pins, exact error, cleanup flags and memory scopes.

| Retained evidence | SHA256 |
|---|---|
| `admission.json` | `0ef02e663b06d39a9b698feaa24530fdd66b15ecc5ade913c9a410437d4aa43b` |
| Guard `result.json` | `f6312204ddc51941abc83efbf67ade8e62399eec1086d53a45bd7707b33d98fd` |
| `identity.json` | `e9fad8c3591bc5c06d76fe9acaaf2b9d37970945ee69ca60a808a34f12c62b9d` |
| `memory.jsonl` | `f5b22162720b2a9e608d863386a84479b460d33d9ece4391be8de84492b33fbb` |
| `stderr.txt` | `c975c713cf0860ea1dea8dc7282ca5f2cd6adfcf0a7488ef114f411901fd9cfc` |

Publication inspected saved evidence only; no source change, hardware call or
retest was performed.

## Changed candidate with custom-op registration — 06:03 UTC / 08:03 Berlin

Root changed the probe to register custom operators with the same pinned
`onnxruntime_providers_ryzenai.dll`, then ran one separate guarded admission.
The source pin was
`deae67c055150c868237dcd71f66408903dc5a4bfad06e981751dbac63120225`.
Graph/header/manifest and provider-copy pins remained identical to the first
attempt. The receipt records the custom-operator-registration stage and exact
custom-op library path/hash. It selected exactly one Light NPU device with
CPU fallback disabled.

The missing-operator error was resolved. The sole session-creation attempt
then failed in `CustomOpKernel` under ORT 1.25.2:

```text
Unsupported version '27' in custom op 'QMoEBf
```

Both attempted and completed call counts remain zero. The 10.2292 ms elapsed
host initialization time is neither NPU kernel latency nor an inference
benchmark. The retained profile has two session events and zero Node events;
there is no executed-kernel attribution. This establishes a custom-op version
compatibility rejection in the selected runtime path, not an unsupported
512-expert/top10 geometry. Shape/padding execution, routing, activation,
weight residency, numerical quality, complete MTP and acceptance are still
unqualified. No unchanged rerun is proposed; compatibility is being diagnosed
separately.

The child again released session/device/options before successful provider
unregistration, DLL-directory closure and bootstrap shutdown. Root's guard
records child exit1 and owned-job closure. Child physical/commit minima were
45.908276 / 200.606339 GiB; guard minima were 45.929825 / 200.626736 GiB.
Both scopes held the 18-GiB floor. The stock baseline remains
1768.47 PP-only / 46.355 MTP decode / 60% acceptance; no end-to-end gain is
qualified, and full live NPU MTP remains incomplete.

The second receipt is retained independently under
`server/.local/optimization9h-20261004/qmoe-light-admission-98114cda0f9c47aab59a379917a2f810`.

| Second candidate evidence | SHA256 |
|---|---|
| `admission.json` | `e2b355ffcc21da892fd87da24defa0a4766c97982f2a341dc327a73937c241a5` |
| Guard `result.json` | `c696da0c598047826d96960e79ca251e38008cff7f1bd17d8d35e4c6bd56b4a2` |
| `identity.json` | `22431446d097ce5b9ba0123ccd28b0e059f7543538cc2555176f3035d04e6301` |
| `memory.jsonl` | `de2796168eaeb24e81fa1f72593bd2476b58cded890c9b9ee9ec6208cc9a104c` |
| `stderr.txt` | `6e1d8320438b6deb858d0015ec921722637562955faab46c0c3001532b1cf54c` |

Both original negative receipts are preserved. This publication made no source
change or runtime call.
