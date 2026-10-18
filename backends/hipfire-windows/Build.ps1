#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$BuildRoot,
    [Parameter(Mandatory = $true)][string]$RustToolchainPath,
    [Parameter(Mandatory = $true)][string]$CargoHome,
    [string]$HipSdkPath = 'C:\Program Files\AMD\ROCm\7.2',
    [ValidateRange(1, 64)][int]$Jobs = 2
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-ExistingDirectory([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    if (-not $item.PSIsContainer) { throw "Expected a directory: $Path" }
    return $item.FullName
}
function Assert-FilePin([string]$Path, $Pin) {
    if ($null -eq $Pin) {
        if (Test-Path -LiteralPath $Path) { throw "Expected absent baseline file: $Path" }
        return
    }
    $item = Get-Item -LiteralPath $Path
    if ($item.PSIsContainer -or $item.Length -ne [long]$Pin[0] -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$Pin[1]) {
        throw "Source hash/length mismatch: $Path"
    }
}

$source = Get-ExistingDirectory $SourcePath
$toolchain = Get-ExistingDirectory $RustToolchainPath
$cargoCache = Get-ExistingDirectory $CargoHome
$sdk = Get-ExistingDirectory $HipSdkPath
$build = [IO.Path]::GetFullPath($BuildRoot)
if ($build.TrimEnd('\') -eq $source.TrimEnd('\') -or
    $build.StartsWith($source.TrimEnd('\') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'BuildRoot must be outside SourcePath.'
}
$workSource = Join-Path $build 'src'
if (Test-Path -LiteralPath $workSource) { throw 'BuildRoot/src already exists; select a fresh build root.' }
$cargo = Join-Path $toolchain 'bin\cargo.exe'
$rustc = Join-Path $toolchain 'bin\rustc.exe'
foreach ($file in @($cargo, $rustc, (Join-Path $sdk 'bin\clang++.exe'), (Join-Path $sdk 'bin\amdhip64_7.dll'))) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required installed file missing: $file" }
}
if (-not (Get-Command link.exe -ErrorAction SilentlyContinue) -or -not $env:LIB) {
    throw 'Run Build.ps1 from an x64 Visual Studio Native Tools/Developer shell with the Windows SDK configured.'
}
$git = (Get-Command git.exe -ErrorAction Stop).Source
$manifestPath = Join-Path $PSScriptRoot 'patches\source-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$patch = Join-Path $PSScriptRoot 'patches\native-windows-ddee82.patch'
$counterPatch = Join-Path $PSScriptRoot 'patches\native-mtp-drafted-counter.patch'
$counterSha = (Get-FileHash -LiteralPath $counterPatch -Algorithm SHA256).Hash.ToLowerInvariant()
$patchSha = (Get-FileHash -LiteralPath $patch -Algorithm SHA256).Hash.ToLowerInvariant()
if ($manifest.baseline_commit -ne 'ddee82c7464946c86f946d89af1b5634f212d466' -or
    $patchSha -ne 'd6beb649176543a76ad146ff2fa8a5143bea8886de87e6cd4215f588ada1f619' -or
    $patchSha -ne $manifest.patch.sha256 -or
    $counterSha -ne 'a5e36c349ccdbc8d1d5eefe219d74f80a1361d7e4a04c0762f807de4d73faa30') { throw 'Pinned patch/manifest identity mismatch.' }
foreach ($entry in $manifest.changed_files) { Assert-FilePin (Join-Path $source $entry.path) $entry.before }
foreach ($name in @('Cargo.toml', 'Cargo.lock')) {
    $entry = $manifest.source_files | Where-Object { $_.path -eq $name }
    Assert-FilePin (Join-Path $source $name) $entry.before
}

New-Item -ItemType Directory -Path $workSource -Force | Out-Null
$copyArgs = @($source, $workSource, '/E', '/XJ', '/XD') + @($manifest.copy.excluded_directories) +
    @('/XF', '*.pyc', '/NFL', '/NDL', '/NP', '/NJH', '/R:0', '/W:0')
& robocopy.exe @copyArgs | Out-Host
if ($LASTEXITCODE -gt 7) { throw "Source copy failed ($LASTEXITCODE)." }
foreach ($entry in $manifest.changed_files) { Assert-FilePin (Join-Path $workSource $entry.path) $entry.before }
# The retained snapshot includes this acceptance-counter instrumentation.
# A pristine upstream input receives it once; an already-counted input keeps it.
$ErrorActionPreference = 'Continue'
& $git -C $workSource apply --reverse --check --whitespace=nowarn $counterPatch 2>$null
$counterPresent = $LASTEXITCODE -eq 0
$ErrorActionPreference = 'Stop'
if (-not $counterPresent) {
    & $git -C $workSource apply --check --whitespace=nowarn $counterPatch
    if ($LASTEXITCODE -ne 0) { throw 'Draft-counter patch is neither present nor applicable.' }
    & $git -C $workSource apply --whitespace=nowarn $counterPatch
    if ($LASTEXITCODE -ne 0) { throw 'Draft-counter patch application failed.' }
}
foreach ($name in @('crates/hipfire-generate/src/common.rs', 'crates/hipfire-generate/src/qwen.rs')) {
    $entry = $manifest.source_files | Where-Object { $_.path -eq $name }
    Assert-FilePin (Join-Path $workSource $name) $entry.before
}
& $git -C $workSource apply --check --whitespace=nowarn $patch
if ($LASTEXITCODE -ne 0) { throw 'Patch applicability check failed; no patch applied.' }
& $git -C $workSource apply --whitespace=nowarn $patch
if ($LASTEXITCODE -ne 0) { throw 'Patch application failed.' }
foreach ($entry in $manifest.changed_files) { Assert-FilePin (Join-Path $workSource $entry.path) $entry.after }

$target = Join-Path $build 'target'
$names = @('PATH', 'CARGO_HOME', 'RUSTUP_HOME', 'RUSTC', 'CARGO_TARGET_DIR', 'CARGO_NET_OFFLINE', 'HIPFIRE_ROCM_PATH', 'HIPFIRE_ROCM_STRICT', 'HIPFIRE_HIPCC', 'ROCM_PATH', 'HIP_PATH')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:PATH = (Join-Path $toolchain 'bin') + ';' + (Join-Path $sdk 'bin') + ';' + $env:PATH
    $env:CARGO_HOME = $cargoCache
    $env:RUSTUP_HOME = Join-Path $build 'rustup-home'
    $env:RUSTC = $rustc
    $env:CARGO_TARGET_DIR = $target
    $env:CARGO_NET_OFFLINE = 'true'
    $env:HIPFIRE_ROCM_PATH = $sdk
    $env:ROCM_PATH = $sdk
    $env:HIP_PATH = $sdk
    $env:HIPFIRE_ROCM_STRICT = '1'
    $env:HIPFIRE_HIPCC = Join-Path $sdk 'bin\clang++.exe'
    Push-Location -LiteralPath $workSource
    try {
        & $cargo build --release --locked --offline --target x86_64-pc-windows-msvc -p hipfire-daemon -p hipfire-cli --jobs $Jobs
        if ($LASTEXITCODE -ne 0) { throw "Native build failed ($LASTEXITCODE)." }
    } finally { Pop-Location }
    $bin = Join-Path $build 'bin'
    New-Item -ItemType Directory -Path $bin -Force | Out-Null
    $binaries = @()
    foreach ($name in @('hipfire.exe', 'daemon.exe')) {
        $compiled = Join-Path $target ('x86_64-pc-windows-msvc\release\' + $name)
        Copy-Item -LiteralPath $compiled -Destination (Join-Path $bin $name)
        $binaries += @{ name = $name; sha256 = (Get-FileHash -LiteralPath $compiled -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
    @{ schema = 'hipfire.windows-build.v1'; baseline_commit = $manifest.baseline_commit; patch_sha256 = $patchSha;
        drafted_counter_patch_sha256 = $counterSha; drafted_counter_already_present = $counterPresent;
        source = $workSource; hip_sdk = $sdk; rust_toolchain = $toolchain; target = 'x86_64-pc-windows-msvc';
        binaries = $binaries; runtime_qualification = 'pending' } |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $build 'build-receipt.json') -Encoding UTF8
    Write-Output "Built native CLI and daemon in $bin. Runtime/model qualification remains separate."
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
