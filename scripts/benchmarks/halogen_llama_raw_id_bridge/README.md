# Pinned llama.cpp CPU/Vulkan raw-ID bridge

This finite native Windows AMD64 CLI implements the current NPU replay protocol against the retained Laurent llama.cpp C API, including bounded reconciliation of complete retained output from a growing replay. Root owns compilation, model/token-map verification, DLL loading, hardware admission and any target lifecycle action. The preceding bridge revision completed one finite screen on both CPU and Vulkan; see [the measured report](../../../docs/research/halogen-cpu-vulkan-proposer-screen-20261006.md). This reconciliation change requires root-owned compilation and execution. Native injection, complete-row append parity, target contention and Halogen speed gains remain unqualified.

Use only source commit `3466b48806f9fefe1162aa4053ffebcfcabe83aa` at `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx`. Its exact headers, import libraries and DLL hashes are pinned in [the boundary manifest](../../../docs/research/halogen-cpu-gpu-proposer-boundary-20261006.json). The deployed `C:/AI/runtimes/llamacpp` DLL and the b10690 archive are different builds and must not be substituted. This fork has extra by-value parameter fields; the source includes its actual header and uses its default parameter constructors, without hand-copied struct layouts.

## Parent-owned build

Use Release x64 MSVC C++20 with `/MD /EHsc /O2 /fp:precise /Zc:__cplusplus`. The retained runtime was built with MSVC 19.44.35228.0, x64, `/MD`. Do not use `/fp:fast`: supported-logit finite checks must remain effective.

Required include roots:

- `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx/include` (`llama.h`).
- `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx/ggml/include` (all five transitive public headers).
- `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx/vendor` (retained `nlohmann/json.hpp`).

Required import libraries:

- `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx/build-vulkan/src/Release/llama.lib`.
- `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx/build-vulkan/ggml/src/Release/ggml.lib` (backend registry).
- `C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx/build-vulkan/ggml/src/Release/ggml-base.lib` (device properties).
- MSVC `delayimp.lib`, plus normal Windows SDK default libraries. Direct CPU/Vulkan import libraries are not needed: the bundle's `ggml.dll` links those backends itself.

```bat
rem Parent-only: invoke in an owned output directory after validating source pins.
set LLAMA_SRC=C:\AI\build\laurent-llamacpp-qwen4exp-rocmfpx
cl /nologo /std:c++20 /Zc:__cplusplus /EHsc /MD /O2 /fp:precise /DLLAMA_SHARED /DGGML_SHARED /DWIN32_LEAN_AND_MEAN /DNOMINMAX /I"%LLAMA_SRC%\include" /I"%LLAMA_SRC%\ggml\include" /I"%LLAMA_SRC%\vendor" C:\Projects\strix-alloy-clean\scripts\benchmarks\halogen_llama_raw_id_bridge\bridge.cpp /Fe:bridge.exe /link /MACHINE:X64 /DELAYLOAD:llama.dll /DELAYLOAD:ggml.dll /DELAYLOAD:ggml-base.dll "%LLAMA_SRC%\build-vulkan\src\Release\llama.lib" "%LLAMA_SRC%\build-vulkan\ggml\src\Release\ggml.lib" "%LLAMA_SRC%\build-vulkan\ggml\src\Release\ggml-base.lib" delayimp.lib
```

The **link command must include** `/DELAYLOAD:llama.dll /DELAYLOAD:ggml.dll /DELAYLOAD:ggml-base.dll`. MSVC ignores those options in `#pragma comment(linker)` with LNK4229, so they are deliberately command-line requirements. Verify the resulting executable's import tables before loading: these must be delayed, with no eager llama/ggml imports or unrelated preloads. `main` rejects preloaded bundle basenames, restricts process DLL search to System32 and its explicit bundle directory, preloads five DLLs by absolute paths, and verifies the resolved module paths. It changes no global PATH or system setting. The required runtime bundle is:

`C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx/build-vulkan/bin/Release`

It contains `llama.dll`, `ggml.dll`, `ggml-base.dll`, `ggml-cpu.dll` and `ggml-vulkan.dll`. Both CPU and GPU executions retain the Vulkan-loader dependency because backends are linked. System dependencies include `vulkan-1.dll`, `VCOMP140.DLL`, MSVC runtime/UCRT and Windows DLLs. Root must resolve missing dependencies without substituting another ggml bundle. Context and model destruction precede backend teardown and bundle release; delay-loader references may keep libraries resident until this owned process exits.

## Replay contract

```text
bridge.exe --run MODEL.gguf DLL_BUNDLE_DIR cpu|vulkan DEVICE_INDEX COMMANDS.json OUTPUT.json
```

CPU mode requires explicit device index `0`, fixes generation and batch threads to four, passes an empty offload-device list and disables layer/KQV/op offload. Vulkan requires an explicit registry device index; the JSON records its name, description and physical device ID. It passes exactly that Vulkan device with all-layer/KQV/op offload requested. Actual fallback/placement must be read from the root-owned native log; requested offload does not establish all-GPU execution.

The candidate is `Qwen3.5-0.8B-Q4_0.gguf`, repository `ggml-org/Qwen3.5-0.8B-GGUF`, immutable revision `9447f74101aeb4e93621884dfa36ee8effb8831b`, exactly 563,036,064 bytes, SHA256 `57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`. Root must verify the payload and exhaustive embedded shared token map before execution. Before DLL initialization the source requires that exact payload length; it subsequently checks vocabulary/model geometry, not payload hashes or tokenizer equivalence. Startup has a 120-second cooperative budget checked after each phase and through the model-load progress callback. This cannot interrupt a hung DLL initialization, context call or missing callback; root must retain an external owned-process deadline. It loads only the text GGUF, with MTP disabled; no multimodal projector, text tokenizer or chat template is used.

Input is a regular JSON file of at most 1 MiB containing 1..64 sequential commands. The existing 52-command NPU input is supported unchanged, including its explicit `append_when_authoritative:true` pilot. Missing `append_when_authoritative`, `device_rejection_snapshot` and `full_device_rejection_snapshot` default to false. The two snapshot selectors must be explicit booleans and cannot both be true.

| Operation | Fields and behavior |
|---|---|
| `clear` | Retire owned state, synchronize and clear both attention/recurrent data and metadata. |
| `prefill` | `ids`: 1..512 shared raw IDs; always retire and clear/rebuild at positions 0..length−1. |
| `forward` | `id`: one authoritative shared ID; append, or clear/rebuild tail512 after a window shift. |
| `propose` | `count`: 1..3; independently greedy IDs from the committed row, consuming exactly count−1 speculative inputs. |
| `commit` | `accepted_ids`: prefix of the preceding proposal; `correction_or_bonus`: one shared ID or null, supplied only after prediction by target authority. |
| `resolve_replay` | `ids`: complete retained authoritative output for the current round, 0..4 IDs; `opening_reference_id`: one shared raw ID, compared with the first ID of the current pending proposal only after prediction. |

Every consumed/predicted ID is restricted to `0..248069`. Logical committed history is capped at 512. Context requests and checks 1024 capacity, one sequence, `n_rs_seq=0`, at most 512 batch/ubatch tokens, no backend sampler and four CPU threads. Explicit public API snapshots are separate from the recurrent rollback slots disabled by `n_rs_seq=0`. This revision pads context capacity to 256, so 1024 remains 1024. Both output-cap fields are explicitly one: every decode requests only its final logit row. Their zero defaults would expand to the 512-token batch cap and reserve a much larger output graph unnecessarily. Extra capacity accommodates up to two consumed drafts; it does not enlarge retained history. Native sequence maximum positions are checked after clear/decode and before append/restore; every nonzero decode status fails/discards the context.

`commit` defaults to full tail512 rebuild. Optional append requires `accepted.size() >= proposal.size()-1` and no eviction. The owned speculative row then describes a fully authoritative consumed prefix; only the remaining authoritative IDs are forwarded. Count-one proposals consume zero IDs and retain committed logits. An explicitly selected snapshot mode can restore a saved committed boundary after rejected consumed inputs, as described below. Window shifts and the default policy clear/rebuild both caches. Owned feed state retires before authoritative mutation; failures retire it and attempt full clear. Acceptance is a caller claim, not native verification. Future continuations never inform greedy prediction; syntax validation does not feed labels into the model. A new prefill cancels/rebuilds any prior pending proposal.

`resolve_replay` preserves that `commit` contract and resolves one current pending proposal against the complete retained round output. Let `C` be committed IDs, `D` the pending proposal, `c = D.size()-1` the inputs already consumed, and `R` the supplied retained output. It appends only when `append_when_authoritative` is true, the current proposal's opening ID equals `opening_reference_id`, `R.size() >= c`, `D[:c] == R[:c]`, and `C.size()+R.size() <= 512`. It checks the native length, retains the owned row after `c` inputs, retires the pending feed and decodes `R[c:]` once as one bounded batch when that suffix is nonempty; either selected snapshot mode uses scalar suffix forwards. With zero consumed inputs it retains the committed row; an empty suffix makes no decode call. Otherwise a selected available snapshot restores the committed boundary and scalar-replays the complete `R` when no eviction is needed. Remaining cases clear both caches and prefill `tail512(C+R)` once. An empty `R` still requires an existing committed prefix. A count-three proposal with only one retained output requires rollback or rebuild, even if its drafts match future labels. Opening reference equality authorizes reuse for this replay; it is recorded as `opening_reference_equal` and does not establish native target acceptance.

The root-owned policy check is `replay_policy_test.cpp`, a single standard-library C++20 executable using the same append predicate as `Bridge`. It requires no model, DLL or device. It covers incomplete output, opening and consumed-prefix rejection, capacity and zero-consumed-input cases. The native bridge remains responsible for pending epoch, both-cache clearing, row ownership and failure retirement.

Full native F32 heads are deep-copied before another engine call; greedy argmax uses only the shared 248,070 rows, requires those rows finite and chooses the lowest ID on ties. Rows outside the shared set are preserved in snapshots but never sampled. For this geometry each `.f32` snapshot contains 248,320 little-endian IEEE-754 floats, exactly 993,280 bytes. Every non-clear command saves its committed row. Proposals consuming inputs also save the final speculative row; the committed snapshot still describes the committed prefix. Count-one emits only a committed snapshot. Owned references must not survive a subsequent adapter mutation.

Both `OUTPUT.json` and its derived `OUTPUT.json.rows` directory must be fresh unique paths. A failed run may leave rows, but no successful manifest is written after a failed command. The manifest is separate from native stdout/stderr. It records PID, actual device/context choices, startup Unix timestamps and DLL/backend/model/context wall times. Commands record actual Unix timestamps, steady-clock wall time, clear/decode/synchronization/logit-readiness/copy/greedy components, raw committed/draft IDs, consumed count and context epoch. Replay resolutions also record `opening_reference_id`, `opening_reference_equal`, `replay_ids`, the pre-resolution `replay_consumed_inputs`, and the actual update path. Explicit synchronization precedes logit access and clear; this revision also synchronizes within `llama_get_logits_ith`. Command time includes F32 ownership and greedy selection and excludes snapshot disk writes; `snapshot_write_ms` records those writes separately. Whole-run time includes snapshot writes up to manifest writing; root should record process duration including teardown externally.

## Minimal qualification

### Experimental device rejection snapshots

Both public C API snapshot paths are default-off and belong only to this
independent model's private one-sequence context. They save sequence0 immediately
before the first speculative input, bind the save to the committed length and
context epoch, and preserve the committed owned F32 row and host metadata locally
before retiring the proposal. Count-one consumes no input and makes no save.
Successful accepted suffixes and restored resolutions use scalar authoritative
forwards. Save failures, restore failures and any resulting full rebuild remain
recorded and charged. Window eviction still rebuilds.

| Selector | Manifest mode/flags | Rejected-input rollback |
|---|---|---|
| `device_rejection_snapshot: true` | `partial_device`, `3` | Save/restore `PARTIAL_ONLY | ON_DEVICE`; restore recurrence, then remove the speculative attention suffix. Retained failed mode for evidence. |
| `full_device_rejection_snapshot: true` | `full_device_clear`, `2` | Save/restore `ON_DEVICE` alone, including live attention and recurrence. Synchronize and clear this private context's attention/recurrent memory with `data=true`, restore the saved state, require the exact metadata byte count and sequence position `L-1`, then scalar-replay the complete authoritative output. |

Full mode records `save_full_device_snapshot`, then on rollback
`clear_private_context_for_full_snapshot` and `restore_full_device_snapshot`
before any `authoritative_replay` calls. The successful path is
`full_device_snapshot_restore`. No suffix removal follows a full restore.
The full clear is a paid rollback operation: save includes metadata sizing,
allocation and device copies; clear and restore have separate elapsed records;
complete command wall time includes every operation and scalar replay. Full
mode does not establish the cause of the partial-mode mismatch or a correction.

At the pinned revision, device snapshot buffers live separately in the context's
`mem_storage`; clearing its memory data preserves those saved buffers. Full
serialization restores live K/V and recurrent state, while the preceding clear
zeros unused cache data. Backend graph state is outside this snapshot. Host
metadata is bounded at 64 MiB; this is not the size of device-resident tensor
copies. Actual copy extents, V transposition, allocation, residency and elapsed
cost require root-owned qualification. The device payload remains until the
next snapshot for that sequence or context destruction; retiring host metadata
does not release the device storage.

`check_snapshot_screen.py CANDIDATE.json --control CONTROL.json --mode full`
pins `full_device_clear`/flags2 and requires the private data clear before each
full restoration. `--mode partial` is the default for retained partial evidence.
The qualifier checks an identical initial full F32 row and all15
post-resolution rows against an independent snapshot-off control applying all37
authoritative IDs through scalar forwards. Exact 993,280-byte equality remains
mandatory. It requires fifteen real before-proposal saves, at least one restore,
no measured fallback/rebuild and finite recorded costs covered by command wall
time. `charged_component_ms` includes the initial seed and every measured
proposal/resolution, including the final round and every full private clear;
diagnostic F32 disk writes are reported separately. Root must retain process
duration and startup/teardown costs separately for any broader claim.

The measured partial device mode failed full-row equality at round2 despite
matching greedy IDs; it remains disabled. Its original measured source/checker
are retained under the ignored
`server/.local/optimization9h-20261004/snapshot-partial-source-before-full-20261006`
evidence directory. The distinct [full-mode finite GPU pass](../../../docs/research/halogen-device-full-snapshot-results-20261006.md)
subsequently qualified an identical initial row and all15 complete resolved rows,
with15 saves, nine private clears/restores and no measured prefix rebuilds.
Its seed plus proposals and complete resolutions cost26.05545ms per round;
diagnostic row writes are separate. This is independent-model state/cost
qualification on one retained family. The mode remains default off: no native
Halogen acceptance, target feed or serving token-rate improvement is established.

Before root-owned compile/load, source review must check the exact fork fields/API signatures, delayed-import completeness, explicit CPU/Vulkan selection, full-row ownership, count−1 accounting, authoritative append/rejection/window guards, private both-cache clearing and compatibility with the current 52 command shapes. Root owns the host-only replay policy check and bounded native screen. Compilation and actual rows/state/device placement remain unverified until root executes them. Compare the selected candidate against the identical-prefill scalar control without relaxing full-row equality. Any eventual adoption also requires actual target contention and opening/deadline evidence; this CLI creates no persistent feed, detour or main-engine cohort.
