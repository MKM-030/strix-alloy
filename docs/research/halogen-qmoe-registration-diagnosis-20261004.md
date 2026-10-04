# QMoEBf registration and runtime API boundary in installed Light1.8

The first strict Light candidate stopped at **ONNX custom-op registration**, before shape admission or NPU execution. Registering the **same verified Light DLL** resolved that error in the next owned attempt, which now stops at **custom-op C API version27 versus the installed runtime's maximum25**. An existing complete CPython3.12 ONNX Runtime1.29 package accepts API27 in static binary evidence and supplies a candidate for a new root-owned guarded attempt. Full Light compatibility remains unqualified.

## Observed failure and missing boundary

Root's owned attempt `server/.local/optimization9h-20261004/qmoe-light-admission-d8498f570cb943099e06eb261e3fd30a/` passed source/artifact validation and selected the real Light NPU. Model loading failed with `com.ryzenai:QMoEBf(-1) is not a registered function/op`, initialization duration1.8323ms, zero NPU calls. Provider unregistration, DLL-directory cleanup, bootstrap release, and terminal-owned job closure completed.

The probe registered `RyzenAILightExecutionProvider` using `ort.register_execution_provider_library`, selected its device, and added that provider to session options. It did not call `options.register_custom_ops_library` before `InferenceSession`. EP factory registration and custom-op schema/kernel registration are separate API boundaries.

[ONNX Runtime's custom-operator documentation](https://onnxruntime.ai/docs/reference/operators/add-custom-op.html) documents the exported `RegisterCustomOps` entry and attaching the custom-op library to session options. [AMD's standalone Light example](https://github.com/amd/sd-sandbox/blob/main/src/utils/common.py#L342-L390) supplies the concrete pattern: `config_session_options` adds the device provider, then calls `session_options.register_custom_ops_library(custom_op_path)` before constructing a session. That project uses `onnxruntime_providers_ryzenai.dll` as the Light/custom-op library. The public `main` reference is a current source precedent, not an additional pinned deployment artifact.

## Existing matching library: static PE evidence

Chosen verified copy:

`C:/AI/halogen-mtp-npu/npu-ep-1.8.75-20261004/onnxruntime_providers_ryzenai.dll`

| Property | Verified value |
|---|---|
| Installed package | `MicrosoftCorporationII.WinML.AMD.NPU.EP.1.8_1.8.75.0_x64__8wekyb3d8bbwe` |
| File size/version | 4,368,688 bytes; `1.8.0.6` |
| SHA256 | `ccc3bd0c2a8f519f9cd5fb112491785918810819f80c804302f717d2a93456ec` |
| PE architecture | AMD64 (`0x8664`) |
| Standard custom-op entry | `RegisterCustomOps`, RVA `0x19fe40` |
| AMD entry | `RyzenAI_RegisterCustomOps`, RVA `0x19fed0`; its first instruction jumps directly to `0x19fe40` |
| Other relevant exports | `CreateEpFactories`, `ReleaseEpFactory`, `RyzenAI_RegisterCPUGateCustomOps`, `RyzenAI_SetExecutionProviderType`, `RyzenAI_SetSessionOptions` |
| Exact ASCII evidence | `QMoEBf` at file offset `0x362134`; `com.ryzenai` at `0x3676d0`; `RyzenAILightExecutionProvider` at `0x36a3a8` |
| Static imports | `ryzen_mm.dll`, `dyn_dispatch_core.dll`, `xrt_coreutil.dll`, `dbghelp.dll`, `KERNEL32.dll` |

The retained admission inventory records matching catalog/copied hashes for the chosen EP and its task-local companions. A fresh static file hash matches the EP pin above. Export and string evidence plus the documented registration pattern support this exact next candidate; they do not establish its eventual512/top10 kernel support or successful initialization.

The same verified directory also contains `onnxruntime_vitis_ai_custom_ops.dll` (2,758,944 bytes, version1.8.0.6, SHA256 `be3acceb0f2de7c8d24eec3e3a8e6970c40cff31fb7637c7f90dc6ad915fe15e`). It exports `RegisterCustomOps`/`RegisterCustomOpsAltName`, but static inspection found no exact `QMoE`, `QMoEBf`, `com.ryzenai`, or Light-provider strings. Its filename alone is insufficient reason to register it for this graph. The chosen Light DLL is the directly supported candidate.

## Registration change used by the next root-owned attempt

Retain the verified copy, its existing DLL search directory, exact graph/Header/bank pins, provider options, memory floors, strict device selection, fallback exclusion, profiling, and owned cleanup. After provider selection is attached to this session's options, add only:

```python
options.register_custom_ops_library(str(chosen_library))
# Then construct the same pinned InferenceSession with these options.
```

This call belongs to the guarded runtime attempt owned by root; it was not executed during this static diagnosis. The standard entry aliases the named AMD custom-op entry, so no direct `ctypes` call or guessed additional AMD API is proposed. Record registration failure separately from model loading; continue strict execution attribution if loading succeeds.

The initial error says nothing about512 experts, top10, standard-SwiGLU attributes, logical-versus-padded dimensions, or the2.78125GiB bank. Those checks remain downstream. Identical zero experts can only qualify admission and bounded zero-output behavior, not routing/addressing or arithmetic. SDK/Light compatibility, NPU placement, state ownership, draft acceptance, and useful throughput remain unqualified.

## Subsequent failure: custom-op API27 exceeds WinML API25

Root's owned attempt `server/.local/optimization9h-20261004/qmoe-light-admission-98114cda0f9c47aab59a379917a2f810/` registered the chosen custom-op library and reached `CustomOpKernel` initialization, then failed with `Unsupported version '27' in custom op 'QMoEBf'` at the vendor build's `custom_ops.cc:911`. Its actual Python package was `onnxruntime-windowsml 1.25.2.202605110140`; it recorded zero NPU calls and clean owned cleanup.

The [official ORT v1.25.0 kernel constructor](https://github.com/microsoft/onnxruntime/blob/v1.25.0/onnxruntime/core/session/custom_ops.cc#L831-L847) rejects `op_.version > ORT_API_VERSION` before either kernel creation callback, then passes the custom op's version to `OrtGetApiBase()->GetApi`. The [same release's C API header](https://github.com/microsoft/onnxruntime/blob/v1.25.0/include/onnxruntime/core/session/onnxruntime_c_api.h#L34-L38) defines version25; its [`OrtCustomOp` declaration](https://github.com/microsoft/onnxruntime/blob/v1.25.0/include/onnxruntime/core/session/onnxruntime_c_api.h#L6939-L6949) requires that field to use the C API version. Thus27 is the registered custom op's ABI/API version, not the graph's ONNX opset or expert count. The vendor source line differs from this upstream tag; the observed function/error and installed binary bound identify the same rejection boundary.

Static reads of PE bytes, without loading either file, independently establish the installed version limit:

| WinML1.25 file under `C:/AI/runtimes/winml-npu/Lib/site-packages/onnxruntime/capi/` | Size | SHA256 | API-bound evidence |
|---|---:|---|---|
| `onnxruntime.dll` | 22,136,632 | `25eadfc2d4d998ce2e1a2404790e73cf7f86dbf584d64b6e25e59d2c157ea757` | `OrtGetApiBase` RVA `0x6f850`; table points to `GetApi` RVA `0x52b00`; `lea eax,[rcx-1]; cmp eax,0x18; ja unsupported` accepts1..25 |
| `onnxruntime_pybind11_state.pyd` | 27,825,504 | `f7f09ee4fcb8a24094ccc4cdd1e13b548d72e82594b3c1972030720848d4dc3a` | Unique matching API-bound code at file offset `0x194310`, also1..25; exact `Unsupported version` string at `0x114ff48` |

Both inspected Python bindings contain their own API-bound code and neither lists `onnxruntime.dll` in its PE import table. Substituting only the standalone DLL does not replace the binding's embedded maximum25 code. The candidate should use a complete matching Python package in isolation, with a compatible CPython interpreter, rather than a single-DLL substitution.

## Existing complete API-compatible package candidate

The existing package is `C:/AI/runtimes/qwen3-tts/.venv/Lib/site-packages/onnxruntime/`, with metadata at the sibling `onnxruntime-1.29.0.dist-info/`. Its metadata states `Name: onnxruntime`, `Version: 1.29.0`, and `Requires-Python: >=3.11`; its wheel tag is `cp312-cp312-win_amd64`. The containing environment's `pyvenv.cfg` identifies CPython3.12.10 at `C:/Users/Marcel/AppData/Local/Programs/Python/Python312`. No wheel download or installation was needed for this static candidate.

| ORT1.29 file under that package's `capi/` | Size | SHA256 | API-bound evidence |
|---|---:|---|---|
| `onnxruntime.dll` | 18,093,880 | `f9013e824c1dbc5b1874ffdabeedfd1cad4e2dabd9d93528f6ec6d21c2980d00` | `OrtGetApiBase` RVA `0x29600`; table points to `GetApi` RVA `0x64b70`; `lea eax,[rcx-1]; cmp eax,0x1c; ja unsupported` accepts1..29, including27 |
| `onnxruntime_pybind11_state.pyd` | 18,748,216 | `d9114a3f211f302fb6efb537a1972c2a5e01b408a7311abf14127d100dc76849` | Unique matching API-bound code at file offset `0x1588b0`, also1..29; PE imports `python312.dll` |

Source inspection shows that the candidate exposes `get_ep_devices`, `register_execution_provider_library`, and `unregister_execution_provider_library`; its inference collection source documents `add_provider_for_devices`. The following source/metadata pins support a complete root-owned isolated overlay if chosen:

| File relative to `C:/AI/runtimes/qwen3-tts/.venv/Lib/site-packages/` | SHA256 |
|---|---|
| `onnxruntime/__init__.py` | `c8dc5c6007d8a3a4691fc7dcc650c11bda155a033bcc029cd0dd46f630565c32` |
| `onnxruntime/capi/onnxruntime_inference_collection.py` | `2bc0c884f3e139e1b7800c7f0601f1bf34dfc84880fb4bb4407fefc156ecb4b6` |
| `onnxruntime/capi/_pybind_state.py` | `9db5299d49dcc01bf9a60240f32ba00d82510384d37c2d206983840f98c3f920` |
| `onnxruntime-1.29.0.dist-info/METADATA` | `eb1f9c5003bd1146122da378763d3f0a853e48d5156f2d54685481820794ac80` |
| `onnxruntime-1.29.0.dist-info/WHEEL` | `f767fbbf21c4fc6662c119c3d88d39bc24ff4b7f54be4472ba0b980c028e19bf` |

This is an API-level candidate only. It has not been imported, used to load Light, or run through provider registration, session creation, or NPU execution during this diagnosis. Its complete-package/runtime compatibility, Light plugin registration, required dependencies, QMoEBf shape admission, and512/top10 behavior still require the next owned guard. Retain the existing graph/Header/bank pins, selected verified Light copy, strict NPU attribution, provider options, memory floors, and cleanup ownership. No graph or packing change is justified by this API-version error.

## Sealed task-local candidate prepared for root review

The entire existing donor package and sibling metadata tree were copied to:

`C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/qmoe-ort129-stage-f1e210f85e8e4f609aa66df0b80e5495/site-packages/`

The adjacent `stage-manifest.json` records every donor/stage path, size, donor SHA256, and staged SHA256: **630 files,45,280,440 bytes**, including the donor's existing bytecode files. All donor hashes were compared before and after copying; the complete file set and bytes were unchanged. The staged files and manifest were marked read-only. Both existing environments were preserved; this stage is a file copy, not an installation.

| Review artifact | SHA256 |
|---|---|
| Stage `stage-manifest.json` | `3760ee417baa2ecea0d5c8921f3a80568483a28cd1b24479f9ef4f8b8583216f` |
| `scripts/benchmarks/halogen_qmoe_light_probe.py` | `0c0e0071e8c3953f91df0729c3c86e44c959f8616e1feb392cae95a01c942abc` |
| Ignored `server/.local/optimization9h-20261004/run_qmoe_light_guard.py` | `9610d697f13f62ccbee6a9f621b54ed04a57a0313ba33a649d293010ca3b2eed` |
| Ignored `server/.local/optimization9h-20261004/stage_qmoe_ort129.py` | `f14c1e43e54a791f9177ec8be023baa056904847cbce1806493536ba5fc89272` |
| Public identical stager `scripts/benchmarks/halogen_qmoe_ort_stage.py` | `f14c1e43e54a791f9177ec8be023baa056904847cbce1806493536ba5fc89272` |

The public stager is an identical source copy for reproducibility, not another execution. It accepts a fresh direct child of this task's work directory named `qmoe-ort129-stage-*`; copying it does not alter the frozen stage manifest or probe/guard pins. A future execution would produce a new inventory and require a separately reviewed candidate pin.

The probe now requires the sealed manifest path/hash, verifies the complete staged tree before package selection and immediately before ORT import, rejects preloaded ORT, and confirms the imported package version and native binding's exact staged path. The existing pinned WinML interpreter, NumPy, ONNX, WinUI bootstrap dependencies, and old-environment ORT file pins remain in its source checks. The guard verifies the whole stage before launch, seals a copy of its manifest in the owned attempt receipt, passes the manifest pin to the child, monitors that seal, and verifies the whole stage again after owned closure. Its child retains `-B` so the stage does not gain bytecode files. Existing native lifetime ownership, memory floors,90-second deadline, strict fallback/device policy, and synthetic graph/bank pins are retained.

Static compilation succeeded for the three changed Python files. AST-extracted file-verifier functions independently accepted all630 sealed files in both probe and guard and rejected a wrong manifest pin, preloaded ORT, and a simulated native-binding digest mismatch. The checks imported only standard-library modules; they did not import the probe, guard, ORT, NumPy, ONNX, WinUI, or host/device helpers. No native admission child was started. Root owns review and launch of this candidate; successful runtime initialization or NPU behavior has not been established here.

This investigation used retained source/receipts, static PE imports/exports/strings/code, file version/hash reads, Python source/metadata reads, official documentation/source, and the authorized complete-package file copy. No target DLL was loaded, native target module imported, EP registered, provider/session/device invoked, task model loaded, or graph/packer test repeated. The probe and staging/guard files were adapted in addition to this diagnosis note; frozen graph source contracts and artifacts were unchanged.
