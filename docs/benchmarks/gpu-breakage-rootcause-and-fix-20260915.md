# GPU breakage: root cause, fix, and why the earlier reasoning was wrong (2026-09-15)

## Root cause — a DLL shadow, not the boot experiments

`ggml-hip.dll` imports **`amdhip64_7.dll` by name**. Windows' loader searches in this order:

1. the directory of the **executable** (`...\build-therock\bin\`) ← *no copy existed here*
2. **`C:\Windows\System32\`** ← **the GPU driver's copy won**
3. `PATH`

So the server silently loaded the **driver's** HIP runtime instead of the SDK's:

| | size | date |
| --- | ---: | --- |
| SDK `amdhip64_7.dll` (TheRock, correct) | 16,578,560 | 2026-09-15 04:41 |
| **`C:\Windows\System32\amdhip64_7.dll`** (driver's, what we got) | **17,512,464** | **2026-08-18** |

**One fact settles it beyond doubt.** The SDK's own `hipInfo.exe` sits **next to** the SDK runtime, so it
resolves its *own* copy and works perfectly:

```
TheRock SDK hipInfo -> exit=0,  "AMD Radeon(TM) 8060S Graphics", totalGlobalMem: 107.87 GB
our llama-server.exe -> cudaMemGetInfo failed (invalid argument), returning 0/0
```

Same GPU, same driver, same session, same instant. The only difference is *which* `amdhip64_7.dll` each
process loads. That is a name-resolution bug, not a hardware or boot-state fault.

## The fix

Place the SDK runtime **beside the executable**, where the loader looks first:

```powershell
.\fix-hip-dll.ps1     # copies amdhip64_7.dll, amd_comgr.dll, amdocl64.dll from the SDK bin
```

Result — the failing line is gone and the server comes up:

```
1.15.450 I cmn init: llama threadpool init, n_threads = 16
1.15.985 I srv llama_server: model loaded
1.15.985 I srv llama_server: listening on http://127.0.0.1:8299
```

Confirmed with a real benchmark (16384 prompt, 3 reps):

| config | prefill @16k | decode @16k |
| --- | ---: | ---: |
| **after fix** | **1026.8 / 1033.9 t/s** | **28.0 / 28.4 t/s** |
| pre-incident baseline | 1024.8 / 1029.3 t/s | 27.7 / 27.9 t/s |

**Back to baseline.** Also restored: MTP n-max 2 @16k = 985 prefill / 29.11 decode.

The fix is now **written into `build-win-therock.ps1`**, so a rebuild re-pins the DLLs and cannot
reintroduce the shadow. `fix-hip-dll.ps1 -Revert` undoes it.

## Correction: my earlier diagnosis was wrong

I claimed the boot experiments broke the GPU, and specifically that arm C (`vsmlaunchtype Off` +
`hypervisoriommupolicy Disable`) caused a GPU wedge that a warm reboot failed to clear. **That was wrong**,
and the cold boot failing is what disproved it.

What actually happened is more likely this: the **17:10 baseline run was fine**, and the breakage appeared
at ~19:04. But a boot-state change cannot explain a *load-order* difference in a DLL. The most probable
trigger is that something between 17:10 and 19:04 caused `...\bin\amdhip64_7.dll` to be **absent or
replaced** — the 19:12 timing lines up with when I last copied files into that tree (`apply-phase-timing.sh`
runs during rebuilds), and I had also run a full `build-win-therock.ps1` which rebuilds into that directory.

I do not have proof of the exact trigger, and I will not invent one. What I do have is the *mechanism*,
demonstrated by the hipInfo-vs-server split, and a fix that is verifiable and now permanent.

**Two hypotheses I asserted before checking, both of which turned out false:**
1. a leftover `hypervisoriommupolicy` in the global `{hypervisorsettings}` container → the full BCD dump
   was clean;
2. WSL holding the GPU → shutting `vmmemWSL` down changed nothing.

Both are recorded so the record shows they were tested and rejected rather than quietly dropped.

## What the boot experiments actually established (unaffected)

- **Arm D is blocked by VBS**: the test entry booted with `hypervisorlaunchtype Off` *and*
  `vsmlaunchtype Off`, yet `HypervisorPresent = True` and VBS status 2. `RequiredSecurityProperties`
  includes base virtualization, so VBS forces the hypervisor.
- **Arm C breaks the native ROCm path** — though given the DLL finding, this result should now be treated
  as **unconfirmed**: the "C breaks the GPU" conclusion was drawn while the DLL shadow was already present,
  so it may have been the same bug rather than an effect of the C settings. **Re-testing arm C is now
  cheap and worth doing** if we care about the IOMMU question, because we can distinguish the two causes.

## Lesson worth keeping

The distinguishing test was **"run the vendor's own probe against its own runtime"** — `hipInfo.exe` next
to its DLL, versus our binary. That split a 40-minute dead end into a one-line answer. Reach for the
vendor tool earlier next time.
