# Packaging notes

How the end-user ZIP is assembled, and the one failure mode that cost a release cycle.

## Build

```
packaging\build-release.ps1 -Version 0.1.1
```

Bump `-Version` for each release: it names the ZIP and the checksum file. The script's default is
the most recent published version.

Outputs, by default into `%LOCALAPPDATA%\strix-alloy-release` (override with `-OutDir`):

| file | what |
| --- | --- |
| `strix-alloy-<version>-windows-x64.zip` | the runtime archive |
| `strix-alloy-<version>-SHA256SUMS.txt` | checksums for the release assets |

The script uses an **explicit allowlist**. It never blanket-copies, never follows reparse points,
and never lets the research tree (`kernel-work/`, `artifacts/`, `docs/benchmarks/`) into the ZIP.
The engine binaries come from `-BinSource` (default: the frozen Windows HIP build). Models are never
bundled. A secret/personal-path scan runs on the staged payload and **fails the build** if it finds
credentials or internal markers.

## The DLL closure — derived, not guessed

A first attempt at this package shipped 12 files: the engine binaries plus the three ROCm DLLs that
sit beside them in the engine build directory (`amdhip64_7.dll`, `amd_comgr.dll`, `amdocl64.dll`).
It **could not start**. `llama-server.exe` exited with `0xC0000135` (`STATUS_DLL_NOT_FOUND`) and wrote
**nothing at all** to stdout or stderr, so the launcher log showed an empty server log and no reason.

The cause is HIP's own ROCm library closure, which is **not** in the engine build directory:

```
rocblas.dll  rocsolver.dll  hipblas.dll  libhipblaslt.dll  libtensilelite-host.dll  origami.dll  rocm_kpack.dll
```

Those live in the SDK's `bin\` next to the compiler, which is on the developer PATH — so on the
development machine the missing files are invisible and the engine "just works". Only a clean-PATH
test exposes it.

**Why the first fix was also wrong.** The first correction came from a "copy DLLs in one at a time
until it loads" experiment. That direction is misleading: it stops at the first success and never
proves the other DLLs are unnecessary. It found 6 of the 7 files and missed `rocm_kpack.dll`.

The reliable method is a **static closure**: walk `dumpbin /nologo /dependents` transitively over the
engine roots, skipping system libraries, and collect every non-system DLL that resolves only from the
SDK bin. The build script now also runs a **standalone load check** with a stripped PATH, so this
cannot regress silently.

## Verification the build performs

1. Every allowlisted file exists and is not a reparse point.
2. The staged `runtime\` loads with **no SDK on PATH** (`llama-server.exe --version` exit 0).
3. The staged payload passes the secret/private-content scan.
4. A checksum manifest is written for the ZIP.

Post-build validation (extract to a clean directory, start, complete a real request, stop) is done
separately — see the release validation report. The build script proves the package is *well-formed*;
only the post-build run proves it *serves*.

## Redistribution

llama.cpp is MIT (`LICENSE`, ggml authors). The AMD ROCm components are redistributed under their own
terms, with the relevant license text copied into `licenses\`:

- `amd-comgr-LICENSE.txt` — Apache-2.0 with LLVM exceptions
- `hipcc-LICENSE.txt` — MIT (AMD)

`libomp140.x86_64.dll` is **not** bundled: it is part of the Microsoft Visual C++ OpenMP runtime and is
present in `System32` on any machine with the VC++ redistributable installed. It is listed as a
prerequisite in `docs/user/README.md` rather than copied.
