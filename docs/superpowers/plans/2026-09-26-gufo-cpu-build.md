# GUFO Focused CPU Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute this plan and independently review the evidence. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obtain a reproducible CPU-only CMake build and real execution of the two required Flash Next sampling/lookup tests.

**Architecture:** Build unchanged pinned GUFO source out of tree, using isolated pinned vcpkg dependencies and the existing compiler in a child-process environment. Preserve source/runtime installations; this is build evidence, not GPU or model qualification.

**Tech Stack:** Windows x64, VS2022 SDK/STL, existing TheRock10.2 clang as a CPU compiler, CMake/Ninja, vcpkg2026.07.29; HIP disabled.

## Global Constraints

- Source snapshots remain clean. Any required engine fix belongs in a separate working checkout and a recorded patch, not a silently modified reference snapshot.
- No model/GPU/WSL execution, broad GPU diagnose command, system-wide package integration, driver/BIOS/carve change or shared SDK replacement.
- Download/build directories stay below `C:\Projects\strix-alloy-research`; do not use D:.
- Parallelism at most four compiler jobs, including dependency builds. Check at least 40 GiB free on C: before dependency acquisition; stop if the working volume approaches 25 GiB free. These are disk safeguards, not runtime RAM admission.
- Reuse the live build/process handle across observation timeouts; do not restart a build merely because a wait yielded.
- The user approved installation/build work as part of isolated optional GUFO support. No separate design-approval question is pending.

### Task 1: Isolated dependencies and required CPU tests

**Files:**
- No integration production-code changes in this task.
- Acquire source: `C:\Projects\strix-alloy-research\deps\vcpkg`.
- Generated binaries/cache: `C:\Projects\strix-alloy-research\build\gufo-cpu` and `deps\downloads`, `deps\binary-cache`.
- Evidence: `C:\Projects\strix-alloy-research\reports\gufo-cpu-build-20260926.md`, plus bounded logs/build manifest alongside it.

**Interfaces:**
- Consumes GUFO `cff564964e8506c0abb3e530cecb55332187ac6c` from `sources\gufo-windows`, clean snapshot.
- Produces configured build directory, CTest results, dependency/version identity and an exact reproducible command record. No claim that a CPU test proves GPU correctness.
- Required target names: `qwen38_flash_next_mtp_sampling_test`, `qwen38_flash_next_prompt_lookup_test`.
- Required CTest names: `qwen38_flash_next.mtp_sampling`, `qwen38_flash_next.prompt_lookup`.

- [ ] **Step 1: Resolve tools and verify source/free-space state.**

```powershell
Get-Volume -DriveLetter C | Select-Object SizeRemaining
git -C C:\Projects\strix-alloy-research\sources\gufo-windows rev-parse HEAD
git -C C:\Projects\strix-alloy-research\sources\gufo-windows status --porcelain=v1
Get-Command cmake,ninja,git | Select-Object Name,Source
Get-Content -LiteralPath C:\AI\sdk\therock1151\.info\version
```

Read GUFO `AGENTS.md`, `docs/WINDOWS.md` and the referenced setup scripts before executing setup. Check the pinned target declarations against `tests/models/qwen38_flash_next/CMakeLists.txt`. Expected source hash above, clean status, sufficient free disk. Never invoke the system `bash.exe`, which would start WSL.

- [ ] **Step 2: Acquire pinned vcpkg, with no existing-directory overwrite.**

```powershell
git clone --branch 2026.07.29 --depth 1 https://github.com/microsoft/vcpkg.git C:\Projects\strix-alloy-research\deps\vcpkg
git -C C:\Projects\strix-alloy-research\deps\vcpkg rev-parse HEAD
```

If the destination exists, inspect it and reuse only when exact identity and clean state are proven; do not reset/delete it. The expected peeled commit is `9e593bb18ea69cc5095e012465dcd675a822ed0d`; mismatch stops acquisition. Read applicable repository instructions and bootstrap entrypoints before running. vcpkg source is bounded; resolved dependency downloads are estimated 1–3 GiB and temporary/installed footprint 3–8 GiB, not promises. Record actual usage and any larger requirements.

- [ ] **Step 3: Bootstrap and install only the required ports.** Run in a fresh child PowerShell environment; no machine/user environment writes, no `vcpkg integrate install`.

```powershell
$env:VCPKG_DISABLE_METRICS = '1'
$env:VCPKG_MAX_CONCURRENCY = '4'
$env:VCPKG_DOWNLOADS = 'C:\Projects\strix-alloy-research\deps\downloads'
$env:VCPKG_DEFAULT_BINARY_CACHE = 'C:\Projects\strix-alloy-research\deps\binary-cache'
New-Item -ItemType Directory -Force -Path $env:VCPKG_DOWNLOADS,$env:VCPKG_DEFAULT_BINARY_CACHE | Out-Null
& C:\Projects\strix-alloy-research\deps\vcpkg\bootstrap-vcpkg.bat -disableMetrics
if ($LASTEXITCODE -ne 0) { throw 'vcpkg bootstrap failed' }
& C:\Projects\strix-alloy-research\deps\vcpkg\vcpkg.exe install icu curl openssl libpng libjpeg-turbo --triplet x64-windows
if ($LASTEXITCODE -ne 0) { throw 'vcpkg dependencies failed' }
```

Preserve installation logs; poll actual live process/session handles. Do not dump the whole environment or credentials. A download/network failure is not evidence of a compiler or model defect. Record concrete errors before choosing a safe alternative.

- [ ] **Step 4: Configure CPU-only with local compiler and VS headers.** The supplied upstream build script unnecessarily copies GPU runtime DLLs for CPU builds, so configure directly. Read/import VS's standard developer environment only in the child process; do not echo imported environment values. `vcvars64.bat` is at `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat`. Preserve actual detected versions in the report. Then:

```powershell
$gufoSource = 'C:\Projects\strix-alloy-research\sources\gufo-windows'
$gufoBuild = 'C:\Projects\strix-alloy-research\build\gufo-cpu'
$gufoClang = 'C:/AI/sdk/therock1151/lib/llvm/bin/clang.exe'
$gufoClangXX = 'C:/AI/sdk/therock1151/lib/llvm/bin/clang++.exe'
cmake -S $gufoSource -B $gufoBuild -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON -DENGINE_ENABLE_HIP=OFF -DGUFO_BUILD_TOOLS=OFF "-DCMAKE_C_COMPILER=$gufoClang" "-DCMAKE_CXX_COMPILER=$gufoClangXX" -DCMAKE_LINKER_TYPE=LLD -DCMAKE_TOOLCHAIN_FILE=C:/Projects/strix-alloy-research/deps/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows -DGUFO_VERSION=cff564964e8506c0abb3e530cecb55332187ac6c
if ($LASTEXITCODE -ne 0) { throw 'CPU configure failed' }
cmake --build $gufoBuild --target qwen38_flash_next_mtp_sampling_test qwen38_flash_next_prompt_lookup_test --parallel 4
if ($LASTEXITCODE -ne 0) { throw 'Required CPU target build failed' }
```

If configuration/build exposes a source incompatibility, keep logs and report it before patching; source snapshots are not an editing target. Do not remove CMake caches in place to hide failed configuration. A distinct explicitly named retry build directory is allowed after diagnosing the differing compiler/configuration.

- [ ] **Step 5: Execute and verify exactly the required tests.** Make the isolated vcpkg DLL directory available only in the test process PATH if CMake did not stage dependencies automatically.

```powershell
ctest --test-dir C:\Projects\strix-alloy-research\build\gufo-cpu -N -R '^qwen38_flash_next\.(mtp_sampling|prompt_lookup)$'
ctest --test-dir C:\Projects\strix-alloy-research\build\gufo-cpu -R '^qwen38_flash_next\.(mtp_sampling|prompt_lookup)$' --output-on-failure --no-tests=error
if ($LASTEXITCODE -ne 0) { throw 'Required CPU tests failed' }
```

Require both named tests executed, zero failures and no missing-model skips. A zero-test match fails even with an old CTest exit code of zero. Report that this is a focused subset, not the full CPU suite, and the10.2 compiler has not qualified GPU numerics. Optional cache/scheduler tests are subsequent work, not substitutes for these two tests.

- [ ] **Step 6: Record evidence and self-review.** Record source commit/clean status, vcpkg commit, installed package versions, compiler/CMake/Ninja/VS versions, CMake settings, actual commands/exit codes, test counts, executable hashes and disk consumption. Classify failures without erasing logs. Return report path and live build handle if work is still running. Do not commit generated build artifacts, dependencies or logs to the integration Git repository.

Main reviews this evidence before GPU build or runtime qualification. No test in this task admits a model load.
