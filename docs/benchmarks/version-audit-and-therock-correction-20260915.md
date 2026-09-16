# Version audit + correction of my own TheRock claim (2026-09-15)

## 1. I was wrong about "TheRock is Linux-only" — correcting it properly

**What I said earlier:** that the TheRock build is only available for Linux, that our Windows SDK was
therefore behind, and that we would have to build it ourselves to use it on Windows.

**That was wrong, and it is wrong in two separate ways:**

1. **Windows tarballs are published.** `nightly.repo.amd.com/rocm/core/tarball/` serves
   `therock-dist-windows-gfx1151-<version>.tar.gz` for gfx1151 on **every daily build**. We are not
   building TheRock ourselves and never had to.
2. **We are already on the newest one.** Verified by version-sorted listing of that host:

```
therock-dist-windows-gfx1151-10.1.0a20260910.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260911.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260912.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260913.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260914.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260915.tar.gz   <-- ours, HTTP 200
```

**Nothing newer than `20260915` exists on that host as of today.** Our SDK is current, and the exact URL
resolves (HTTP 200). Local file: `C:\AI\sdk\therock-dist-windows-gfx1151-10.2.0a20260915.tar.gz`,
1,713,662,621 bytes, 2026-09-15 09:18.

**Where the confusion came from — worth recording, because it nearly caused a wrong conclusion twice:**
there are **two** TheRock listing hosts, and they disagree:
- `rocm.nightlies.amd.com/tarball/` — the one I first queried. Its newest Windows gfx1151 entry is
  **`7.14.0a20260612`** (June 2026), and it 404s on our filename. It is a different/stale bucket.
- `nightly.repo.amd.com/rocm/core/tarball/` — the correct one, current through today.

I also tripped over **sorting**: `sort` (string) puts `10.2.0a...` *before* `7.9.0rc...`, so my first
`tail -10` displayed June's 7.x builds as if they were the newest. Version-sorting (`sort -V`) is required
for these filenames.

## 2. Toolchain we actually build with (verified)

| item | value |
| --- | --- |
| TheRock SDK | `therock-dist-windows-gfx1151-10.2.0a20260915` (newest published) |
| HIP version | 7.16 (`HIP_PACKAGING_VERSION_PATCH=26370-1091c91191`), git `1091c91191` |
| Compiler | **AMD clang 24.0.0git** (`ROCm/llvm-project` @ `bc1e171b6a53`), target **`x86_64-pc-windows-msvc`** |
| Build | `GGML_HIP=ON`, `GPU_TARGETS=gfx1151`, native Windows |

The compiler target string `x86_64-pc-windows-msvc` is direct proof this is a **native Windows**
toolchain — the Linux question is closed on evidence, not opinion.

**No profiler is shipped in it** (verified earlier: no `rocprof`, `rocprofv2`, `rocprofv3`,
`rocprofiler-sdk`). That is a real limitation for the composition work, but it is not a version problem —
upgrading would not change it.

## 3. What a newer TheRock would and would not give us

Since we are already newest, the actionable question is what the *next* build might carry:
- **clang toolchain bump** — this was the single biggest measured win we found (clang 21 → 24 gave
  **+60–71% prefill**). If a future build moves to a newer LLVM, re-measuring is worthwhile.
- **Nothing else promised.** MMB, QSA, PLE and the hyper-connection kernels are in the *llama.cpp fork*,
  not the SDK. Those advance with the fork, not the toolchain.

So: **no SDK upgrade is available or needed today.** Re-check when an LLVM bump lands.

## 4. Driver (the other half of "are we current")

| item | value / status |
| --- | --- |
| GPU | AMD Radeon(TM) 8060S Graphics, `PCI\VEN_1002&DEV_1586`, `CM_PROB_NONE`, ConfigManagerErrorCode 0 |
| Driver version | `32.0.31041.1004` (driver date 2026-08-17) |
| Not changed by us | Reinstalling/upgrading the GPU driver was **considered and not done** — it was a candidate GPU recovery step that proved unnecessary once the real cause (the `amdhip64_7.dll` shadowing) was found. |
| NPU | `NPU Compute Accelerator Device`, `CM_PROB_NONE` |

Driver `32.0.31041.1004` is the driver that has produced every measurement in this project, and it is the
version our baseline was taken on — so it is the correct one to keep for comparability. If we ever do
upgrade it, **every benchmark needs re-baselining**, because we have no evidence the numbers are
driver-invariant.

## 5. Repo pins (our side)

| component | pin |
| --- | --- |
| llama.cpp fork | `pwilkin/llama.cpp`, branch `strix-halo`, base commit **`40a9f4d0`** + our 3 windows commits |
| our branch | `win-native`, clean working tree |
| model | `ilintar/qwen3.8-flash-next-gguf-strix-halo` (PROJFIX), 9 shards |
| MTP head | `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` |
| draft head source | `drluoto/Qwen3.8-Flash-Next-MTP-GGUF` |

Upstream-delta check on these repos is running separately.
