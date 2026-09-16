#requires -Version 5.1
# suspect-hunt.ps1 — READ-ONLY. Remaining suspects for the native-HIP failure.
$ErrorActionPreference = 'Continue'
$res = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'
New-Item -ItemType Directory -Path $res -Force | Out-Null

function Is-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
Write-Output "Elevated = $(Is-Admin)"

Write-Output ''
Write-Output '=== A. HSA/HIP/ROCm/GGML env vars at EVERY scope ==='
foreach ($scope in @('Process','User','Machine')) {
    Write-Output "  --- $scope scope ---"
    $vars = [Environment]::GetEnvironmentVariables($scope)
    $hit = $false
    foreach ($k in ($vars.Keys | Sort-Object)) {
        if ($k -match '(?i)^(HSA|HIP|ROCM|GGML|AMD|MIOPEN|AITER|VLLM)') {
            Write-Output ("      {0} = {1}" -f $k, $vars[$k]); $hit = $true
        }
    }
    if (-not $hit) { Write-Output '      (none)' }
}

Write-Output ''
Write-Output '=== B. is PATH sane, and does it contain the SDK bin? ==='
$bins = ($env:PATH -split ';') | Where-Object { $_ -match '(?i)therock|rocm|hip' }
if ($bins) { foreach ($b in $bins) { Write-Output "      $b" } } else { Write-Output '      (no SDK bin in this shell PATH)' }

Write-Output ''
Write-Output '=== C. Windows Update history (anything installed in the last 24h) ==='
try {
    $s = New-Object -ComObject Microsoft.Update.Session
    $sr = $s.CreateUpdateSearcher()
    $r = $sr.Search("IsInstalled=1 and IsHidden=0")
    $r.Updates | Sort-Object LastDeploymentChangeTime -Descending | Select-Object -First 8 |
        ForEach-Object {
            Write-Output ("      {0}  {1}" -f $_.LastDeploymentChangeTime.ToString('MM-dd HH:mm'), $_.Title)
        }
} catch { Write-Output "      (update query failed: $($_.Exception.Message))" }

Write-Output ''
Write-Output '=== D. SDK diagnostics tools available ==='
$sdk = 'C:\AI\sdk\therock1151'
foreach ($t in @('bin\rocminfo.exe','bin\hipInfo.exe','bin\clinfo.exe','bin\rocminfo','rocminfo.exe','hipInfo.exe')) {
    $p = Join-Path $sdk $t
    if (Test-Path $p) { Write-Output "      FOUND $p" }
}
Write-Output '      --- everything in SDK bin\ ---'
Get-ChildItem (Join-Path $sdk 'bin') -File -ErrorAction SilentlyContinue |
    Select-Object -First 40 | ForEach-Object { Write-Output ("        {0}" -f $_.Name) }
Write-Output '      --- SDK bin\bin\ ? ---'
Get-ChildItem (Join-Path $sdk 'bin\bin') -File -ErrorAction SilentlyContinue |
    Select-Object -First 40 | ForEach-Object { Write-Output ("        {0}" -f $_.Name) }

Write-Output ''
Write-Output '=== E. adapter memory in the registry (the carve) ==='
$classKey = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
Get-ChildItem $classKey -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($p.DriverDesc -match '(?i)radeon|8060') {
        Write-Output ("      key {0}  desc={1}  ver={2}" -f (Split-Path $_.PSPath -Leaf), $p.DriverDesc, $p.DriverVersion)
        foreach ($n in @('HardwareInformation.DedicatedVideoMemory','HardwareInformation.qwMemorySize',
                         'HardwareInformation.MemorySize','HardwareInformation.SystemVideoMemory',
                         'HardwareInformation.SharedSystemMemory','HardwareInformation.AvailVidMem')) {
            if ($p.PSObject.Properties[$n]) {
                $v = $p.$n
                if ($v -is [byte[]]) {
                    $b = New-Object byte[] 8; [Array]::Copy($v, $b, [Math]::Min(8, $v.Length))
                    $v = [BitConverter]::ToUInt64($b, 0)
                }
                if ($v -is [uint64] -or $v -is [int64] -or $v -is [int]) {
                    Write-Output ("          {0} = {1:N0} bytes ({2:N2} GB)" -f $n, $v, ($v / 1GB))
                } else { Write-Output ("          {0} = {1}" -f $n, $v) }
            }
        }
    }
}
