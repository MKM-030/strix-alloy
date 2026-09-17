#requires -Version 5.1
# carve-sweep.ps1 — benchmark at a SMALL iGPU carve (more host RAM, smaller device pool).
#
# The operator set the dedicated GPU carve to 0.5 GB, which moves the device pool from ~108 GB to
# ~60 GB while freeing host RAM (Windows now sees ~127 GB). On a UMA box the weights are read from host
# RAM, so this may still work — and more free host RAM may reduce the pressure we hit at 96 GB.
#
# Two shapes, same as our published numbers so they are comparable:
#   prefill : -ub 16384, no drafter
#   decode  : -ub 8192, shared MTP head, n-max 2
param(
  [int]$Ctx = 262144,
  [int]$Port = 8470,
  [int]$Gen = 256,
  [int]$Repeats = 3,
  [string]$PrefillSizes = "16384,65536,131072,251904",
  [string]$DecodeSizes  = "16384,65536,131072,251904",
  [string]$Label = "carve05"
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\strix-alloy\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Start-Server([string]$tag, [bool]$withDraft, [int]$ub) {
    Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 5
    $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
        '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$ub",'-ub',"$ub",'--parallel','1',
        '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
    if ($withDraft) {
        $a += @('-md',$head,'--n-gpu-layers-draft','999','--spec-type','draft-mtp',
                '--spec-draft-n-max','2','--spec-draft-p-min','0.0')
    }
    $serr = Join-Path $res "$Label-$tag.err"
    Remove-Item $serr -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru `
        -RedirectStandardOutput (Join-Path $res "$Label-$tag.out") -RedirectStandardError $serr -NoNewWindow
    $ok=$false; $t0=Get-Date
    while (((Get-Date)-$t0).TotalSeconds -lt 900) {
        if ($p.HasExited) {
            Write-Output "[$tag] EXITED rc=$($p.ExitCode) after $([int]((Get-Date)-$t0).TotalSeconds)s"
            $t = Get-Content $serr -Raw -ErrorAction SilentlyContinue
            ($t -split "`n") | Where-Object { $_ -match 'error|failed|out of memory|alloc|GGML_ASSERT|abort' } |
                Select-Object -First 8 | ForEach-Object { '      | ' + $_.Trim() }
            return $null
        }
        try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
    }
    if (-not $ok) { Write-Output "[$tag] NOT READY (timeout)"; return $null }
    Write-Output "[$tag] READY in $([int]((Get-Date)-$t0).TotalSeconds)s (ub=$ub draft=$withDraft)"
    return $p
}

foreach ($shape in @(
    @{ tag='prefill'; draft=$false; ub=16384; sizes=$PrefillSizes },
    @{ tag='decode';  draft=$true;  ub=8192;  sizes=$DecodeSizes  }
)) {
    Write-Output ''
    Write-Output "===== $($shape.tag) shape (ub $($shape.ub)) ====="
    $p = Start-Server $shape.tag $shape.draft $shape.ub
    if (-not $p) { Write-Output "  -> $($shape.tag) could not start"; continue }
    python "$root\fnbench.py" --port $Port --label "$Label-$($shape.tag)" --sizes $shape.sizes `
        --gen $Gen --repeats $Repeats --context-limit $Ctx `
        --out (Join-Path $res "$Label-$($shape.tag).json") 2>&1 |
        Select-String 'n=|skip' | ForEach-Object { '  ' + $_.Line.Trim() }
    Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 3
}
Write-Output ''
Write-Output '=== summary ==='
foreach ($shape in 'prefill','decode') {
    $jp = Join-Path $res "$Label-$shape.json"
    if (-not (Test-Path $jp)) { Write-Output ("  {0,-8} no data" -f $shape); continue }
    $j = Get-Content $jp -Raw | ConvertFrom-Json
    foreach ($g in ($j.rows | Where-Object { -not $_.error } | Group-Object target_n)) {
        $pf = ($g.Group | Where-Object { $_.rep -gt 0 -and $_.prefill_tps } | ForEach-Object { $_.prefill_tps }) | Sort-Object
        $dc = ($g.Group | Where-Object { $_.rep -gt 0 -and $_.decode_tps }  | ForEach-Object { $_.decode_tps })  | Sort-Object
        if (-not $pf) { continue }
        $dn = ($g.Group | Where-Object { $_.draft_n } | Select-Object -Last 1).draft_n
        $da = ($g.Group | Where-Object { $_.draft_n } | Select-Object -Last 1).draft_n_accepted
        $acc = if ($dn) { '{0:P0}' -f ($da/$dn) } else { '' }
        Write-Output ("  {0,-8} n={1,7} prefill={2,7:N0} decode={3,6:N2} {4}" -f $shape, [int]$g.Name, $pf[[int]($pf.Count/2)], $dc[[int]($dc.Count/2)], $acc)
    }
}
Write-Output 'done'
