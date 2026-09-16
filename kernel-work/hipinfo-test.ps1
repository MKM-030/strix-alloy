#requires -Version 5.1
# hipinfo-test.ps1 — READ-ONLY. Run each installed HIP runtime's own hipInfo.exe to see whether the
# RUNTIME is broken or only our binary's environment is.
$ErrorActionPreference = 'Continue'
$res = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'

function Run-HipInfo([string]$exe, [string]$label, [string]$prepend) {
    Write-Output "===== $label ====="
    Write-Output "  exe: $exe  exists=$(Test-Path $exe)"
    if (-not (Test-Path $exe)) { Write-Output ''; return }
    $oldPath = $env:PATH
    if ($prepend) { $env:PATH = "$prepend;$env:PATH" }
    $o = ''
    try {
        $o = (& $exe 2>&1 | Out-String)
        $code = $LASTEXITCODE
    } catch { $o = "<invoke failed: $($_.Exception.Message)>"; $code = -999 }
    $env:PATH = $oldPath
    Write-Output "  exit=$code"
    $lines = ($o -replace "`r", '') -split "`n" | Where-Object { $_.Trim() }
    if (-not $lines) { Write-Output '  (no output)' }
    else {
        foreach ($l in ($lines | Select-Object -First 18)) { Write-Output ("    " + $l.Trim()) }
        if ($lines.Count -gt 18) { Write-Output ("    ... ($($lines.Count) lines total)") }
    }
    Write-Output ''
}

# 1. TheRock SDK's own hipInfo (loads its own amdhip64_7.dll from its own dir)
Run-HipInfo 'C:\AI\sdk\therock1151\bin\hipInfo.exe' 'TheRock SDK hipInfo' 'C:\AI\sdk\therock1151\bin'

# 2. ROCm 7.2 install's hipInfo
Run-HipInfo 'C:\Program Files\AMD\ROCm\7.2\bin\hipInfo.exe' 'ROCm 7.2 hipInfo' 'C:\Program Files\AMD\ROCm\7.2\bin'

# 3. Is there a HIP runtime in System32 that could shadow everything?
Write-Output '===== DLL search-order reality check ====='
foreach ($d in @('C:\Windows\System32\amdhip64_7.dll',
                 'C:\AI\sdk\therock1151\bin\amdhip64_7.dll',
                 'C:\AI\build\strix-llama-win\build-therock\bin\amdhip64_7.dll')) {
    if (Test-Path $d) {
        $i = Get-Item $d
        Write-Output ("  PRESENT {0,-70} {1,12:N0} bytes  {2}" -f $d, $i.Length, $i.LastWriteTime)
    } else {
        Write-Output ("  absent  {0}" -f $d)
    }
}
Write-Output ''
Write-Output '  NOTE: Windows searches the exe''s own directory FIRST, then System32, then PATH.'
Write-Output '  So System32\amdhip64_7.dll beats the SDK copy unless a copy sits beside the exe.'
Write-Output '  A copy beside the exe is the standard, minimal fix if the runtimes differ.'

Write-Output ''
Write-Output '===== what ggml-hip.dll actually imports ====='
$ggml = 'C:\AI\build\strix-llama-win\build-therock\bin\ggml-hip.dll'
Write-Output "  $ggml exists=$(Test-Path $ggml)"
if (Test-Path $ggml) {
    $bytes = [IO.File]::ReadAllBytes($ggml)
    $ascii = [Text.Encoding]::ASCII.GetString($bytes)
    foreach ($name in @('amdhip64_7.dll','amdhip64.dll','amdhip64_6.dll','amd_comgr.dll','amd_comgr0702.dll')) {
        if ($ascii -match [regex]::Escape($name)) { Write-Output "      imports (by name string): $name" }
    }
}
