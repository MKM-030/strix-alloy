# requires-Version 5.1
# verify-all.ps1 — end-to-end health check after the HIP DLL fix.
$ErrorActionPreference = 'Continue'
$res = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results'
$sdk = 'C:\AI\sdk\therock1151'
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function ReadShared([string]$p) {
    if (-not (Test-Path $p)) { return '' }
    try { $fs = [IO.File]::Open($p,'Open','Read','ReadWrite'); $sr=New-Object IO.StreamReader($fs); $t=$sr.ReadToEnd(); $sr.Close(); $fs.Close(); $t }
    catch { '' }
}

Write-Output '=== 1. pinned DLLs (must be the SDK sizes, NOT 17,512,464) ==='
foreach ($f in @('amdhip64_7.dll','amd_comgr.dll','amdocl64.dll')) {
    $p = "C:\AI\build\strix-llama-win\build-therock\bin\$f"
    if (Test-Path $p) {
        $i = Get-Item $p
        $ok = if ($f -eq 'amdhip64_7.dll') { $i.Length -eq 16578560 } else { $true }
        Write-Output ("  {0,-18} {1,12:N0} bytes  {2}  {3}" -f $i.Name, $i.Length, $i.LastWriteTime, $(if ($ok) {'OK'} else {'WRONG COPY'}))
    } else { Write-Output "  $f MISSING" }
}

Write-Output ''
Write-Output '=== 2. SDK hipInfo (vendor probe, should always work) ==='
$o = (& "$sdk\bin\hipInfo.exe" 2>&1 | Out-String)
foreach ($ln in (($o -replace "`r",'') -split "`n")) {
    if ($ln -match 'device#|Name:|totalGlobalMem|multiProcessorCount') { Write-Output ("  " + $ln.Trim()) }
}

Write-Output ''
Write-Output '=== 3. llama-hidden-dump (training harness) ==='
$hd = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-hidden-dump.exe'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$pre = Join-Path $res 'verify-hd'
Remove-Item "$pre.h","$pre.tokens","$pre.json" -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $hd -ArgumentList @('-m',$model,'-f','C:\Projects\REV-N-ornith-eval-20260911\kernel-work\bench-corpus.txt',
      '--out',$pre,'--ntokens','1024','--window','1024','-c','1024','-b','1024','-ngl','99') `
      -PassThru -RedirectStandardOutput (Join-Path $res 'verify-hd.out') -RedirectStandardError (Join-Path $res 'verify-hd.err') -NoNewWindow
$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt 420) { if ($p.HasExited) { break }; Start-Sleep -Seconds 5 }
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
Start-Sleep -Seconds 2
$err = ReadShared (Join-Path $res 'verify-hd.err')
foreach ($needle in @('cudaMemGetInfo failed','threadpool init','hidden-dump: wrote')) {
    Write-Output ("  {0,-26} {1}" -f $needle, $(if ($err -match [regex]::Escape($needle)) {'YES'} else {'--'}))
}
if (Test-Path "$pre.h") {
    $h = Get-Item "$pre.h"
    Write-Output ("  output: {0:N0} bytes  (expect {1:N0} = 1024 x 10240 x 2)" -f $h.Length, (1024*10240*2))
} else { Write-Output '  output: MISSING' }

Write-Output ''
Write-Output '=== 4. memory ==='
$os = Get-CimInstance Win32_OperatingSystem
Write-Output ("  free {0:N1} GB / total {1:N1} GB" -f ($os.FreePhysicalMemory/1MB), ($os.TotalVisibleMemorySize/1MB))
