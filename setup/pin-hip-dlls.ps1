#requires -Version 5.1
# pin-hip-dlls.ps1 — copy the SDK's HIP runtime DLLs beside llama-server.exe.
#
# WHY THIS IS NOT OPTIONAL:
#   ggml-hip.dll imports "amdhip64_7.dll" BY NAME. Windows resolves a DLL by searching
#     (1) the executable's own directory, (2) System32, (3) PATH.
#   With no local copy, the GPU driver's older copy in C:\Windows\System32 shadows the SDK's, and HIP
#   fails at device init with a misleading error:
#       cudaMemGetInfo failed (invalid argument), returning 0/0
#   The SDK's own hipInfo.exe still works (it resolves its own directory), which makes this very hard
#   to diagnose by hand. Placing the SDK runtime beside the exe makes the correct pair win.
#
# Idempotent: skips files that already match, reports what it changes.
param(
    [Parameter(Mandatory = $true)][string]$Sdk,      # e.g. C:\AI\sdk\therock1151
    [Parameter(Mandatory = $true)][string]$BinDir,   # e.g. <build>\bin  (where llama-server.exe lives)
    [switch]$Revert
)
$ErrorActionPreference = 'Stop'

$files = @('amdhip64_7.dll', 'amd_comgr.dll', 'amdocl64.dll')
$sdkBin = Join-Path $Sdk 'bin'

if ($Revert) {
    foreach ($f in $files) {
        $dst = Join-Path $BinDir $f
        if (Test-Path $dst) { Remove-Item $dst -Force; Write-Output "removed $dst" }
    }
    Write-Output 'reverted.'
    exit 0
}

if (-not (Test-Path $sdkBin)) { throw "SDK bin not found: $sdkBin" }
if (-not (Test-Path $BinDir)) { throw "target bin not found: $BinDir" }

$changed = 0
foreach ($f in $files) {
    $src = Join-Path $sdkBin $f
    $dst = Join-Path $BinDir $f
    if (-not (Test-Path $src)) { Write-Warning "SDK runtime missing, skipped: $src"; continue }
    if (Test-Path $dst) {
        $a = (Get-Item $src).Length; $b = (Get-Item $dst).Length
        if ($a -ne $b) { Copy-Item $src $dst -Force; Write-Output "pinned $f ($b -> $a bytes)"; $changed++ }
        else { Write-Output "$f already matches SDK" }
    } else {
        Copy-Item $src $dst -Force; Write-Output "pinned $f (new)"; $changed++
    }
}
Write-Output "done ($changed changed)."
