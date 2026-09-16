#requires -Version 5.1
# final-diag.ps1 — READ-ONLY. Reads files with FileShare (no lock errors), dates the GPU-hang
# reports, confirms whether Vulkan really used the GPU, and looks for ROCm caches/logs.
$ErrorActionPreference = 'Continue'
$res = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'

function ReadShared([string]$path) {
    if (-not (Test-Path $path)) { return '' }
    try {
        $fs = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        $sr = New-Object IO.StreamReader($fs)
        $t = $sr.ReadToEnd(); $sr.Close(); $fs.Close(); return $t
    } catch { return "<could not read: $($_.Exception.Message)>" }
}

Write-Output '=== 1. VULKAN test log: did it load onto the GPU? ==='
foreach ($f in @('vktest.out','vktest.err')) {
    $t = ReadShared (Join-Path $res $f)
    if (-not $t) { Write-Output "  $f : (empty/missing)"; continue }
    Write-Output "  --- $f ($($t.Length) chars) ---"
    foreach ($ln in ($t -split "`n")) {
        if ($ln -match '(?i)vulkan|device|offload|VRAM|buffer size|error|model loaded|listening') {
            Write-Output ("    " + $ln.Trim())
        }
    }
}

Write-Output ''
Write-Output '=== 2. date the Kernel_141 (GPU hang) reports from their Report.wer EventTime ==='
$q = 'C:\ProgramData\Microsoft\Windows\WER\ReportQueue'
if (Test-Path $q) {
    $dirs = Get-ChildItem $q -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 4
    foreach ($d in $dirs) {
        $wer = Join-Path $d.FullName 'Report.wer'
        $t = ReadShared $wer
        $et = ($t -split "`n" | Where-Object { $_ -match '^EventTime=' } | Select-Object -First 1)
        Write-Output ("  {0}  (folder mtime {1})" -f $d.Name, $d.LastWriteTime.ToString('MM-dd HH:mm:ss'))
        if ($et) { Write-Output ("      " + $et.Trim()) }
    }
}

Write-Output ''
Write-Output '=== 3. adapter memory as Windows sees it ==='
Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
    Select-Object Name, @{n='AdapterRAM_GB';e={[math]::Round($_.AdapterRAM/1GB,2)}}, DriverVersion,
                  @{n='VideoProcMem_MB';e={[math]::Round((Get-CimInstance Win32_VideoController -Filter "Name='$($_.Name)'").AdapterRAM/1MB,0)}} |
    Format-List

Write-Output ''
Write-Output '=== 4. ROCm/HIP caches and logs ==='
$cands = @(
    "$env:LOCALAPPDATA\AMD", "$env:APPDATA\AMD", "$env:USERPROFILE\.rocm", "$env:USERPROFILE\.hip",
    "$env:TEMP\hip", "$env:TEMP\rocm", "$env:ProgramData\AMD", "$env:ProgramData\ROCm"
)
foreach ($c in $cands) {
    if (Test-Path $c) {
        Write-Output "  EXISTS: $c"
        Get-ChildItem $c -ErrorAction SilentlyContinue | Select-Object -First 6 |
            ForEach-Object { Write-Output ("      " + $_.Name) }
    }
}
Write-Output '  --- recent hip/rocm/amd log files anywhere obvious ---'
foreach ($root in @($env:TEMP, "$env:LOCALAPPDATA")) {
    Get-ChildItem $root -Recurse -Depth 2 -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)hip|rocm|amdgpu|hsa' -and $_.LastWriteTime -gt (Get-Date).AddHours(-3) } |
        Select-Object -First 10 |
        ForEach-Object { Write-Output ("      {0}  {1}" -f $_.LastWriteTime.ToString('HH:mm:ss'), $_.FullName) }
}

Write-Output ''
Write-Output '=== 5. biggest memory holders right now ==='
Get-Process -ErrorAction SilentlyContinue | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 |
    ForEach-Object { Write-Output ("  {0,-22} {1,7} MB" -f $_.Name, [int]($_.WorkingSet64/1MB)) }
