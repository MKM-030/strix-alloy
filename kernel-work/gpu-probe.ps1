# gpu-probe.ps1 — does the ROCm device initialize on THIS boot? (still on arm C until reboot)
# Runs the server for at most ~20 s and reports whether it gets past device init.
# A healthy boot reaches 'llama threadpool init' / 'constructing llama_context'.
param([int]$WaitSeconds = 25)
$ErrorActionPreference = 'Continue'
$bin = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk = 'C:\AI\sdk\therock1151'
$res = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$err = Join-Path $res 'gpuprobe.err'
$out = Join-Path $res 'gpuprobe.out'
Remove-Item $err,$out -ErrorAction SilentlyContinue
$a = @('-m',$model,'-dev','ROCm0','-ngl','99','-fa','on','-fit','off','--load-mode','none',
       '-c','2048','-b','512','-ub','512','--parallel','1','--host','127.0.0.1','--port','8299','--no-webui')
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$exited = $false
while ((Get-Date) -lt $deadline) {
    if ($p.HasExited) { $exited = $true; break }
    Start-Sleep -Milliseconds 500
}
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
Start-Sleep -Seconds 1

function Read-Txt($path) {
    if (-not (Test-Path $path)) { return '' }
    $bytes = [IO.File]::ReadAllBytes($path)
    if ($bytes.Length -gt 4 -and ($bytes[1] -eq 0)) { return [Text.Encoding]::Unicode.GetString($bytes) }
    return [Text.Encoding]::UTF8.GetString($bytes)
}
$etxt = Read-Txt $err
$otxt = Read-Txt $out

Write-Output "process exited within ${WaitSeconds}s = $exited"
Write-Output "stderr bytes = $($etxt.Length) ; stdout bytes = $($otxt.Length)"
Write-Output ''
foreach ($m in @('cudaMemGetInfo failed','ROCm devices','loading model','threadpool init',
                 'constructing llama_context','listening on','error','failed')) {
    $locs = @()
    foreach ($pair in @(@('err',$etxt), @('out',$otxt))) {
        if ($pair[1] -match [regex]::Escape($m)) { $locs += $pair[0] }
    }
    Write-Output ("  {0,-28} {1}" -f $m, $(if ($locs.Count) { 'FOUND in ' + ($locs -join '+') } else { '-' }))
}
Write-Output ''
Write-Output '--- stderr (last 12 lines) ---'
($etxt -split "`n") | Where-Object { $_.Trim() } | Select-Object -Last 12 | ForEach-Object { Write-Output ("  " + $_.Trim()) }
Write-Output '--- stdout (last 8 lines) ---'
($otxt -split "`n") | Where-Object { $_.Trim() } | Select-Object -Last 8 | ForEach-Object { Write-Output ("  " + $_.Trim()) }
