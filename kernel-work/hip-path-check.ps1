#requires -Version 5.1
# hip-path-check.ps1 — READ-ONLY. Is a second ROCm install shadowing the TheRock SDK?
$ErrorActionPreference = 'Continue'

Write-Output '=== machine PATH entries mentioning ROCm / AMD / HIP ==='
foreach ($scope in @('Machine','User')) {
    Write-Output "  --- $scope PATH ---"
    $p = [Environment]::GetEnvironmentVariable('PATH', $scope)
    if ($p) {
        foreach ($e in ($p -split ';')) {
            if ($e -match '(?i)rocm|hip|amd' -and $e.Trim()) { Write-Output ("      $e") }
        }
    }
}

Write-Output ''
Write-Output '=== does C:\Program Files\AMD\ROCm\7.2 exist, and when was it touched? ==='
$r72 = 'C:\Program Files\AMD\ROCm\7.2'
if (Test-Path $r72) {
    $i = Get-Item $r72
    Write-Output ("  EXISTS  created={0}  modified={1}" -f $i.CreationTime, $i.LastWriteTime)
    Write-Output '  --- bin\ (HIP runtimes) ---'
    Get-ChildItem (Join-Path $r72 'bin') -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)hip|amd' } |
        ForEach-Object { Write-Output ("      {0,-34} {1,12:N0} bytes  {2}" -f $_.Name, $_.Length, $_.LastWriteTime) }
} else { Write-Output '  does NOT exist' }

Write-Output ''
Write-Output '=== comparison: TheRock SDK bin HIP runtimes ==='
$tr = 'C:\AI\sdk\therock1151\bin'
Get-ChildItem $tr -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '(?i)hip|amd' } |
    ForEach-Object { Write-Output ("      {0,-34} {1,12:N0} bytes  {2}" -f $_.Name, $_.Length, $_.LastWriteTime) }

Write-Output ''
Write-Output '=== any other ROCm installs? ==='
foreach ($base in @('C:\Program Files\AMD','C:\Program Files\AMD\ROCm')) {
    if (Test-Path $base) {
        Write-Output "  $base :"
        Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Output ("      {0}   modified={1}" -f $_.Name, $_.LastWriteTime) }
    }
}

Write-Output ''
Write-Output '=== the SDK .hipVersion and what the binary was built against ==='
Get-Content (Join-Path $tr '.hipVersion') -ErrorAction SilentlyContinue | ForEach-Object { Write-Output "  $_" }
$bt = 'C:\AI\build\strix-llama-win\build-therock\CMakeCache.txt'
if (Test-Path $bt) {
    foreach ($ln in (Get-Content $bt -ErrorAction SilentlyContinue)) {
        if ($ln -match 'HIP_ROOT_DIR|ROCM_PATH|HIP_PATH|hip_DIR|AMDDeviceLibs|CMAKE_HIP_COMPILER:') {
            Write-Output ("  " + $ln)
        }
    }
}

Write-Output ''
Write-Output '=== RUNTIME A/B: which amdhip64 does the server actually load? ==='
$bin = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
Write-Output "  binary: $bin  exists=$(Test-Path $bin)"
if (Test-Path $bin) {
    foreach ($dll in @('amdhip64.dll','amdhip64_7.dll')) {
        $hit = Get-ChildItem -Path 'C:\AI','C:\Program Files\AMD','C:\Windows\System32' -Filter $dll -Recurse -Depth 5 -ErrorAction SilentlyContinue |
               Select-Object -First 5
        Write-Output "  --- $dll ---"
        if ($hit) { foreach ($h in $hit) { Write-Output ("      {0}  {1:N0} bytes  {2}" -f $h.FullName, $h.Length, $h.LastWriteTime) } }
        else { Write-Output '      (not found)' }
    }
}
