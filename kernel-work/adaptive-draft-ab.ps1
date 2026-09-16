# adaptive-draft-ab.ps1 - does --spec-draft-adaptive beat a fixed draft length?
#
# The controller's claim is that ONE fixed n_max is wrong for both content types at once:
# it overshoots on unpredictable text (prose) and undershoots on predictable text (JSON,
# verbatim quoting). So the honest test is not "adaptive vs fixed" on one prompt -- it is
# whether adaptive tracks the better of two fixed lengths as content changes.
#
# Arms (all with the shared MTP head, --spec-draft-p-min 0.0 so acceptance is the only variable):
#   n2     fixed n_max = 2   (our current production setting)
#   n4     fixed n_max = 4   (a higher fixed ceiling)
#   adapt  --spec-draft-adaptive with n_max = 4  (EMA sizes the draft between 1 and 4)
#
# fnbench --mode both measures two content classes in every arm:
#   corpus = continuation of the repo doc pool (repetitive -> predictable)
#   chat   = a long realistic assistant answer (prose -> unpredictable)
# If adaptive is worth keeping, it should approach n4 on corpus and n2 on chat.
param([int]$Ctx = 32768, [int]$Port = 8660, [int]$Gen = 192)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$draft = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$res   = 'C:\Projects\strix-alloy\kernel-work\results'
$root  = 'C:\Projects\strix-alloy\kernel-work'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

$arms = @(
    @{ name = 'n2';    extra = @('--spec-draft-n-max','2') },
    @{ name = 'n4';    extra = @('--spec-draft-n-max','4') },
    @{ name = 'adapt'; extra = @('--spec-draft-n-max','4','--spec-draft-adaptive') }
)

$rows = @()
foreach ($arm in $arms) {
    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 6
    $tag = "ada-$($arm.name)"
    $o = Join-Path $res "$tag.out"; $e = Join-Path $res "$tag.err"
    Remove-Item $o, $e -ErrorAction SilentlyContinue
    $a = @('-m', $model, '-md', $draft, '-dev', 'ROCm0', '-ngl', '99', '-fa', 'on', '-fit', 'off',
           '--load-mode', 'none', '-ctk', 'f16', '-ctv', 'f16', '-c', "$Ctx", '-b', '2048', '-ub', '2048',
           '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui', '--seed', '1234',
           '--jinja', '--spec-type', 'draft-mtp', '--spec-draft-device', 'ROCm0', '--spec-draft-ngl', '99') + $arm.extra
    Write-Output "=== $($arm.name) : $($arm.extra -join ' ') ==="
    $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                       -RedirectStandardOutput $o -RedirectStandardError $e
    $ok = $false; $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt 600) {
        if ($p.HasExited) { break }
        try { if ((Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200) { $ok = $true; break } } catch { Start-Sleep -Seconds 4 }
    }
    if (-not $ok) {
        Write-Output "  NOT READY"
        Select-String -Path $e -Pattern 'failed to allocate|error|invalid' | Select-Object -Last 3 | ForEach-Object { Write-Output ('   ' + $_.Line.Trim()) }
        if (-not $p.HasExited) { & taskkill /F /PID $p.Id 2>&1 | Out-Null }
        $rows += [pscustomobject]@{ arm = $arm.name; mode = '-'; decode = $null; accept_pct = $null; prefill = $null }
        continue
    }
    Write-Output ("  ready in {0}s" -f [int]((Get-Date)-$t0).TotalSeconds)
    $out = Join-Path $res "$tag.json"
    python "$root\fnbench.py" --port $Port --label $tag --sizes '1024,8192' --gen $Gen --repeats 3 --mode both `
        --context-limit ($Ctx - $Gen - 64) --out $out 2>&1 | ForEach-Object { Write-Output ('  ' + $_) }
    if (-not $p.HasExited) { & taskkill /F /PID $p.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 3

    if (Test-Path $out) {
        $j = Get-Content $out -Raw | ConvertFrom-Json
        foreach ($kind in 'corpus','chat') {
            $rr = $j.rows | Where-Object { $_.kind -eq $kind -and -not $_.error }
            if ($rr.Count -eq 0) { continue }
            $d = ($rr | ForEach-Object { $_.decode_tps }) | Sort-Object
            $accN = ($rr | ForEach-Object { [double]$_.draft_n_accepted }) | Measure-Object -Sum
            $accD = ($rr | ForEach-Object { [double]$_.draft_n }) | Measure-Object -Sum
            $pct = if ($accD.Sum -gt 0) { [math]::Round(100.0*$accN.Sum/$accD.Sum, 1) } else { $null }
            $rows += [pscustomobject]@{ arm = $arm.name; mode = $kind; decode = [math]::Round($d[-1],2); accept_pct = $pct; prefill = $null }
        }
    }
}

Write-Output ''
Write-Output '=== MTP decode (best of reps) by arm x content ==='
$rows | Where-Object { $_.mode -ne '-' } | Format-Table -AutoSize | Out-String | Write-Output
$rows | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $res 'adaptive-draft-ab.json')

Write-Output '=== interpretation ==='
foreach ($kind in 'corpus','chat') {
    $a2 = ($rows | Where-Object { $_.arm -eq 'n2'    -and $_.mode -eq $kind }).decode
    $a4 = ($rows | Where-Object { $_.arm -eq 'n4'    -and $_.mode -eq $kind }).decode
    $ad = ($rows | Where-Object { $_.arm -eq 'adapt' -and $_.mode -eq $kind }).decode
    if ($a2 -and $a4 -and $ad) {
        $best = [Math]::Max($a2, $a4)
        Write-Output ("  {0,-7} n2={1,6:N2}  n4={2,6:N2}  adaptive={3,6:N2}   best fixed={4,6:N2}  adaptive vs best={5:+0.0;-0.0}%" -f `
            $kind, $a2, $a4, $ad, $best, (100*($ad-$best)/$best))
    }
}
Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { & taskkill /F /PID $_.Id 2>&1 | Out-Null }
Write-Output 'done'
