#requires -Version 5.1
# width-equivalence.ps1 — handover A0: does wide-verify produce the SAME greedy tokens as serial?
#
# Why this matters here specifically: our production n-max 2 verifies 3 rows, and the QSA indexer's
# flattened width is 4 x rows -> ne11 = 12, which crosses MMVF_MAX_BATCH_SIZE = 8. So the indexer
# scoring kernel FAMILY differs between serial (ne11=4) and our production (ne11=12). n-max 1
# verifies 2 rows -> ne11 = 8, still MMVF.
#
# Speculative decoding is defined to be output-equivalent to serial greedy. If it is not, we have a
# correctness issue to fix BEFORE optimizing the draft head.
#
# Four arms, run strictly serially (never two 177B instances at once). Every arm emits its raw greedy
# token stream; comparison is CROSS-ARM (reference vs each variant).
#   A  : no drafter                    -> serial greedy          (ne11=4, MMVF)      = REFERENCE
#   A2 : no drafter, repeated          -> same config again      (ne11=4, MMVF)      = DETERMINISM CONTROL
#   B1 : -md head --spec-draft-n-max 1 -> verify 2 rows          (ne11=8, MMVF)
#   B2 : -md head --spec-draft-n-max 2 -> verify 3 rows          (ne11=12, OTHER)    = PRODUCTION
# Generation is forced full-length (ignore_eos) so short-trajectory EOS cannot make the test vacuous.
param(
  [int]$Ctx = 32768,
  [string]$Sizes = "1024,8192",
  [int]$Gen = 200,
  [int]$Port = 8301,
  [int]$Repeats = 2,
  [int]$NProbs = 12,
  [int]$Ub = 2048,
  [int]$Offset = 0,
  [string]$Wrap = "",
  [bool]$IgnoreEos = $true,
  [string]$Arms = "serial,same,n1,n2"
)
$ErrorActionPreference = 'Continue'
$bin  = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk  = 'C:\AI\sdk\therock1151'
$root = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$res  = Join-Path $root 'results'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$head  = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

# arm spec: tag; nmax = 0 means no drafter; env = extra environment overrides for this arm
# (the graphs-off arm isolates a HIP-graph capture defect from an arithmetic/state defect:
#  production decode is dispatch-free, so a wrong captured 3-row verify buffer would show up
#  here as divergence-with-graphs and agreement-without-graphs).
$spec = @{
  'serial'    = @{ nmax = 0; env = @{} };
  'same'      = @{ nmax = 0; env = @{} };
  'n1'        = @{ nmax = 1; env = @{} };
  'n2'        = @{ nmax = 2; env = @{} };
  'n2-nograph'= @{ nmax = 2; env = @{ GGML_CUDA_DISABLE_GRAPHS = '1' } };
  'n1-nograph'= @{ nmax = 1; env = @{ GGML_CUDA_DISABLE_GRAPHS = '1' } };
}

function Start-Arm([string]$tag) {
  $cfg = $spec[$tag]
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 5
  # apply this arm's env overrides; clear any leftover graph override first
  Remove-Item Env:GGML_CUDA_DISABLE_GRAPHS -ErrorAction SilentlyContinue
  foreach ($k in $cfg.env.Keys) { Set-Item -Path "Env:$k" -Value $cfg.env[$k] }
  $a = @('-m',$model,'-dev','ROCm0','-ngl','999','-fa','on','-fit','off','--load-mode','none',
    '-ctk','f16','-ctv','f16','-c',"$Ctx",'-b',"$Ub",'-ub',"$Ub",'--parallel','1',
    '--host','127.0.0.1','--port',"$Port",'--no-webui','--seed','1234')
  if ($cfg.nmax -gt 0) { $a += @('-md',$head,'--spec-type','draft-mtp','--spec-draft-n-max',"$($cfg.nmax)",'--spec-draft-p-min','0.0') }
  $serr = Join-Path $res "vwe-$tag.err"
  Remove-Item $serr -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -RedirectStandardOutput (Join-Path $res "vwe-$tag.out") -RedirectStandardError $serr -NoNewWindow
  $ok=$false; $t0=Get-Date
  while (((Get-Date)-$t0).TotalSeconds -lt 900) {
    if ($p.HasExited) { Write-Output "  [$tag] EXITED $($p.ExitCode)"; return $null }
    try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 5 }
  }
  if (-not $ok) { Write-Output "  [$tag] NOT READY"; return $null }
  Write-Output "  [$tag] READY $([int]((Get-Date)-$t0).TotalSeconds)s (nmax=$($cfg.nmax))"
  python "$root\fnbench.py" --port $Port --label "vwe-warm-$tag" --sizes "1024" --gen 16 --repeats 1 --out (Join-Path $res "vwe-warm-$tag.json") 2>&1 | Out-Null
  $extraArgs = @()
  if ($Offset -gt 0) { $extraArgs += @('--offset', "$Offset") }
  if ($Wrap) { $extraArgs += @('--wrap', $Wrap) }
  if (-not $IgnoreEos) { $extraArgs += @('--respect-eos') }
  python "$root\verify-width-equivalence.py" --port $Port --sizes $Sizes --gen $Gen --repeats $Repeats `
    --n-probs $NProbs --label $tag --out (Join-Path $res "vwe-$tag.json") @extraArgs 2>&1 | Tee-Object -FilePath (Join-Path $res "vwe-$tag.log")
  Start-Sleep -Seconds 2
  Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 3
  return $true
}

foreach ($tag in $Arms.Split(',')) {
  Write-Output "=== arm $tag ==="
  Start-Arm $tag.Trim() | Out-Null
  Write-Output ''
}

Write-Output '=== COMPARISON (cross-arm, token-for-token) ==='
$ser = Get-Content (Join-Path $res 'vwe-serial.json') -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
if (-not $ser) { Write-Output '  no serial reference json'; Write-Output 'done'; return }
$summary = @()
foreach ($tag in ($Arms.Split(',') | Where-Object { $_.Trim() -ne 'serial' })) {
  $tag = $tag.Trim()
  $path = Join-Path $res "vwe-$tag.json"
  if (-not (Test-Path $path)) { Write-Output "  [$tag] MISSING json"; continue }
  $arm = Get-Content $path -Raw | ConvertFrom-Json
  foreach ($s in $ser.rows) {
    $m = $arm.rows | Where-Object { $_.requested_prompt_tokens -eq $s.requested_prompt_tokens } | Select-Object -First 1
    if (-not $m) { Write-Output "  [$tag] prompt $($s.requested_prompt_tokens): no row"; continue }
    if ($s.prompt_sha256 -ne $m.prompt_sha256) {
      Write-Output "  [$tag] prompt $($s.requested_prompt_tokens): PROMPT MISMATCH -> invalid"; continue
    }
    $first = $null
    $lim = [Math]::Min($s.n, $m.n)
    for ($i = 0; $i -lt $lim; $i++) { if ($s.tokens[$i] -ne $m.tokens[$i]) { $first = $i; break } }
    $ident = ($null -eq $first) -and ($s.n -eq $m.n)
    if ($ident) { $verdict = 'IDENTICAL' }
    elseif ($null -eq $first) { $verdict = "PREFIX-OK len differs ser=$($s.n) $tag=$($m.n)" }
    else { $verdict = "DIVERGES at token $first" }
    $det = if ($m.self_consistent) { 'self-consistent' } else { 'NOT self-consistent' }
    Write-Output ("  [$tag] prompt {0,6} tok: ser n={1} {2} n={3}  -> {4}  ({5})" -f `
      $s.requested_prompt_tokens, $s.n, $tag, $m.n, $verdict, $det)
    if ($null -ne $first) {
      $lo = [Math]::Max(0, $first - 3); $hi = [Math]::Min($lim, $first + 4)
      Write-Output ("      ser  [{0}:{1}] = {2}" -f $lo, $hi, ($s.tokens[$lo..$hi] -join ','))
      Write-Output ("      {3} [{0}:{1}] = {2}" -f $lo, $hi, ($m.tokens[$lo..$hi] -join ','), $tag)
      # decisive discriminator: at the first divergence, how strongly did each arm prefer its
      # own token, and what did it think of the other arm's token? a small gap = benign near-tie
      # (float reduction order); a large gap = a materially different computation.
      $refTok = $s.tokens[$first]; $armTok = $m.tokens[$first]
      $sRef = $null; $sArm = $null; $mRef = $null; $mArm = $null
      if ($first -lt $s.probs.Count) { $pr = $s.probs[$first]
        if ($pr.PSObject.Properties["$refTok"]) { $sRef = $pr."$refTok" }
        if ($pr.PSObject.Properties["$armTok"]) { $sArm = $pr."$armTok" } }
      if ($first -lt $m.probs.Count) { $pm = $m.probs[$first]
        if ($pm.PSObject.Properties["$armTok"]) { $mArm = $pm."$armTok" }
        if ($pm.PSObject.Properties["$refTok"]) { $mRef = $pm."$refTok" } }
      $fmt = { param($v) if ($null -eq $v) { 'n/a' } else { ('{0:F3}' -f [double]$v) } }
      $sGap = if ($null -ne $sRef -and $null -ne $sArm) { [double]$sRef - [double]$sArm } else { $null }
      $mGap = if ($null -ne $mArm -and $null -ne $mRef) { [double]$mArm - [double]$mRef } else { $null }
      Write-Output ("      logprob@div token {0} vs {1}: ser[ref={2} alt={3} gap={4}]  {5}[own={6} alt={7} gap={8}]" -f `
        $refTok, $armTok, (& $fmt $sRef), (& $fmt $sArm), (& $fmt $sGap), $tag, (& $fmt $mArm), (& $fmt $mRef), (& $fmt $mGap))
      $summary += [pscustomobject]@{ size=$s.requested_prompt_tokens; arm=$tag; ref_n=$s.n; arm_n=$m.n
        first_divergence=$first; identical=$ident; self_consistent=$m.self_consistent
        ref_sha=$s.token_sha256; arm_sha=$m.token_sha256
        ser_logprob_ref=$sRef; ser_logprob_alt=$sArm; ser_gap=$sGap
        arm_logprob_own=$mArm; arm_logprob_alt=$mRef; arm_gap=$mGap }
    } else {
    $summary += [pscustomobject]@{ size=$s.requested_prompt_tokens; arm=$tag; ref_n=$s.n; arm_n=$m.n
      first_divergence=$first; identical=$ident; self_consistent=$m.self_consistent
      ref_sha=$s.token_sha256; arm_sha=$m.token_sha256 }
    }
  }
}
$summary | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $res 'vwe-summary.json')
Write-Output 'done'
