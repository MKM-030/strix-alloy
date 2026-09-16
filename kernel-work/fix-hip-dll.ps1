#requires -Version 5.1
# fix-hip-dll.ps1 — pin the SDK's HIP runtime beside llama-server.exe.
#
# ROOT CAUSE: ggml-hip.dll imports "amdhip64_7.dll" by name. Windows searches the executable's own
# directory FIRST, then System32, then PATH. With no local copy, the DRIVER's copy in
# C:\Windows\System32 (17,512,464 bytes, 2026-08-18) shadowed the SDK's (16,578,560 bytes).
# The SDK's own hipInfo.exe works; our server - which resolved to System32's - did not.
# Fix: place the SDK runtime beside the exe, which is searched first.
#
# Idempotent. Creates .bak copies of anything it overwrites.
param([switch]$Revert)
$ErrorActionPreference = 'Stop'

$sdkBin   = 'C:\AI\sdk\therock1151\bin'
$buildBin = 'C:\AI\build\strix-llama-win\build-therock\bin'

# the HIP runtime set the SDK build needs at load time
$files = @('amdhip64_7.dll', 'amd_comgr.dll', 'amdocl64.dll')

if ($Revert) {
    foreach ($f in $files) {
        $dst = Join-Path $buildBin $f
        if (Test-Path $dst) { Remove-Item $dst -Force; Write-Output "removed $dst" }
    }
    Write-Output 'reverted.'
    return
}

Write-Output "sdkBin   = $sdkBin"
Write-Output "buildBin = $buildBin"
Write-Output ''
Write-Output '=== before ==='
foreach ($f in $files) {
    $dst = Join-Path $buildBin $f
    $src = Join-Path $sdkBin $f
    Write-Output ("  {0,-20} local={1,-6} sdk={2}" -f $f, (Test-Path $dst), (Test-Path $src))
    if (Test-Path $dst) {
        $d = Get-Item $dst; $s = Get-Item $src
        Write-Output ("      local {0:N0} bytes {1}   vs sdk {2:N0} bytes {3}" -f $d.Length, $d.LastWriteTime, $s.Length, $s.LastWriteTime)
    }
}

Write-Output ''
Write-Output '=== copying SDK runtime beside the exe ==='
foreach ($f in $files) {
    $src = Join-Path $sdkBin $f
    $dst = Join-Path $buildBin $f
    if (-not (Test-Path $src)) { Write-Warning "  source missing, skipped: $src"; continue }
    if (Test-Path $dst) { Copy-Item $dst "$dst.bak" -Force }
    Copy-Item $src $dst -Force
    $i = Get-Item $dst
    Write-Output ("  placed {0,-20} {1,12:N0} bytes  {2}" -f $i.Name, $i.Length, $i.LastWriteTime)
}

Write-Output ''
Write-Output '=== after ==='
foreach ($f in $files) {
    $dst = Join-Path $buildBin $f
    if (Test-Path $dst) {
        $i = Get-Item $dst
        Write-Output ("  local {0,-20} {1,12:N0} bytes  {2}" -f $i.Name, $i.Length, $i.LastWriteTime)
    }
}
Write-Output ''
Write-Output 'Now retest:  .\gpu-probe.ps1'
