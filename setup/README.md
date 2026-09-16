# strix-alloy setup

Everything needed to reproduce the numbers in the top-level README on a Strix Halo box, natively on
Windows.

## 1. The SDK

Download the **TheRock Windows HIP SDK for gfx1151** (clang 24). Nightly tarballs are published at:

- `https://nightly.repo.amd.com/rocm/core/tarball/` ← use this one

> ⚠️ Two listing hosts disagree. `rocm.nightlies.amd.com` is stale (it stops at an older release and
> 404s the current file). And a plain string `sort` puts `10.2.0a…` *before* `7.9.0rc…` — use
> `sort -V` if you script the lookup.

Extract to e.g. `C:\AI\sdk\therock1151`. It ships clang, hipcc, and the device bitcode.

## 2. Build

```powershell
.\setup\build-windows.ps1 -Src C:\AI\build\strix-llama-win -Sdk C:\AI\sdk\therock1151
```

That configures with `GGML_HIP=ON -DGPU_TARGETS=gfx1151 -DGGML_HIP_GRAPHS=ON` and builds `llama-server`
and `llama-bench`, then runs the DLL pin step below.

You also need the Windows SDK (for `vcvars64.bat`) and Ninja.

## 3. Pin the HIP runtime DLLs — do not skip this

```powershell
.\setup\pin-hip-dlls.ps1 -Sdk C:\AI\sdk\therock1151 -BinDir C:\AI\build\strix-llama-win\build-therock\bin
```

**Why:** `ggml-hip.dll` imports `amdhip64_7.dll` by name, and Windows searches the exe's own directory
before System32. With no local copy, the GPU driver's older DLL shadows the SDK's and HIP fails at
device init with a *misleading* error:

```
cudaMemGetInfo failed (invalid argument), returning 0/0
```

The confusing part is that the SDK's own `hipInfo.exe` still works, because it resolves its own
directory. Copying the SDK runtime beside the exe makes the correct pair win.

## 4. Models

| what | file | size |
| --- | --- | --- |
| target | `Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-0000N-of-00009.gguf` (9 shards) | ~100 GB |
| MTP draft head | `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` | 2.6 GB |

The draft head is a **shared** sidecar: it omits `token_embd.weight` and `output_norm.weight` and
borrows them from the target, which is why it must be loaded *as a draft of that target* — not
standalone. (A standalone load fails, and `--fit on`'s auto-fit probe tries exactly that; see below.)

## 5. Run

```bat
llama-server.exe ^
  -m  <target-00001-of-00009.gguf> ^
  -md <mtp-...-shared-Q8_0.gguf> ^
  --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-p-min 0.0 ^
  -dev ROCm0 -ngl 999 --n-gpu-layers-draft 999 -fa on ^
  -fit off --load-mode none -ctk f16 -ctv f16 ^
  -c 262144 -b 8192 -ub 8192 --parallel 1 --host 127.0.0.1 --port 8080
```

### Flag notes that cost us real time

| flag | why |
| --- | --- |
| `-fit off --load-mode none` | **Required with the shared MTP head.** `--fit on` measures the sidecar standalone, which fails (`qwen4exp requires ctx_other to be set`), then silently fits the model *without* accounting for the draft — a large `-ub` then under-reserves memory. |
| `-fa on` | Flash attention. Also a hard prerequisite for the fast sparse path. |
| `-ctk f16 -ctv f16` | **Required.** The sparse-attention path asserts `k->type == F16 && v->type == F16`; `q8_0` KV aborts at model load. |
| `-b/-ub` | 8192 is fine **with** the draft head on current builds. An older note claimed 2048 was mandatory — it no longer is, and lifting it recovered 18–25% prefill. 16384 gives max prefill (no drafter). |
| `-c 262144` | The trained context. Larger `-c` is free at steady state; the KV allocation does not cost throughput. |

### Measurement hygiene (matters on this box)

See the top-level README's *Reproducing measurements* — the rules are the same. The two that bite
hardest here: `wsl --shutdown` before every run, and prefill needs 3–4 warm reps.

## 6. Verify

```powershell
..\kernel-work\fnbench.py --port 8080 --label check --sizes 1024,8192,16384 --gen 128 --repeats 3 --out check.json
```

You should see roughly: prefill ~1000 t/s @16k, decode ~34 t/s with MTP. If you get ~10 t/s decode,
graphs are not running — check the build has `GGML_HIP_GRAPHS=ON`.
