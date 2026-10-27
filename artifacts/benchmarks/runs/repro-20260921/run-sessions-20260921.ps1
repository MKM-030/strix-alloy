$ErrorActionPreference = 'Continue'
$run   = 'C:\Projects\strix-alloy-clean\artifacts\benchmarks\runs\repro-20260921'
$rt    = 'C:\Users\Marcel\AppData\Local\Programs\strix-alloy\current\runtime'
$model = 'C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf'
$draft = 'C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$tpl    = 'C:\Projects\strix-alloy-clean\app\flash-next-clients.jinja'
$port  = 8826

function Log([string]$m) { Write-Output "[$(Get-Date -Format 'HH:mm:ss')] $m" }

function Stop-Server {
    Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 8
}

function Start-Server([string]$name, [int]$np, [int]$ctx) {
    $log = Join-Path $run "server-$name.log"
    $a = @('-m',$model,'--alias','Qwen3.8-Flash-Next','-dev','ROCm0','-ngl','99','-fa','on','-fit','off',
          '--load-mode','none','-ctk','f16','-ctv','f16','-c',"$ctx",'-b','8192','-ub','8192','--parallel',"$np",
          '--slots','--host','127.0.0.1','--port',"$port",'--seed','1234','--jinja','--chat-template-file',$tpl,
          '-md',$draft,'--spec-type','draft-mtp','--spec-draft-device','ROCm0','--spec-draft-ngl','99','--spec-draft-n-max','2')
    $p = Start-Process -FilePath "$rt\llama-server.exe" -ArgumentList $a -WindowStyle Hidden -PassThru `
         -RedirectStandardError $log -RedirectStandardOutput "$run\server-$name.out"
    $deadline = (Get-Date).AddSeconds(900)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        if ($p.HasExited) { Log "  server $name EXITED early (code $($p.ExitCode))"; return $null }
        try { $h = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 5; if ($h.status -eq 'ok') { Log "  server $name ready (pid $($p.Id))"; return $p } } catch {}
    }
    Log "  server $name HEALTH TIMEOUT"; return $null
}

function Get-DedicatedGB {
    $c = Get-Counter -Counter '\GPU Adapter Memory(*)\Dedicated Usage' -SampleInterval 1 -MaxSamples 1 -ErrorAction SilentlyContinue
    $v = ($c.CounterSamples | Measure-Object -Maximum).Maximum
    return [math]::Round($v/1GB, 2)
}

function Invoke-Concurrent([int]$n, [int]$ntok) {
    $jobs = @()
    for ($i=1; $i -le $n; $i++) {
        $jobs += Start-Job -ScriptBlock {
            param($i,$port,$ntok)
            $body = @{ prompt = "Repeat the digits in order starting from 0, ten per line, and keep going as far as you can."; temperature = 0; max_tokens = $ntok; seed = 1234; timing_per_token = $true } | ConvertTo-Json
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            try {
                $r = Invoke-RestMethod -Uri "http://127.0.0.1:$port/completion" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 900
                $sw.Stop()
                $tok = if ($r.tokens_evaluated) { $r.tokens_evaluated } else { 0 }
                $eng = if ($r.timings) { [math]::Round($r.timings.predicted_per_token*1000,1) } else { $null }
                "$i|$($tok)|$([math]::Round($sw.Elapsed.TotalSeconds,2))|$eng"
            } catch { $sw.Stop(); "$i|ERR|$([math]::Round($sw.Elapsed.TotalSeconds,2))|$($_.Exception.Message.Substring(0,[Math]::Min(60,$_.Exception.Message.Length)))" }
        } -ArgumentList $i,$port,$ntok
    }
    $null = Wait-Job -Job $jobs -Timeout 900
    $res = $jobs | Receive-Job
    $jobs | Remove-Job -Force
    return $res
}

# ---------- D: depth ladder on the shipped configuration ----------
$env:PATH = "C:\AI\build\strix-llama-win\build-therock\bin;C:\AI\sdk\therock1151\bin;$env:PATH"
Stop-Server
Log "D-depth-ladder start"
cmd /c "C:\AI\build\strix-llama-win\build-therock\bin\llama-bench.exe -m `"$model`" -dev ROCm0 -ngl 99 -fa on -lm none -p 16384 -n 128 -b 16384 -ub 16384 -d 0,40000 -r 3 -o json > `"$run\D-depth-ladder.json`" 2> `"$run\D-depth-ladder.stderr.log`""
Log "D-depth-ladder exit=$LASTEXITCODE"

# ---------- Session capacity ----------
$configs = @(
    @{name='np1-c262144';  np=1;  ctx=262144},
    @{name='np2-c262144';  np=2;  ctx=262144},
    @{name='np4-c262144';  np=4;  ctx=262144},
    @{name='np8-c262144';  np=8;  ctx=262144},
    @{name='np16-c262144'; np=16; ctx=262144}
)
foreach ($cfg in $configs) {
    Log "=== $($cfg.name) ==="
    Stop-Server
    $p = Start-Server $cfg.name $cfg.np $cfg.ctx
    if (-not $p) { Log "  SKIPPED (no server)"; continue }
    Start-Sleep -Seconds 5
    $alloc = Get-DedicatedGB
    $res = Invoke-Concurrent $cfg.np 128
    $peak = Get-DedicatedGB
    foreach ($r in $res) { Log "  slot-out: $r" }
    $toks = ($res | ForEach-Object { [int]($_.Split('|')[1]) } | Measure-Object -Sum).Sum
    $walls = ($res | ForEach-Object { [double]($_.Split('|')[3]) } | Measure-Object -Maximum).Maximum
    Log "  aggregate: $toks tokens / $walls s = $([math]::Round($toks/$walls,2)) tok/s total, $([math]::Round($toks/$walls/$cfg.np,2)) tok/s per session"
    Log "  gpu dedicated: idle=$alloc GB after-load, $peak GB after concurrent run"
    Stop-Server
}
Log '=== SESSION TESTS DONE ==='
