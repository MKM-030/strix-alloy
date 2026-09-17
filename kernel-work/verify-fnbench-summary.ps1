# verify-fnbench-summary.ps1 - prove the repaired fnbench summary works end-to-end.
#
# fnbench.py gained a warm-rep median summary and a rep>=3 warning, and its corpus builder no
# longer reads a private path. Both changes touch output paths that scripts parse, so verify with a
# real server rather than only a syntax check.
param([int]$Port = 8760)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$root = 'C:\Projects\strix-alloy-clean\kernel-work'
$res  = Join-Path $root 'results'
New-Item -ItemType Directory -Force -Path $res | Out-Null

Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /T /PID $_.Id 2>&1 | Out-Null }
Start-Sleep -Seconds 5
$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$o = Join-Path $res 'vfs.out'; $e = Join-Path $res 'vfs.err'
Remove-Item $o, $e -ErrorAction SilentlyContinue
$a = @('-m', $model, '-dev', 'ROCm0', '-ngl', '99', '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
       '-ctk', 'f16', '-ctv', 'f16', '-c', '8192', '-b', '2048', '-ub', '2048',
       '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui', '--seed', '1234')
$p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                   -RedirectStandardOutput $o -RedirectStandardError $e
Write-Output 'loading...'
$ok = $false; $t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt 600) {
    if ($p.HasExited) { break }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok = $true; break } } catch { Start-Sleep -Seconds 4 }
}
if (-not $ok) { Write-Output 'NOT READY'; Get-Content $e -Tail 8; exit 1 }
Write-Output ("ready in {0}s" -f [int]((Get-Date)-$t0).TotalSeconds)

# 2 sizes, 4 reps -> exercises the median path AND clears the rep>=3 rule
python "$root\fnbench.py" --port $Port --label vfs --sizes '1024,4096' --gen 32 --repeats 4 `
    --context-limit 8000 --out (Join-Path $res 'vfs.json') 2>&1 | ForEach-Object { Write-Output $_ }

& taskkill /F /T /PID $p.Id 2>&1 | Out-Null
Write-Output ''
Write-Output '=== corpus identity file ==='
$cid = Join-Path $root 'bench-corpus.sha256'
if (Test-Path $cid) { Get-Content $cid } else { Write-Output '  MISSING bench-corpus.sha256' }
Write-Output '=== json has warm rep counts? ==='
$j = Join-Path $res 'vfs.json'
if (Test-Path $j) {
    $d = Get-Content $j -Raw | ConvertFrom-Json
    if ($d.sizes_warm_rep_count) { Write-Output ('  ' + ($d.sizes_warm_rep_count | ConvertTo-Json -Compress)) }
    else { Write-Output '  field ABSENT' }
}
Write-Output 'done'
