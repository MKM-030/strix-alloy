#requires -Version 5.1
# preflight-audit.ps1 — cheap environment + execution-condition audit (handover #6.2).
# Priority: catch a CONFOUND before spending on correctness work.
# HIP_LAUNCH_BLOCKING is the flagged one: if inherited, it serializes every kernel launch and
# would dominate all our timings.
$ErrorActionPreference = 'Continue'
$res = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'
New-Item -ItemType Directory -Path $res -Force | Out-Null
$out = Join-Path $res 'preflight-audit.json'

$data = [ordered]@{}

Write-Output '=== 1. HIP / ROCm / GGML / LLAMA env at every scope ==='
$found = [ordered]@{}
foreach ($scope in @('Process','User','Machine')) {
    $vars = [Environment]::GetEnvironmentVariables($scope)
    $hits = [ordered]@{}
    foreach ($k in ($vars.Keys | Sort-Object)) {
        if ($k -match '(?i)^(HSA|HIP|ROCM|GGML|AMD|MIOPEN|AITER|VLLM|OCL|GPU)') {
            $hits[$k] = [string]$vars[$k]
        }
    }
    $found[$scope] = $hits
    Write-Output "  --- $scope ---"
    if ($hits.Count -eq 0) { Write-Output '      (none)' }
    else { foreach ($k in $hits.Keys) { Write-Output ("      {0} = {1}" -f $k, $hits[$k]) } }
}
$data.env = $found

# the specific confound
$hlb = @()
foreach ($scope in @('Process','User','Machine')) {
    $v = [Environment]::GetEnvironmentVariable('HIP_LAUNCH_BLOCKING', $scope)
    if ($v) { $hlb += "$scope=$v" }
}
Write-Output ''
if ($hlb.Count -eq 0) { Write-Output 'HIP_LAUNCH_BLOCKING: NOT SET at any scope  -> no confound' }
else { Write-Output ("HIP_LAUNCH_BLOCKING: SET -> " + ($hlb -join ', ') + '   *** CONFOUND ***') }
$data.hip_launch_blocking = ($hlb -join ', ')

Write-Output ''
Write-Output '=== 2. does the SDK ship a HIP_LAUNCH_BLOCKING default anywhere? ==='
$sdk = 'C:\AI\sdk\therock1151'
$hits2 = Get-ChildItem $sdk -Recurse -File -Include '*.bat','*.cmd','*.json','*.txt' -ErrorAction SilentlyContinue |
    Select-String -Pattern 'HIP_LAUNCH_BLOCKING' -List -ErrorAction SilentlyContinue |
    Select-Object -First 5 -ExpandProperty Path
if ($hits2) { foreach ($h in $hits2) { Write-Output "  $h" } } else { Write-Output '  (no SDK file sets it)' }
$data.sdk_sets_hlb = @($hits2)

Write-Output ''
Write-Output '=== 3. GPU / driver state ==='
$gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
       Where-Object { $_.Name -match 'Radeon' } | Select-Object -First 1
if ($gpu) {
    Write-Output ("  {0}  driver {1}" -f $gpu.Name, $gpu.DriverVersion)
    $data.gpu = @{ name = $gpu.Name; driver = $gpu.DriverVersion }
}
$npu = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
       Where-Object { $_.FriendlyName -match 'NPU Compute' } | Select-Object -First 1
Write-Output ("  NPU: " + $(if ($npu) { "$($npu.FriendlyName) [$($npu.Status)]" } else { 'not found' }))
$data.npu = @{ present = [bool]$npu; status = $(if ($npu) { $npu.Status } else { $null }) }

Write-Output ''
Write-Output '=== 4. is another session running heavy work? ==='
$busy = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)llama|ggml|python|vmmem|docker' } |
        Sort-Object WorkingSet64 -Descending | Select-Object -First 8
if ($busy) {
    foreach ($b in $busy) { Write-Output ("  {0,-20} pid={1,-7} {2,7} MB" -f $b.Name, $b.Id, [int]($b.WorkingSet64/1MB)) }
} else { Write-Output '  (nothing heavy)' }
$data.busy = @($busy | ForEach-Object { @{ name=$_.Name; pid=$_.Id; mb=[int]($_.WorkingSet64/1MB) } })

Write-Output ''
Write-Output '=== 5. binary hashes (pin for the record) ==='
$bin = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
foreach ($f in @($bin, 'C:\AI\build\strix-llama-win\build-therock\bin\llama.dll',
                 'C:\AI\build\strix-llama-win\build-therock\bin\ggml-hip.dll')) {
    if (Test-Path $f) {
        $h = (Get-FileHash $f -Algorithm SHA256).Hash
        Write-Output ("  {0,-22} {1}  {2}" -f (Split-Path $f -Leaf), $h.Substring(0,16), (Get-Item $f).LastWriteTime)
    }
}
$data.model = $null

[pscustomobject]$data | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $out -Encoding UTF8
Write-Output ''
Write-Output "audit written: $out"
