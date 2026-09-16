#requires -Version 5.1
# gpu-wedge.ps1 — READ-ONLY. (a) timestamps of GPU-hang events, (b) does the GPU work via Vulkan
# (a non-ROCm path)? If Vulkan works and HIP does not, the fault is in the ROCm runtime, not the GPU.
$ErrorActionPreference = 'Continue'
$res = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'

Write-Output '=== LiveKernelEvent / GPU-hang evidence (System log, last 6h) ==='
$since = (Get-Date).AddHours(-6)
try {
    Get-WinEvent -FilterHashtable @{ LogName='System'; StartTime=$since } -ErrorAction Stop |
        Where-Object { $_.ProviderName -match 'LiveKernelEvent|Display|amdkmdag|dxgkrnl|WHEA|BugCheck' } |
        Select-Object -First 25 |
        ForEach-Object { Write-Output ("  {0} [{1}] id={2} : {3}" -f $_.TimeCreated.ToString('HH:mm:ss'), $_.ProviderName, $_.Id, (($_.Message -split "`n")[0]).Trim()) }
} catch { Write-Output "  (System-log query failed: $($_.Exception.Message))" }

Write-Output ''
Write-Output '=== WER ReportQueue entries with their FILE timestamps (Kernel_ entries) ==='
$q = 'C:\ProgramData\Microsoft\Windows\WER\ReportQueue'
if (Test-Path $q) {
    Get-ChildItem $q -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^Kernel_|^AppCrash' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 15 |
        ForEach-Object { Write-Output ("  {0}  {1}" -f $_.LastWriteTime.ToString('MM-dd HH:mm:ss'), $_.Name) }
} else { Write-Output '  (no ReportQueue)' }

Write-Output ''
Write-Output '=== minidumps present ==='
$md = 'C:\Windows\Minidump'
if (Test-Path $md) {
    Get-ChildItem $md -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 10 |
        ForEach-Object { Write-Output ("  {0}  {1}" -f $_.LastWriteTime.ToString('MM-dd HH:mm:ss'), $_.Name) }
} else { Write-Output '  (no minidump dir)' }

Write-Output ''
Write-Output '=== VULKAN path test (non-ROCm GPU access) ==='
$vk = 'C:\AI\runtimes\strix-vulkan-ba5354d\llama-server.exe'
Write-Output "  binary: $vk  exists=$(Test-Path $vk)"
if (Test-Path $vk) {
    $model = 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf'
    Write-Output "  model : $model exists=$(Test-Path $model)"
    if (Test-Path $model) {
        $o = Join-Path $res 'vktest.out'; $e = Join-Path $res 'vktest.err'
        Remove-Item $o,$e -ErrorAction SilentlyContinue
        $p = Start-Process -FilePath $vk -ArgumentList @('-m',$model,'-ngl','99','-fa','on','-c','2048','-b','512','-ub','512','--host','127.0.0.1','--port','8298','--no-webui') `
                           -PassThru -RedirectStandardOutput $o -RedirectStandardError $e -NoNewWindow
        $up = $false; $t0 = Get-Date
        while (((Get-Date) - $t0).TotalSeconds -lt 180) {
            if ($p.HasExited) { break }
            try { if ((Invoke-WebRequest 'http://127.0.0.1:8298/health' -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $up = $true; break } } catch { Start-Sleep -Seconds 5 }
        }
        if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
        Write-Output "  VULKAN SERVER READY = $up   (exited=$($p.HasExited) code=$($p.ExitCode))"
        $txt = ''
        foreach ($f in @($e, $o)) { if (Test-Path $f) { $txt += ([IO.File]::ReadAllText($f)) } }
        foreach ($needle in @('found 1 Vulkan','ggml_vulkan','device','error','failed')) {
            if ($txt -match [regex]::Escape($needle)) { Write-Output "    contains: $needle" }
        }
        Write-Output '  --- last 10 lines ---'
        ($txt -split "`n") | Where-Object { $_.Trim() } | Select-Object -Last 10 | ForEach-Object { Write-Output ("    " + $_.Trim()) }
    }
}
