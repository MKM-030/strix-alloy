#requires -Version 5.1
# crash-evidence.ps1 — READ-ONLY. What happened when llama-server died on this boot?
$ErrorActionPreference = 'Continue'
$since = (Get-Date).AddHours(-2)

Write-Output '=== Application log: errors/faults in the last 2h ==='
try {
    Get-WinEvent -FilterHashtable @{ LogName='Application'; StartTime=$since } -ErrorAction Stop |
        Where-Object { $_.LevelDisplayName -in @('Error','Warning','Critical') } |
        Select-Object -First 25 |
        ForEach-Object {
            Write-Output ("  {0} [{1}] id={2}" -f $_.TimeCreated.ToString('HH:mm:ss'), $_.ProviderName, $_.Id)
            $m = ($_.Message -split "`n") | Where-Object { $_.Trim() } | Select-Object -First 3
            foreach ($l in $m) { Write-Output ("      " + $l.Trim()) }
        }
} catch { Write-Output "  (query failed: $($_.Exception.Message))" }

Write-Output ''
Write-Output '=== Application log: anything naming llama / HIP / amd ==='
try {
    Get-WinEvent -FilterHashtable @{ LogName='Application'; StartTime=$since } -ErrorAction Stop |
        Where-Object { $_.Message -match '(?i)llama|ggml|hip|rocm|amdfendr|AMD' } |
        Select-Object -First 15 |
        ForEach-Object { Write-Output ("  {0} [{1}] {2}" -f $_.TimeCreated.ToString('HH:mm:ss'), $_.ProviderName, (($_.Message -split "`n")[0]).Trim()) }
} catch { Write-Output "  (query failed)" }

Write-Output ''
Write-Output '=== WER / crash reports ==='
$werPaths = @(
    "$env:LOCALAPPDATA\CrashDumps",
    "$env:ProgramData\Microsoft\Windows\WER\ReportArchive",
    "$env:ProgramData\Microsoft\Windows\WER\ReportQueue"
)
foreach ($p in $werPaths) {
    if (Test-Path $p) {
        Write-Output "  --- $p ---"
        Get-ChildItem $p -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '(?i)llama|ggml' -or $_.LastWriteTime -gt $since } |
            Select-Object -First 10 |
            ForEach-Object { Write-Output ("      {0}  {1}  {2}" -f $_.LastWriteTime.ToString('HH:mm:ss'), $_.Name, $_.Length) }
    }
}

Write-Output ''
Write-Output '=== processes possibly holding the GPU (dxg/d3d compute) ==='
Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '(?i)llama|ggml|vmmem|wsl|docker|vmcompute|RadeonSoftware|amdow|amdfendr' } |
    Select-Object Name, Id, @{n='MB';e={[int]($_.WorkingSet64/1MB)}}, StartTime |
    ForEach-Object { Write-Output ("  {0,-18} pid={1,-7} {2,6} MB  started={3}" -f $_.Name, $_.Id, $_.MB, $_.StartTime) }

Write-Output ''
Write-Output '=== memory ==='
$os = Get-CimInstance Win32_OperatingSystem
Write-Output ("  free {0:N1} GB / total {1:N1} GB" -f ($os.FreePhysicalMemory/1MB), ($os.TotalVisibleMemorySize/1MB))

Write-Output ''
Write-Output '=== ROCm SDK present? (the runtime we link against) ==='
$sdk = 'C:\AI\sdk\therock1151'
Write-Output ("  $sdk exists = " + (Test-Path $sdk))
foreach ($f in @('bin\amdhip64.dll','bin\hiprtc*.dll','bin\rocblas.dll','bin\hipblas.dll')) {
    $hit = Get-ChildItem (Join-Path $sdk $f) -ErrorAction SilentlyContinue | Select-Object -First 1
    Write-Output ("    {0,-24} {1}" -f $f, $(if ($hit) { "$($hit.Name)  $($hit.Length) bytes  $($hit.LastWriteTime)" } else { 'MISSING' }))
}
