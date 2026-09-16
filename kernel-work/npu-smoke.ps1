# npu-smoke.ps1 — NPU preservation check to run per boot arm.
# HONEST SCOPE: this verifies the NPU *device and driver* load correctly (a necessary condition).
# There is no NPU inference runtime (FastFlowLM/FLM or similar) installed on this box, so this
# script CANNOT prove NPU *execution* the way the review asks. If a runtime is added, call it here.
param([string]$Label = 'arm', [string]$OutRoot = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\windows-ab')
$ErrorActionPreference = 'Continue'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $OutRoot "$stamp-$Label-npu"
New-Item -ItemType Directory -Path $out -Force | Out-Null

$rows = @()
$dev = Get-PnpDevice -PresentOnly | Where-Object { $_.Class -eq 'ComputeAccelerator' -or $_.FriendlyName -match 'NPU|Neural|XDNA' }
foreach ($d in $dev) {
    $rows += [pscustomobject]@{
        FriendlyName = $d.FriendlyName
        Status       = $d.Status
        Class        = $d.Class
        Problem      = $d.Problem
        InstanceId   = $d.InstanceId
    }
}
$rows | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'npu-devices.json') -Encoding UTF8

$drv = Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceName -match 'NPU|Neural|Accelerator' } |
    Select-Object DeviceName, DriverVersion, DriverProviderName, InfName, IsSigned
$drv | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'npu-driver.json') -Encoding UTF8

$hv = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
@"
NPU preservation check -- label $Label at $(Get-Date -Format o)
HypervisorPresent = $hv

Devices found: $($rows.Count)
$($rows | ForEach-Object { "  [$($_.Status)] $($_.FriendlyName)  (problem=$($_.Problem))" } | Out-String)

SCOPE LIMIT: this proves device/driver presence and health, NOT NPU execution.
No NPU inference runtime (FLM/FastFlowLM) is installed on this box, so execution
cannot be demonstrated here. A healthy device is a NECESSARY but not SUFFICIENT gate.

Compare against the pre-change baseline before accepting a boot arm.
"@ | Set-Content -LiteralPath (Join-Path $out 'NPU-CHECK.txt') -Encoding UTF8

Write-Output "NPU check written to $out"
Get-Content (Join-Path $out 'NPU-CHECK.txt')
