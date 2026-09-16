#requires -Version 5.1
# round-yield.ps1 — Codex priority 1: separate "round cost grew" from "yield fell" by depth.
param([int]$Ctx = 32768, [int]$B = 2048, [int]$Ub = 2048, [int]$Gen = 384, [int]$Port = 8297)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$blog  = Join-Path $res 'round-yield.log'

Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$a = @('-m',$model,'-md',$head,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
  '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$B",'-ub',"$Ub",'--parallel','1',
  '--host','127.0.0.1','--port',"$Port",'--no-webui',
  '--spec-type','draft-mtp','--spec-draft-n-max','2')
$serr = Join-Path $res 'ry-server.err'
Remove-Item $serr -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res 'ry-server.out') -RedirectStandardError $serr -NoNewWindow
$ok=$false; $t0=Get-Date
while (((Get-Date)-$t0).TotalSeconds -lt 900) {
  if ($p.HasExited) { Write-Output "EXITED $($p.ExitCode)"; break }
  try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
}
if ($ok) {
  Write-Output "READY $([int]((Get-Date)-$t0).TotalSeconds)s"
  python "$root\fnbench.py" --port $Port --label 'ry' --sizes "1024,8192,16384" --gen $Gen --repeats 1 `
    --out (Join-Path $res 'ry.json') 2>&1 | Tee-Object -FilePath $blog -Append
}
Start-Sleep -Seconds 2
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

Write-Output ''
Write-Output '=== round/yield lines (per size) ==='
$t = ''
try { $t = [IO.File]::ReadAllText($serr) } catch {}
foreach ($l in (($t -replace "`r",'') -split "`n" | Where-Object { $_ -match 'rounds:|prefix survival|draft acceptance' })) {
  Write-Output ("  " + $l.Trim())
}
