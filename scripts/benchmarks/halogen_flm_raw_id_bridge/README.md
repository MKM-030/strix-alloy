# Pinned FLM Windows XRT raw-ID bridge

Root subsequently compiled this source and completed the [first real NPU screen](../../../docs/research/halogen-npu-independent-proposer-screen-20261006.md). The source-preparation notes below describe the original handoff; measured outcomes supersede their unexecuted status. The candidate remains default-off: no complete-engine speed gain or native acceptance improvement is qualified, and append-versus-full-prefill BF16 rows did not match exactly.

`bridge.cpp` uses the public `qwen3_5vl_npu(LM_Config, npu_xclbin_manager*, int)` constructor and qualified public method calls. It does not recover objects from vtables, use ctypes, tokenize/decode strings, or import the whole FLM application. This artifact has **not been compiled, linked, run, or runtime-qualified**. No DLL was loaded and no NPU operation or model download was performed while producing it. The parent task owns those steps.

The adapter owns 248,070 BF16 logit rows, copies them before the next engine call, and computes greedy argmax in that same native pass. IDs 0..248,069 are supported; finite supported logits are required, the lowest ID wins ties, and extra head rows never participate. Its committed history is at most 512 IDs. One to three drafts consume zero to two speculative engine inputs. By default, every `commit` uses clear/prefill of the accepted prefix plus optional correction/bonus, retaining only tail512. An explicit default-off `append_when_authoritative` option appends when all consumed inputs were accepted and no window shift occurs; rejection or eviction still rebuilds. `forward` appends a committed ID and uses the same rebuild when the window shifts. No checkpoint, restore, context setter, or update-max-length shortcut is used.

The caller must independently establish target acceptance, model/tokenizer equivalence, request identity, stop/constraint policy, and packet integrity. CLI `accepted_ids` are caller claims, not target verification. This finite replay CLI is an adapter probe, not a persistent native feed or a replacement for the existing coordinator and selector.

## Pinned inputs and ABI limitations

- Header root: `C:\AI\src\FastFlowLM-zip\FastFlowLM-1.0.7\src\include`.
- Engine: `C:\AI\runtimes\flm-1.0.7-npu-probe\portable\qwen3_5vl_npu.dll`, SHA256 `d77388dcd21fcd7422005d0f780a044142d525e3afaafef3bcb9e980b8c18501`, 2,316,288 bytes. This matches `src\lib\xrt`; HRX is a different binary.
- Import libraries: `src\lib\xrt\qwen3_5vl_npu.lib`, SHA256 `552fd01d65fdfc2efb15d46f3c24428574eee84164c9adabb213d75fbdf07b4d`; `q4_npu_eXpress.lib`, SHA256 `d643ba640ad890ed596ff2e83438f3cde5e23c7960e9672c58dc9645d3cddf7e`.
- Model directory must contain `config.json` and language `model.q4nx` from immutable package commit `1d16e5eaa2508889fb88eb1bfab1921a30a1a466`, branch `flm_q4k_high_precision`. Expected model payload: 560,985,936 bytes, SHA256 `787428ffe87be5e3e5a8fcaf241844b69896ca0c74a41f2432c436739f7ba4e4`. That payload was absent at authoring time. Parent must verify payload/config provenance before execution; the source geometry check is not a hash check.
- Retained config SHA256: `a571afa7fca18a6ecb4c0c2dbc7758204b442804056280e85d4e2d6c582c70c3`.
- Xclbin bundle root argument is `C:\AI\src\FastFlowLM-zip\FastFlowLM-1.0.7\src`, **the parent of `xclbins`**. The fixed model subdirectory is `Qwen3.5-0.8B-NPU2`. Token-only kernels required: layer, lm_head, mm, attn, conv, GateDeltaNet_prefill.

`LM_Config` is passed by value across the DLL boundary. The supplied header explicitly requires its layout to match the DLL; by-value STL/JSON and buffer ownership ABI compatibility remain unqualified. The prebuilt FLM DLLs record linker 14.51; local MSVC is 14.44. Do not regard decorated-symbol matches as proof of layout or runtime compatibility.

The bridge populates `LM_Config` directly to avoid FLM app path discovery and tokenizer dependencies. It keeps the disk config intact, sets the public path/version fields, and sets **in-memory `is_vlm=false` and `is_audio=false`** for token-only operation. Static DLL inspection identifies `is_vlm` at RVA `0x10cdc0`, stored in Impl+`0x99`, guarding image encoder construction at `0x49ca1` and vision weight loading at `0x5e44d`. This route is not runtime-tested; it does not assert that arbitrary multimodal IDs have useful text semantics.

The pinned constructor clamps requested capacity to at least 4096 (RVA `0x49bdd`..`0x49bed`), then rounds as needed. Accordingly, the adapter requests **4096** explicitly. **512 is a logical retained-history limit, not a claim of 512-token device allocation or bounded total device residency.** Maximum transient consumed length is 514. The manager uses NPU2/device index 0 with preemption disabled; engine dies before manager/device, and Q4NX is released after load, matching public AutoModel construction.

## Build route for the parent

Use a **Release AMD64 MSVC C++20** environment, `/MD /EHsc /O2 /fp:precise`. Precise FP is intentional so the nonfinite-logit check remains meaningful. Local compiler:

```text
C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\cl.exe
```

Developer environment: `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat`. Installed Windows SDK is `10.0.26100.0` under `C:\Program Files (x86)\Windows Kits\10`.

The exact source-supported definitions are `DISABLE_ABI_CHECK=1`, `__WINDOWS__`, `WIN32_LEAN_AND_MEAN`, `NOMINMAX`, `_CRT_SECURE_NO_WARNINGS`, `_CRT_NONSTDC_NO_DEPRECATE`. Leave **`FLM_USE_HRX` undefined**; defining it to zero still selects HRX. No `USEAVX2` definition or `/fp:fast` is required by this bridge.

Required include directories: pinned FLM `src\include` and the **matching Windows XRT SDK include root** exposing `xrt/xrt_device.h`, `xrt/experimental/xrt_module.h`, `xrt/experimental/xrt_elf.h`, and `xrt/experimental/xrt_ext.h`. FLM bundles aiebu headers in its include root. Required import libraries: pinned `qwen3_5vl_npu.lib`, pinned `q4_npu_eXpress.lib`, and matching `xrt_coreutil.lib`. `aiebu_static.lib` is the source CMake-supported extra (present in `src\lib\xrt`); it is included below for inline registration compatibility.

```bat
rem Run only after parent resolves the missing matching XRT SDK and qualifies ABI.
set FLM_SRC=C:\AI\src\FastFlowLM-zip\FastFlowLM-1.0.7\src
set XRT_SDK=C:\PATH\TO\MATCHING\WINDOWS\XRT_SDK
cl /nologo /std:c++20 /EHsc /MD /O2 /fp:precise /D__WINDOWS__ /DDISABLE_ABI_CHECK=1 /DWIN32_LEAN_AND_MEAN /DNOMINMAX /D_CRT_SECURE_NO_WARNINGS /D_CRT_NONSTDC_NO_DEPRECATE /I"%FLM_SRC%\include" /I"%XRT_SDK%\include" bridge.cpp /Fe:bridge.exe /link /MACHINE:X64 /LIBPATH:"%FLM_SRC%\lib\xrt" /LIBPATH:"%XRT_SDK%\lib" qwen3_5vl_npu.lib q4_npu_eXpress.lib xrt_coreutil.lib aiebu_static.lib
```

XRT headers and `xrt_coreutil.lib` were initially unavailable; the parent subsequently acquired and SHA-verified the official SDK at `C:\AI\dev\halogen-pld-xrt-2.21.75\sdk\xrt_sdk\xrt`. Use that directory as `XRT_SDK` in the command above. CMake defaults `C:\dev\XRT` and `C:\dev\xrtNPUfromDLL` remain absent. Read-only installed-runtime metadata identifies XRT 2.21.0, exact commit `15e6319be8de1e76a6150111a3861729e988fdb5`, AMD resource version `32.00.20102.3931`, build date `2026-05-07 16:04:09`, and DLL SHA256 `04a26d37c6e0c713491ad0bfae74ce74ea94c74136d2aa056333616dac6c3a44`. That [exact commit](https://github.com/Xilinx/XRT/commit/15e6319be8de1e76a6150111a3861729e988fdb5) changes two internal implementation files from parent release 2.21.75; its public headers are unchanged. The [official native Windows guide](https://xilinx.github.io/mlir-aie/dev/buildHostWinNative/) names the [2.21.75 SDK archive](https://github.com/Xilinx/XRT/releases/download/2.21.75/xrt_windows_sdk.zip), SHA256 `ccc244c2c423588972ade76142cdc01049477aaa39a35be97e782b97eb7c5295`, 70,834,080 bytes, published 2026-02-24. No archive was downloaded by this source-only agent.

The official SDK import library has exactly the same 541-name set as the installed DLL's 541 exports; no alternative library generation is needed. Static byte-level auditing also found no runtime forwarders/data exports and all 28 engine plus one Q4NX XRT import names present. If a future SDK lacks its import library, the [official Windows host guide](https://xilinx.github.io/mlir-aie/dev/buildHostWin/) documents extracting a module-definition file from the installed DLL's exports and generating an import library with `lib /def:xrt_coreutil.def /machine:x64 /out:xrt_coreutil.lib`. These checks establish structural symbol availability, not behavioral or by-value ABI qualification. Library generation was not performed here.

Compilation was deliberately not attempted. Parent controls DLL search paths and should pair Qwen/Q4NX with their pinned portable DLLs; normal import linking loads dependencies before `main`, including for an invalid CLI invocation. `--run` gates device initialization, not Windows loader activity.

## Finite CLI

```text
bridge.exe --run MODEL_DIR XCLBIN_BUNDLE_ROOT COMMANDS.json OUTPUT.json
```

Input is an object with 1..64 commands, bounded to a 1 MiB regular file. Optional top-level `"append_when_authoritative": true` explicitly enables the conditional append route; omitted/false uses rebuild. Operations are `clear`, `prefill` (1..512 IDs), `forward` (one committed ID), `propose` (count 1..3), and `commit` (accepted proposal prefix and optional correction/bonus). Only one pending proposal is allowed. Failure terminates with a nonzero code; local snapshots retire after a failed engine operation. Execution is synchronous and one-shot. Output JSON is written to its own file after all commands succeed, so library stdout logging cannot corrupt it. Both `OUTPUT.json` and its derived `OUTPUT.json.rows` directory must be fresh unique paths; existing paths are rejected before device initialization.

Every non-clear command emits an owned committed-logit BF16 file in that directory: 248,070 native little-endian two-byte rows (496,140 bytes). Proposal commands with consumed inputs also emit a separately identified speculative-logit file; their committed file still describes the committed prefix. Filenames include command index and are never reused within a run. These binary snapshots support root-owned hashing and full-row parity against a fresh authoritative prefill, beyond argmax equality. `sizeof(bf16)==2` is statically required. The JSON records actual Unix-millisecond timestamps and steady-clock command elapsed time including native logits copying/argmax, excluding snapshot-file writes. Device/manager, model constructor, and Q4NX load/release startup wall times are separate fields. A failed run may leave snapshot files but never a successful output manifest. No values are measured merely by creating this source artifact.

For a parent-owned harness, define `RAW_ID_BRIDGE_NO_MAIN` to include the C++ implementation without the finite CLI entry point; `raw_id::Bridge` accepts an externally owned engine and exposes clear/prefill/forward/propose/commit plus const owned-logit accessors. The adapter is synchronous; callers must not retain an accessor reference across subsequent adapter mutation.

Example input (IDs are illustrative and do not claim a tokenizer-valid prompt):

```json
{"commands":[{"op":"prefill","ids":[100,101,102]},{"op":"propose","count":3}]}
```

An independently known acceptance can be replayed with `{"op":"commit","accepted_ids":[...],"correction_or_bonus":123}`. `null` permits accepted-only/EOS or empty output. There is no intrinsic stop-token handling; caller stop policy owns that decision. A new process starts a new adapter; no background loop, driver mutation, cache snapshot, or hidden download is included.

## Append-only observations for later optimization

One draft samples already-owned committed-prefix logits with zero speculative forward calls or engine state mutation. For k drafts, only k−1 IDs are consumed. If accepted count is at least that consumed count, the engine contains an accepted prefix and the remaining authoritative IDs can be appended: full acceptance appends the last draft plus bonus; three drafted/two accepted appends only correction; two drafted/one accepted does likewise. If acceptance is shorter than the consumed prefix, rejected mutations remain and rebuild is required.

These observations require supported authoritative IDs, truthful acceptance/count/logit state, the same request/origin, sufficient capacity, and **no retained-window shift**. Any output at a full 512-ID retained window evicts IDs and requires clear/rebuild. They establish neither a general per-round speedup nor safety of checkpoint/restore. The option requires future comparison of actual owned BF16 rows against a fresh authoritative rebuild for one-draft/zero-accepted correction, three-draft/accepted-consumed-prefix, and rejection cases. No runtime equality or timing result is claimed here; future measurements must use real captured inputs/rows and actual timestamps, excluding future-label data from inputs.
