# GPU breakage after the boot experiments — localization and recovery (2026-09-15)

## Symptom

`llama-server.exe` (native Windows, TheRock ROCm build) dies ~0.3 s into model load:

```
stdout: <empty>                                   <- device enumeration never printed
stderr: ggml_backend_cuda_device_get_memory: cudaMemGetInfo failed (invalid argument), returning 0/0
stderr length = 899 bytes, process exits
```

A healthy native run prints `found 1 ROCm devices (Total VRAM: 110456 MiB)` on **stdout** and reaches
`llama threadpool init` / `listening on`. Neither happens now.

## What is NOT the cause (all ruled out with evidence)

| candidate | evidence | verdict |
| --- | --- | --- |
| Hardware damage | `AMD Radeon(TM) 8060S Graphics` — `CM_PROB_NONE`, `ConfigManagerErrorCode 0` | **no** |
| Driver change | `32.0.31041.1004`, driver date 8/17/2026 — **identical to the 18:06 baseline** | **no** |
| Missing ROCm DLLs | `rocblas.dll`, `hipblas.dll`, `hiprtc-builtins` all present, dated 09-15 04:41 | **no** |
| Leftover BCD setting | full `/enum all /v` is **clean**; no `hypervisoriommupolicy` anywhere; the global `{hypervisorsettings}` holds only hypervisor debug serial settings; test entries deleted | **no** |
| Fast Startup / hybrid boot | `HiberbootEnabled = 0` | **no** |
| WSL holding the GPU | shut `vmmemWSL` down completely, re-tested — still fails | **no** |
| Memory pressure | 22.7 GB free of 31.6 GB | **no** |

I stated hypotheses for two of these (leftover BCD setting, WSL contention) before checking them. Both
were **wrong**. Recording that plainly: I should have measured first and proposed second.

## What IS true — it works everywhere except native-hybrid HIP

| path | result |
| --- | --- |
| **Vulkan** (`strix-vulkan-ba5354d`, same 93 GB PROJFIX) | **works** — `model loaded` + `listening on` |
| **HIP from WSL** (`build-hip`, over `/dev/dxg`, Ornith 35B) | **works** — `found 1 ROCm devices (VRAM: 114332 MiB)`, all layers assigned to `ROCm0`, tensors loading |
| **HIP native Windows** (TheRock `build-therock`) | **fails** at device init |

That is a clean three-way split. The GPU is healthy, the ROCm *Linux* runtime works, and Windows' legacy
display path (Vulkan) works. Only the **native-Windows ROCm runtime** is broken — specifically its
device-memory query, which is the first D3DKMT/LUID call HIP makes.

There are `Kernel_141` (**LiveKernelEvent 141 = GPU hang**) reports in the WER queue. I could not read
their `EventTime` (Report.wer needs admin), and the folder mtime (19:12) is when they were queued, not
when the hang occurred — so I will not claim they coincide with the breakage.

Likely mechanism, stated as a hypothesis: a **GPU firmware/driver state wedge** from the abrupt power
cycles into and out of arm C (which had `vsmlaunchtype Off` + `hypervisoriommupolicy Disable`). A warm
Windows restart rebuilds the kernel but may reuse the adapter's initialised state; a **full power cycle**
re-initialises the GPU from scratch.

## Recovery, cheapest first

1. **Full shutdown, then power on.** `HiberbootEnabled = 0`, so shutdown genuinely halts. This is the
   single most likely fix and costs nothing.
2. If still broken: **restart the AMD display driver** — `Win+Ctrl+Shift+B`, or disable/enable the adapter
   in Device Manager.
3. If still broken: **reinstall the Radeon driver** (we know the exact version: `32.0.31041.1004`) —
   admin, and a bigger hammer.
4. Meanwhile: **the Vulkan path and WSL HIP both work**, so no data collection is fully blocked.

## What was NOT lost

- The arm D/C results stand: D is VBS-blocked, C breaks the native ROCm path. Both were verified by reading
  settings back off the booted entry, so they are solid measurements.
- All baseline numbers (1057 prefill, 32.8 decode @16k, the 80%/16% phase split) are untouched — the arm-C
  run wrote nothing, so no stale data was overwritten.
- The BCD store is clean and the two test entries are deleted.
