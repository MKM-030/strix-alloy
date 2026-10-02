$ErrorActionPreference = 'Continue'
$bin   = 'C:\AI\build\strix-llama-win\build-therock\bin'
$run   = 'C:\Projects\strix-alloy-clean\artifacts\benchmarks\runs\repro-20260921'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$env:PATH = "$bin;C:\AI\sdk\therock1151\bin;$env:PATH"
Set-Location $bin

function Invoke-Bench([string]$name, [string]$tail) {
    $json = Join-Path $run "$name.json"
    $log  = Join-Path $run "$name.stderr.log"
    Write-Output "=== [$name] start $(Get-Date -Format 'HH:mm:ss')  llama-bench $tail"
    cmd /c "llama-bench.exe -m `"$model`" $tail > `"$json`" 2> `"$log`""
    Write-Output "=== [$name] exit=$LASTEXITCODE end $(Get-Date -Format 'HH:mm:ss')"
    Get-Content $json | Where-Object { $_ -and $_ -notmatch '^\s*$' }
}

Invoke-Bench 'A-canonical-defaults' '-dev ROCm0 -ngl 99 -fa on -lm none -p 512 -n 128 -r 5 -o json'
Invoke-Bench 'B-long-prompt-16k'    '-dev ROCm0 -ngl 99 -fa on -lm none -p 16384 -n 128 -b 16384 -ub 16384 -r 3 -o json'
Invoke-Bench 'C-reference-protocol' '-dev ROCm0 -ngl 99 -fa on -lm none -lzm on-direct -ctk f16 -ctv f16 -p 16384 -n 128 -b 16384 -ub 16384 -d 0,40000 -r 3 -o json'
Write-Output '=== ALL BENCH DONE ==='
