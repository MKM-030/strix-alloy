# 1,000 t/s prefill on native Windows: the TheRock clang 24 build (2026-09-15)

**The founder was right.** TheROC publishes **Windows gfx1151 tarballs** in its nightly index; my earlier
"Linux-only, needs a source build" conclusion was wrong. Using the official SDK moved prefill from 593 to
**1,024 t/s** — the published class, reached natively on Windows, with no Linux and no custom runtime.

## The SDK

```
therock-dist-windows-gfx1151-10.2.0a20260915.tar.gz    (1,713,662,621 bytes)
https://nightly.repo.amd.com/rocm/core/tarball/         (644 Windows artifacts, 14 GPU families)
```
Extracted to `C:\AI\sdk\therock1151`. It ships **AMD clang 24.0.0git** targeting
`x86_64-pc-windows-msvc`, `hipcc`, and device libs at `lib\llvm\amdgcn\bitcode`.

Why it was easy to miss: GitHub `RELEASES.md` lists the Linux tarballs and marks native Windows packages
as `TODO`, and the GitHub release assets are empty. The real distribution is the S3 index above.

## Build

`C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe` — same source (fork `d67d5883` +
the `_WIN32` `prefetch()` stub), same flags, **only the SDK/toolchain differs**:

| | build-win (ROCm 7.2) | **build-therock (10.2)** |
| --- | --- | --- |
| clang | 21.0.0git | **24.0.0git** |
| hipcc | 7.2.60201 | TheRock 10.2 nightly |

Configure flags are identical apart from the SDK paths
(`-DCMAKE_HIP_FLAGS="--rocm-path=<sdk> --rocm-device-lib-path=<sdk>\lib\llvm\amdgcn\bitcode"`).

## Measured (token-exact, gen 256, native Windows, WSL shut down, PROJFIX)

### Prefill-oriented: `-b 8192 -ub 8192`, no draft

| depth | prefill t/s | decode t/s |
| ---: | ---: | ---: |
| 1024 | 705–711 | 29.8–30.1 |
| 8192 | **1015–1024** | 28.4–29.3 |
| 16384 | **1015–1019** | 29.2–29.3 |
| 32768 | **998–1000** | 28.9 |

### Prefill max: `-b 16384 -ub 16384` (the author's setting), no draft

| depth | prefill t/s | decode t/s |
| ---: | ---: | ---: |
| 1024 | 710–714 | 30.0–30.1 |
| 8192 | **1020–1021** | 28.7–28.9 |
| 16384 | **1050–1057** | 29.2 |
| 32768 | **1034–1037** | 28.8 |

**Highest measured on this box: 1,057 t/s @16k.** ub 16384 buys +3–5% over 8192 at depth (and it needs
the ctx 65536 headroom we gave it here).

### Decode-oriented: `-b 2048 -ub 2048` + MTP shared head

| depth | prefill t/s | decode t/s | acceptance |
| ---: | ---: | ---: | ---: |
| 1024 | 672–680 | **35.4–35.8** | 62% |
| 8192 | 811–817 | 30.5–30.7 | 51% |
| 16384 | 793–797 | **33.7** | 60% |
| 32768 | 777–779 | **32.7–32.9** | 59% |

## Effect of the toolchain alone (same source, same quant, same flags)

| config | clang 21 | **clang 24** | gain |
| --- | ---: | ---: | ---: |
| prefill @8k (ub 2048 + MTP) | 506 | **811** | +60% |
| prefill @16k | 500 | **793** | +59% |
| prefill @32k | 491 | **777** | +58% |
| prefill @8k (ub 8192, no draft) | 594 | **1015–1024** | +71% |
| decode @16k | 33.4 | 33.7 | +1% |

**Prefill was toolchain-bound; decode was not** — consistent with prefill being compute-bound (WMMA
scheduling, unrolling) and decode being bandwidth/state-bound.

## Where this lands against the published figures

| | prefill | decode |
| --- | ---: | ---: |
| ilintar (native Linux, PROJFIX, retained PM4) | 1204 @0k / 1086 @40k | 26.28 / 16.63 @40k |
| olliehm (Windows, UD-IQ4_XS, TheRock) | 964–1045 | ~24 (no device ckpt) |
| **ours (Windows, PROJFIX, TheRock clang 24)** | **1057 @16k, 1035 @32k** | **33–36 (MTP), 29 (serial)** |

We now **exceed olliehm's Windows band** and are **within ~13% of the author** — on Windows, with no
retained-PM4 runtime and no Linux. We also **exceed his published decode** (33.7 vs 26.3) — though his
16.63 @40k is a depth figure and his MTP was his own weaker half.

The residual ~13% prefill gap is the retained-PM4 runtime (native Linux, `/dev/kfd`), which we cannot
have here by construction.

## Settings to use

```
# max prefill / long ingest
llama-server -m <PROJFIX shard1> -dev ROCm0 -ngl 999 -fa on -fit off --load-mode none \
  -ctk f16 -ctv f16 -c 65536 -b 16384 -ub 16384 --parallel 1

# max decode
... same, plus -md <shared MTP head> --spec-type draft-mtp --spec-draft-n-max 2 \
  -b 2048 -ub 2048          # ub 8192+ breaks the draft load (Bug A)
```
Binary: `C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe`;
run with `PATH` prepended by `C:\AI\sdk\therock1151\bin` and `...\lib\llvm\bin`, and WSL shut down so it
does not hold host RAM.

Carve: **48 GB** (96 GB starves host RAM on this UMA box; see the carve table in
`native-projfix-windows-result-20260915.md`).
