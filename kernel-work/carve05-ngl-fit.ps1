# carve05-ngl-fit.ps1 - can a reduced GPU split serve this model at a 0.5 GB carve?
#
# The device request shrinks with -ngl (8 -> 115 GiB, 16 -> 92.7, 32 -> 42.8), and the
# 0.5 GB carve pool is 55.94 GiB. So -ngl ~32 might both load and serve, with the
# remaining layers computed on the CPU out of host RAM (the "use the regular RAM"
# route). This tests it, with strict per-arm cleanup so a hung arm cannot poison
# the next one (an orphaned server holding 57 GB confounded an earlier run).
param(
    [int[]]$NglList = @(32, 36),
    [int]$Port = 8500,
    [int]$PerArmTimeoutSec = 420
)
$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin\llama-server.exe'
$sdk   = 'C:\AI\sdk\therock1151'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$res   = 'C:\Projects\strix-alloy\kernel-work\results'

$env:PATH = "$sdk\bin;$sdk\lib\llvm\bin;$env:PATH"
$env:ROCM_PATH = $sdk; $env:HIP_PATH = $sdk
$env:HIP_DEVICE_LIB_PATH = "$sdk\lib\llvm\amdgcn\bitcode"
$env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

function Kill-All {
    Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object {
        & taskkill /F /PID $_.Id 2>&1 | Out-Null
    }
    Start-Sleep -Seconds 4
}

$summary = @()
foreach ($ngl in $NglList) {
    Write-Output "=================== -ngl $ngl ==================="
    Kill-All
    $freeGb = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB, 1)
    Write-Output "  host free before = $freeGb GB"

    $out = Join-Path $res "fit-ngl$ngl.out"
    $err = Join-Path $res "fit-ngl$ngl.err"
    Remove-Item $out, $err -ErrorAction SilentlyContinue

    $a = @('-m', $model, '-dev', 'ROCm0', '-ngl', "$ngl",
           '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
           '-ctk', 'f16', '-ctv', 'f16', '-c', '8192', '-b', '1024', '-ub', '1024',
           '--parallel', '1', '--host', '127.0.0.1', '--port', "$Port", '--no-webui', '--seed', '1234')
    $p = Start-Process -FilePath $bin -ArgumentList $a -PassThru -NoNewWindow `
                       -RedirectStandardOutput $out -RedirectStandardError $err

    $ready = $false
    $deadline = (Get-Date).AddSeconds($PerArmTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($p.HasExited) { break }
        if (Select-String -Path $err -Pattern 'listening on' -ErrorAction SilentlyContinue) { $ready = $true; break }
        Start-Sleep -Seconds 3
    }

    # report what it asked the device for, regardless of outcome
    $req = Select-String -Path $err -Pattern 'allocating ([0-9]+\.[0-9]+) MiB' -ErrorAction SilentlyContinue |
           Select-Object -First 1
    $off = Select-String -Path $err -Pattern 'offloaded|CPU buffer|Host buffer' -ErrorAction SilentlyContinue |
           Select-Object -First 2
    Write-Output ("  device request : " + $(if ($req) { $req.Matches[0].Groups[1].Value + ' MiB' } else { '(none / no failure)' }))
    if ($off) { $off | ForEach-Object { Write-Output ('  ' + $_.Line.Trim()) } }

    if ($ready) {
        Write-Output "  LOADED - benchmarking"
        try {
            $body = @{ prompt = 'Explain how a modern MoE transformer with gated linear attention processes a single decode step end to end, covering embedding lookup, the layer norm and projection GEMVs, top-k expert routing, the shared expert, the linear-attention recurrence, the KV read for full-attention layers, and the final norm and output projection.'; n_predict = 96; cache_prompt = $false; temperature = 0.0; top_k = 1; top_p = 1.0; min_p = 0.0; stream = $false } | ConvertTo-Json
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/completion" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 900
            $t = $r.timings
            Write-Output ("  PREFILL {0:N1} t/s   DECODE {1:N2} t/s" -f $t.prompt_per_second, $t.predicted_per_second)
            $summary += [pscustomobject]@{ ngl = $ngl; loaded = $true; prefill = [math]::Round($t.prompt_per_second,1); decode = [math]::Round($t.predicted_per_second,2) }
        } catch {
            Write-Output "  request failed: $_"
            $summary += [pscustomobject]@{ ngl = $ngl; loaded = $true; prefill = $null; decode = $null }
        }
    } else {
        $state = if ($p.HasExited) { 'EXITED' } else { 'HUNG (timeout)' }
        Write-Output "  DID NOT SERVE: $state"
        Select-String -Path $err -Pattern 'failed to allocate|out of memory|error' -ErrorAction SilentlyContinue |
            Select-Object -First 3 | ForEach-Object { Write-Output ('    ' + $_.Line.Trim()) }
        $summary += [pscustomobject]@{ ngl = $ngl; loaded = $false; prefill = $null; decode = $null }
    }
    if (-not $p.HasExited) { & taskkill /F /PID $p.Id 2>&1 | Out-Null }
    Start-Sleep -Seconds 3
}
Kill-All
Write-Output ''
Write-Output '=== 0.5 GB carve, reduced GPU split ==='
$summary | Format-Table -AutoSize | Out-String | Write-Output
$summary | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $res 'carve05-ngl-fit.json')
