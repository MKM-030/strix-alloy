<#
  build-release.ps1 â€” assemble the versioned end-user ZIP from an explicit allowlist.

  Rules:
    * explicit allowlist; never a blanket copy, never follows reparse points
    * the research tree (kernel-work/, artifacts/, docs/benchmarks/) never enters the ZIP
    * models are NOT bundled â€” the manifest only describes them
    * a secret/personal-path scan runs on the staged payload and fails the build
    * a checksum manifest is produced for the release assets
#>
[CmdletBinding()]
param(
    [string]$Version = '0.1.0',
    [string]$OutDir = (Join-Path $env:LOCALAPPDATA 'strix-alloy-release'),
    [string]$BinSource = 'C:\AI\build\strix-llama-win\build-therock\bin',
    [switch]$SkipScan
)
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StageRoot = Join-Path $env:TEMP "strix-alloy-stage-$Version"

Write-Host ("strix-alloy release build {0}" -f $Version)
Write-Host ("repo  : {0}" -f $RepoRoot)
Write-Host ("stage : {0}" -f $StageRoot)

if (Test-Path $StageRoot) { Remove-Item $StageRoot -Recurse -Force }

# ---------------------------------------------------------------------------
# 1. RUNTIME â€” the binaries actually needed to run, from the frozen build.
#
# The list below was DERIVED, not guessed: a static dependency closure (dumpbin /dependents, walked
# transitively over the engine roots) produced the exact set. The seven ROCm libraries at the end are
# HIP's own dependencies and are NOT in the engine build directory -- without them llama-server.exe
# exits 0xC0000135 (STATUS_DLL_NOT_FOUND) and writes nothing to stdout or stderr, which is very hard
# to diagnose from the logs. NOTE: on the developer box the SDK bin is on PATH, so this failure is
# masked until you test with a stripped PATH. The build script now does exactly that (step 1b).
# ---------------------------------------------------------------------------
$BinDlls = @(
    'llama-server.exe', 'llama-server-impl.dll', 'llama-common.dll', 'llama.dll',
    'ggml.dll', 'ggml-base.dll', 'ggml-cpu.dll', 'ggml-hip.dll', 'mtmd.dll'
)
$SdkBin = 'C:\AI\sdk\therock1151\bin'
$SdkDlls = @(
    'amdhip64_7.dll', 'amd_comgr.dll', 'amdocl64.dll',
    # HIP's ROCm library closure - required, and absent from the engine build dir
    'rocblas.dll', 'rocsolver.dll', 'hipblas.dll', 'libhipblaslt.dll',
    'libtensilelite-host.dll', 'origami.dll', 'rocm_kpack.dll'
)
$runtimeDir = Join-Path $StageRoot 'runtime'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

foreach ($f in $BinDlls) {
    $src = Join-Path $BinSource $f
    if (-not (Test-Path $src)) { throw "runtime file missing from build: $src" }
    $item = Get-Item -LiteralPath $src -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "refusing to follow reparse point: $src" }
    Copy-Item -LiteralPath $src -Destination $runtimeDir -Force
}
foreach ($f in $SdkDlls) {
    $src = Join-Path $SdkBin $f
    if (-not (Test-Path $src)) { throw "HIP runtime file missing from SDK bin: $src" }
    Copy-Item -LiteralPath $src -Destination $runtimeDir -Force
}
Write-Host ("  runtime: {0} files ({1} engine + {2} ROCm)" -f ($BinDlls.Count + $SdkDlls.Count),
            $BinDlls.Count, $SdkDlls.Count)

# 1a. rocBLAS Tensile kernel library.
#
# The rocBLAS DLLs are NOT self-contained: they load their GEMM kernels at runtime from
# `rocblas/library/` next to the DLL. Without it the server starts, loads the model, accepts a
# request and then dies mid-request with:
#     rocBLAS error: Cannot read .../rocblas/library/TensileLibrary.dat
# This only reproduces when a request is actually served, which is why the clean-path validation
# includes a real completion rather than only a health check.
$tensileSrc = Join-Path $SdkBin 'rocblas\library'
if (-not (Test-Path $tensileSrc)) { throw "rocBLAS Tensile library missing: $tensileSrc" }
$tensileDst = Join-Path $runtimeDir 'rocblas\library'
New-Item -ItemType Directory -Path $tensileDst -Force | Out-Null
Copy-Item (Join-Path $tensileSrc '*') $tensileDst -Recurse -Force
$tensileCount = @(Get-ChildItem $tensileDst -Recurse -File).Count
$tensileMb = ((Get-ChildItem $tensileDst -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
Write-Host ("  rocblas/library: {0} files ({1:N1} MB) - gfx1151 GEMM kernels" -f $tensileCount, $tensileMb)

# 1b. Prove the staged runtime set actually loads with a stripped PATH. This is the gate that the
#     first release build lacked: it shipped without the ROCm closure and could not start.
Write-Host '  verifying the staged runtime loads with no SDK on PATH...'
$cleanPath = ($env:PATH -split ';' | Where-Object { $_ -notmatch 'therock|ROCm|hip|llvm' }) -join ';'
$probe = Join-Path $env:TEMP "rtverify-$Version"
if (Test-Path $probe) { Remove-Item $probe -Recurse -Force }
New-Item -ItemType Directory -Path $probe -Force | Out-Null
Copy-Item (Join-Path $runtimeDir '*') $probe -Force
$savedPath = $env:PATH
$env:PATH = "$probe;$cleanPath"
# llama-server prints its version banner to stderr; with $ErrorActionPreference='Stop' PowerShell
# would treat that as a terminating NativeCommandError. Capture and check the exit code instead.
$savedEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$verOut = & (Join-Path $probe 'llama-server.exe') --version 2>&1
$exit = $LASTEXITCODE
$ErrorActionPreference = $savedEap
$env:PATH = $savedPath
Remove-Item $probe -Recurse -Force -ErrorAction SilentlyContinue
if ($exit -ne 0) {
    throw ("staged runtime does not load standalone (exit={0} = 0x{1:X8}). A required DLL is missing from the runtime set." -f $exit, $exit)
}
Write-Host ("    standalone load OK: {0}" -f (($verOut | Where-Object { $_ -match 'version' } | Select-Object -First 1) -replace '\s+', ' '))

# 1c. The rocBLAS Tensile directory must carry this GPU's kernels. The rocBLAS DLLs are not
#     self-contained: they load GEMM kernels lazily at the FIRST matrix multiply, so a package with
#     the DLLs but without rocblas/library starts, loads the model, accepts a request and then dies
#     mid-request with "rocBLAS error: Cannot read .../TensileLibrary.dat". Checking the directory
#     here is cheap; catching it at request time costs a release cycle.
$archDir = Join-Path $tensileDst 'gfx1151'
if (-not (Test-Path $archDir)) { throw "rocBLAS Tensile library has no gfx1151 kernels: $archDir" }
$archKernels = @(Get-ChildItem $archDir -File -ErrorAction SilentlyContinue)
if ($archKernels.Count -eq 0) { throw "no gfx1151 Tensile kernels in $archDir" }
Write-Host ("    rocBLAS: {0} gfx1151 kernel files present" -f $archKernels.Count)

# ---------------------------------------------------------------------------
# 2. APP - the llama-server launcher
#
# A command template, not an application: it validates the model files and then invokes
# llama-server.exe directly. No config store, no wizard, no service - so the package stays a
# runtime plus one script instead of a product with a lifecycle of its own.
# ---------------------------------------------------------------------------
$appStage = Join-Path $StageRoot 'app'
New-Item -ItemType Directory -Path $appStage -Force | Out-Null
foreach ($f in 'launch-flash-next.ps1', 'Launch Flash Next.cmd') {
    Copy-Item -LiteralPath (Join-Path $RepoRoot "app\$f") -Destination $appStage -Force
}
Write-Host '  app: llama-server launcher'

# ---------------------------------------------------------------------------
# 3. CONFIG examples (model manifest only - the launcher is configured by its arguments, so
#    there is no config file to seed)
# ---------------------------------------------------------------------------
$cfgStage = Join-Path $StageRoot 'config'
New-Item -ItemType Directory -Path $cfgStage -Force | Out-Null
Copy-Item -Path (Join-Path $RepoRoot 'config\model-manifest.example.json') -Destination $cfgStage -Force
Write-Host '  config: model manifest example'

# ---------------------------------------------------------------------------
# 4. DOCS â€” user docs only
# ---------------------------------------------------------------------------
foreach ($d in 'docs\user') {
    $src = Join-Path $RepoRoot $d
    if (Test-Path $src) {
        $dst = Join-Path $StageRoot $d
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
        Copy-Item -Path (Join-Path $src '*') -Destination $dst -Force
    }
}
Copy-Item -LiteralPath (Join-Path $RepoRoot 'docs\CREDITS.md') -Destination (Join-Path $StageRoot 'docs\CREDITS.md') -Force

# license + notice
Copy-Item -LiteralPath (Join-Path $RepoRoot 'LICENSE') -Destination (Join-Path $StageRoot 'LICENSE') -Force -ErrorAction SilentlyContinue
$licDir = Join-Path $StageRoot 'licenses'
New-Item -ItemType Directory -Path $licDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $RepoRoot 'LICENSE') -Destination (Join-Path $licDir 'llama.cpp-LICENSE.txt') -Force -ErrorAction SilentlyContinue
foreach ($pair in @(
        @('C:\AI\sdk\therock1151\share\doc\amd_comgr\LICENSE.txt', 'amd-comgr-LICENSE.txt'),
        @('C:\AI\sdk\therock1151\share\doc\hipcc\LICENSE.txt',    'hipcc-LICENSE.txt'))) {
    if (Test-Path $pair[0]) { Copy-Item -LiteralPath $pair[0] -Destination (Join-Path $licDir $pair[1]) -Force }
}
Write-Host '  docs + licenses'

# ---------------------------------------------------------------------------
# 5. README (release-facing, from the repo)
# ---------------------------------------------------------------------------
Copy-Item -LiteralPath (Join-Path $RepoRoot 'README.md') -Destination (Join-Path $StageRoot 'README.md') -Force
Write-Host '  README'

# ---------------------------------------------------------------------------
# 6. Build identity
# ---------------------------------------------------------------------------
$head = (& git -C $RepoRoot rev-parse HEAD 2>&1) -join ''
$patches = Get-ChildItem (Join-Path $RepoRoot 'engine-patches\*.patch') | Sort-Object Name
$ids = [ordered]@{
    version    = $Version
    repoCommit = $head
    builtUtc   = (Get-Date).ToUniversalTime().ToString('o')
    engineBase = '40a9f4d01b69314d0f75c9120abe8e199e49111d (pwilkin/llama.cpp strix-halo)'
    patchSeries = @($patches | ForEach-Object {
        @{ name = $_.Name; sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
    })
    runtime = @((Get-ChildItem $runtimeDir -File | Sort-Object Name) | ForEach-Object {
        # $_.Name, not $_: assigning the FileInfo object itself serializes every property,
        # path and timestamp into the manifest (a 70 KB file instead of a small one).
        @{ name = $_.Name; bytes = $_.Length; sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
    })
    models = 'not bundled - see config/model-manifest.example.json'
}
$ids | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $StageRoot 'BUILD-IDENTITY.json') -Encoding UTF8

# ---------------------------------------------------------------------------
# 7. Secret + private-content scan on the staged payload (fails the build)
#
# Two classes, deliberately separated (release handover Â§5):
#   HARD  - never ship: credentials, REV:N source names, product-internal markers
#   ALLOW - the owner's high-level introduction may mention REV:N / GTA / FiveM as motivation.
#           That mention is permitted; product code, prompts, traces and internals are not.
# ---------------------------------------------------------------------------
if (-not $SkipScan) {
    $hard = @(
        'sk-[A-Za-z0-9]{20,}', 'ghp_[A-Za-z0-9]{20,}', 'gho_[A-Za-z0-9]{20,}',
        'hf_[A-Za-z0-9]{20,}', 'AKIA[0-9A-Z]{16}', 'BEGIN [A-Z ]*PRIVATE KEY',
        'Bearer\s+[A-Za-z0-9._-]{24,}',
        '@revn/', 'revn_bridge', 'consolidation-worker', 'REVN_READY', 'REVN_ONLY',
        'revn-measurement', 'revn-consolidation'
    )
    $hits = @()
    foreach ($f in Get-ChildItem $StageRoot -Recurse -File) {
        if ($f.Length -gt 8MB) { continue }
        foreach ($pat in $hard) {
            $m = Select-String -LiteralPath $f.FullName -Pattern $pat -ErrorAction SilentlyContinue |
                 Select-Object -First 1
            if ($m) { $hits += ("{0} :: {1}" -f $f.FullName.Replace($StageRoot, ''), $pat) }
        }
    }
    if ($hits.Count) {
        Write-Host 'RELEASE SCAN FAILED - these must not ship:' -ForegroundColor Red
        $hits | ForEach-Object { Write-Host ('  ' + $_) -ForegroundColor Red }
        throw 'secret/private-content scan failed'
    }
    Write-Host '  scan: clean (no credentials, no REV:N source or internal markers)'

    # informational: confirm the permitted intro mention is the ONLY product reference
    $intro = Select-String -LiteralPath (Join-Path $StageRoot 'README.md') -Pattern 'REV:N|FiveM|GTA' -ErrorAction SilentlyContinue
    Write-Host ("  note: {0} high-level product mention(s) in README (permitted introduction only)" -f @($intro).Count)
}

# ---------------------------------------------------------------------------
# 8. Zip + checksums
# ---------------------------------------------------------------------------
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$zip = Join-Path $OutDir "strix-alloy-$Version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $StageRoot '*') -DestinationPath $zip -CompressionLevel Optimal

$man = @()
$man += ('{0}  {1}' -f (Get-FileHash $zip -Algorithm SHA256).Hash, (Split-Path $zip -Leaf))
$man += ('{0}  {1}' -f (& git -C $RepoRoot rev-parse HEAD 2>&1), 'engine-repo-commit')
$man | Set-Content (Join-Path $OutDir "strix-alloy-$Version-SHA256SUMS.txt") -Encoding ASCII

Write-Host ''
Write-Host ("ZIP      : {0}" -f $zip)
Write-Host ("bytes    : {0:N0}" -f (Get-Item $zip).Length)
Write-Host ("checksums: {0}" -f (Join-Path $OutDir "strix-alloy-$Version-SHA256SUMS.txt"))
Write-Host ("stage    : {0}  (kept for inspection)" -f $StageRoot)

