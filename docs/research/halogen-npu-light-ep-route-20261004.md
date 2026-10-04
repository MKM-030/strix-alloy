# Ryzen AI Light EP: a bounded alternative-provider admission route

The installed AMD package includes a real ORT plugin for
`RyzenAILightExecutionProvider`. Its factory exports provide a concrete route
for root to try the existing tiny dynamic-weight graph through Light, with CPU
fallback disabled. Ordinary ONNX operator admission, mutable-weight execution,
internal NPU placement and complete Flash-Next MTP support remain unproven.
This is an alternative provider mechanism, not another VitisAI/BF16 Gather
shape experiment. No provider registration, device query, compilation or
inference was performed while preparing this source and note.

## Exact installed evidence

Package:
`C:/Program Files/WindowsApps/MicrosoftCorporationII.WinML.AMD.NPU.EP.1.8_1.8.75.0_x64__8wekyb3d8bbwe`.
The manifest names Light and points to
`ExecutionProvider/onnxruntime_providers_ryzenai.dll`, separately from its two
VitisAI registrations. The Light DLL is 4,368,688 bytes. Inspection parsed PE
metadata and bounded printable strings from that file; it did not load it.

| Static evidence | What it establishes |
|---|---|
| `CreateEpFactories`, RVA `0x1a98b0`; `ReleaseEpFactory`, RVA `0x1a9b20` | The plugin entry points required by ORT are exported. Actual factory/device availability still needs root admission. |
| `RegisterCustomOps`, `RyzenAI_RegisterCustomOps`, `RyzenAI_RegisterCPUGateCustomOps` | Custom operator registration paths exist. Their exported presence does not specify a graph schema or guarantee NPU execution. |
| `RyzenAI_SetExecutionProviderType`, `RyzenAI_SetSessionOptions`, `RyzenAI_Shutdown` | Additional native control exports exist; this probe does not guess their signatures or invoke them. |
| `RyzenAI_QueryCurrentExecutionProviderPerformanceCounters`, `RyzenAI_QueryExecutionProviderPerformanceCounters` | Native counters are exported; no counter API was called. |
| `com.ryzenai`, `QMoEBf`, `LinearAttention`, `CausalConvStateSplitRmsNorm`, `MatMulNBitsBf` | This DLL contains LLM-oriented custom kernels, including MoE and linear attention. This is stronger evidence than its license-only readme, but is not a supported Flash-Next contract. |
| `hybrid_opt_qmoe_dynamic_experts`, `hybrid_opt_qmoe_num_dynamic_layers`, `hybrid_opt_qmoe_bind_all` | Dynamic-expert controls are present. Accepted values, packing, shapes and residency semantics were not established. |
| `expert_weight_bits`, `is_bfp16`, `bfp16ebs8`, `float16` | Precision/packing paths exist. These names do not establish exact BF16 arithmetic or parity with Halogen q4c weights. |

The DLL's Gather custom path contains the diagnostic
`NPU path for gather not implemented`. Its MoE path requests packed FC1/FC2
inputs and identifies NPU as its required backend. Thus switching provider
names is not evidence that a plain resident-bank Gather becomes an NPU route.
A converted custom MoE kernel could avoid that explicit Gather, but constructing
such a node requires its real schema, supported geometry, precision semantics
and packed artifact format. Those cannot safely be invented from strings.

The Light option namespace is `ep.ryzenailightexecutionprovider.`. The binary
directs callers to pass options through `add_provider_for_devices`, rather
than unprefixed session entries. It also contains fusion-runtime diagnostics
about `external_data_file`, `dd_cache` and metadata files. Those are evidence
of prepared custom/fused artifacts, not proof that every ordinary ONNX graph
must supply those artifacts. The new probe uses empty provider options, with
no guessed VitisAI cache or compiler configuration.

## What the primary documentation supports

[ORT's plugin usage reference](https://onnxruntime.ai/docs/execution-providers/plugin-ep-libraries/usage.html)
documents library registration, factory discovery, exact EP-device selection
and provider options. Registration itself calls the factory and discovers
supported hardware, so even that step remains root-only. The installed DLL's
two factory exports satisfy the static prerequisite for this API route.

[AMD's Windows ML EP example](https://ryzenai.docs.amd.com/projects/WinML/en/latest/winml_ep.html)
shows Python `register_execution_provider_library`, `get_ep_devices` and
`add_provider_for_devices`. Its example selects VitisAI NPU devices; it does
not publish a separate Light ordinary-operator support table. The
[Microsoft provider list](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/supported-execution-providers)
likewise names VitisAI for AMD NPU. This documentation gap does not establish
that Light is unusable; the exact guarded selector is the next bounded check.

For complete LLM deployment, the
[pinned AMD WinML LLM tutorial](https://github.com/amd/RyzenAI-SW/blob/43b2dabe4d1bf084d0421953b134707b8cb7275a/WinML/LLM/README.md)
uses Olive/Quark conversion followed by OGA. Its
[pinned recipe](https://github.com/amd/RyzenAI-SW/blob/43b2dabe4d1bf084d0421953b134707b8cb7275a/WinML/LLM/Phi-4-mini-instruct_quark_vitisai_llm.json)
uses grouped asymmetric uint4 weights, BF16 data and a model-generation pass.
The current
[pinned runner](https://github.com/amd/RyzenAI-SW/blob/43b2dabe4d1bf084d0421953b134707b8cb7275a/WinML/LLM/run_genai_llm.py)
registers AMD providers requested by converted configurations, including RyzenAI.
That establishes a prepared-model route, rather than direct consumption of an
arbitrary Halogen head or its q4c container.

[AMD's OGA reference](https://ryzenai.docs.amd.com/projects/WinML/en/stable/hybrid_oga.html)
documents hybrid and NPU-only modes for Strix/Krackan, prepared runtime
artifacts, and different token/full-fusion context limits. Those example limits
are not a qualification for this 32K Halogen workload or a complete Light MTP
head. No new model, SDK, runtime or driver was downloaded.

## Implemented root admission action

New source:
[halogen_npu_light_ep_admission_probe.py](../../scripts/benchmarks/halogen_npu_light_ep_admission_probe.py).
SHA256 `401ea8c9c83758568f19b7e07e3bf128b2d194d79fc01861355b53ca0ad89100`.
AST syntax parsing passed; the source was not executed.

The probe checks the frozen original helper, retained 710-byte eight-op ONNX
graph, prior CPU receipt, exact A/B input hashes and independent reference
hashes. Explicit arrays and copies remain below 8 MiB; each feed is 246,056
bytes. It performs no checkpoint decode and creates no new graph or weights.
It verifies root's existing complete provider copy against the installed
directory and chooses its pinned Light DLL. It then registers Light directly,
requires exactly one device whose EP name is Light and hardware type is NPU,
disables CPU EP fallback and Python fallback, and attempts one persistent
session. Default replay is A/B warmup followed by A/B measured calls.

The numerical gate preserves `rtol=0.03`, `atol=0.003` from the original tiny
NPU probe and separately reports the stricter FP32 gate. Every profiled ORT
Node must be attributed to Light. Reports retain the stage, advertised devices,
all returned tiny arrays/hashes, failures, partial profile and cleanup outcome.
Nonfinite returned values are serialized as strings and still fail numerical
admission. A successful ORT attribution is not proof that every internal custom
kernel ran on NPU; that needs provider-level evidence.

The new ignored runner is
`server/.local/optimization9h-20261004/run_light_ep_guard.py`, SHA256
`0a29d7ef6c7c286de19dea19084e2413af6b97bdcd8dad35af5163e08b14cedc`.
It adapts `run_first_gemm_guard.py` to exactly one Light stage, with no graph
rebuild or repeated CPU probe. It owns a suspended child through the frozen
Windows job helper, records and verifies its identity, then rechecks admission
before resume. It admits 22 GiB physical/commit headroom, continuously monitors
18 GiB floors and terminal idle GPU/known ports, seals source/helper and retained
model/receipt/manifest/Light DLL hashes, and enforces a maximum 90-second child
deadline. Working directory, stdout, stderr, report and guard evidence all use
a fresh owned output directory. Cleanup closes only its own job and requires
terminal GPU/ports and the final memory floor.

Root can invoke this runner only after the current GPU workload is terminal.
The runner sets `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and `MKL_NUM_THREADS`
to `1` in the child environment. The probe's argument marker and point samples
do not replace that external continuous guard. Both new Python sources were
syntax-parsed only; neither was executed during preparation.

```powershell
C:/AI/runtimes/winml-npu/Scripts/python.exe server/.local/optimization9h-20261004/run_light_ep_guard.py --out <fresh-owned-directory> --npu-timeout 90 --expected-probe-sha256 401ea8c9c83758568f19b7e07e3bf128b2d194d79fc01861355b53ca0ad89100 --expected-runner-sha256 0a29d7ef6c7c286de19dea19084e2413af6b97bdcd8dad35af5163e08b14cedc
```

If registration or exact NPU selection fails, the report identifies the
installed plugin/device mismatch. If strict session admission fails, that
rejects this exact ordinary eight-op graph/shape under Light defaults; it does
not reject every larger or converted custom model. A numerical or attribution
failure cannot qualify speed. Even a pass does not prove resident dynamic-ID
routing: these are selected matrices supplied as runtime inputs, without a
Gather remainder or an on-device expert bank.

A full-head path remains a distinct implementation question. It must preserve
Flash-Next target residual streams, norms/mixing, indexed attention and its
persistent state, shared and routed experts, and embedding/output projection,
then establish a real target-state handoff and accepted-token quality. The
[existing head inventory](halogen-npu-next-step-20261004.md) describes those
seams. The approximately 0.405 ms native MLP bracket is a partial scope; it
cannot categorically rule out a wider complete draft-head offload. No
complete-head latency or acceptance gain is claimed here.

## Pinned local inputs

| Input | SHA256 |
|---|---|
| Installed Light DLL | `ccc3bd0c2a8f519f9cd5fb112491785918810819f80c804302f717d2a93456ec` |
| Installed manifest | `0a1e15844043769d095bc70a808bbdff9d30c389182b61ddb7d61a7b6a8809a3` |
| Retained tiny graph | `4190ad34d24b563d0f8ca6a6ed8ef02ed96c475c99bec794719fe8f8c1e29036` |
| Retained tiny CPU receipt | `2a674030aa90eec083c5eec084b9834ad57cc05c89e21146167131098ad01968` |
| Frozen tiny helper | `ddd476b25f6e434b03390fb0974d54f157fcd26492417641a5ed9cc38fa15a1c` |
| Frozen provider-copy helper | `900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722` |

Only the new probe, new ignored guard and this new report were edited for this
task. Earlier probe/result hashes remain unchanged. Root owns admission and
integration; this source preparation made no hardware launch or commit.

## Root execution outcome at 04:59 UTC

Root executed the frozen probe once, after the greedy depth matrix completed
and ordinary GPU cleanup/recovery passed. ORT 1.25.2 advertised both Light NPU
and Light GPU devices; the exact NPU selector passed. The persistent session
then failed strict admission because some graph nodes were assigned to the
default CPU provider while CPU fallback was explicitly disabled. No warmup or
measured inference ran: `calls=[]`, zero NPU calls, and no latency result.
This rejects this exact eight-op graph/shape under the tested Light defaults;
it does not establish that converted QMoEBf or other prepared models fail.

Artifacts are retained under
`server/.local/optimization9h-20261004/light-ep-admission-1`.
`light-admission.json` SHA256 is
`207aa5f2933ec91e0db42b29f7fe5d885789f640ac5b5606ca3521445c2dad49`;
`result.json` records terminal exit1 and `owned_job_closed=true` with no guard
errors. Provider unregistration, DLL-directory close, bootstrap shutdown and
owned child/job close all passed. GPU state remained stopped. Minimum
physical/commit headroom in the child report was 48.0187 / 202.5903 GiB.
The probe is not promoted and should not be repeated unchanged.
