#requires -Version 5.1
# hang-report.ps1 — READ-ONLY, needs ELEVATION. Reads the Kernel_141 (GPU hang) report to date it
# and see which component it names. This is the "what was happening when it broke" artifact.
$ErrorActionPreference = 'Continue'
function ReadShared([string]$path) {
    if (-not (Test-Path $path)) { return '' }
    try {
        $fs = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        $sr = New-Object IO.StreamReader($fs); $t = $sr.ReadToEnd(); $sr.Close(); $fs.Close()
        return $t
    } catch { return '' }
}

$q = 'C:\ProgramData\Microsoft\Windows\WER\ReportQueue'
Write-Output '=== Kernel_141 (GPU hang) report contents ==='
if (-not (Test-Path $q)) { Write-Output '  no ReportQueue'; return }
$dirs = Get-ChildItem $q -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^Kernel_141' } | Sort-Object LastWriteTime -Descending | Select-Object -First 3
if (-not $dirs) { Write-Output '  none'; return }
foreach ($d in $dirs) {
    Write-Output ''
    Write-Output ("--- {0} ---" -f $d.Name)
    $t = ReadShared (Join-Path $d.FullName 'Report.wer')
    if (-not $t) { Write-Output '  (Report.wer unreadable)'; continue }
    foreach ($ln in ($t -split "`n")) {
        if ($ln -match '^(EventType|EventTime|Sig\[|DynamicSig\[|AppName|AppPath|Response\.|ReportDescription|LoadedModule\[') {
            Write-Output ("  " + $ln.Trim())
        }
    }
}

Write-Output ''
Write-Output '=== all Kernel_141 folders by folder-mtime ==='
Get-ChildItem $q -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^Kernel_' } | Sort-Object LastWriteTime -Descending | Select-Object -First 12 |
    ForEach-Object { Write-Output ("  {0}  {1}" -f $_.LastWriteTime.ToString('MM-dd HH:mm:ss'), $_.Name) }

Write-Output ''
Write-Output '=== recent DriverFrameworks / display reset events (System log, 6h) ==='
try {
    Get-WinEvent -FilterHashtable @{ LogName='System'; StartTime=(Get-Date).AddHours(-6) } -ErrorAction Stop |
        Where-Object { $_.ProviderName -match 'Display|Dxgkrnl|amdkmdag|Kernel-PnP|DriverFrameworks' } |
        Select-Object -First 20 |
        ForEach-Object { Write-Output ("  {0} [{1}] id={2} : {3}" -f $_.TimeCreated.ToString('MM-dd HH:mm:ss'), $_.ProviderName, $_.Id, (($_.Message -split "`n")[0]).Trim()) }
} catch { Write-Output "  (none / $($_.Exception.Message))" }
