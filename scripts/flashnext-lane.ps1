[CmdletBinding()]
param(
  [ValidateSet('start', 'stop', 'status', 'benchmark')]
  [string]$Action = 'status',
  [ValidateSet('target-only', 'target-only-fit', 'mtp-2', 'mtp-4')]
  [string]$Profile = 'target-only',
  [ValidateSet(32768, 65536, 131072, 262144)]
  [int]$ContextSize = 32768,
  [ValidateSet('q8_0','q4_0')]
  [string]$CacheType='q8_0'
)

$ErrorActionPreference = 'Stop'

$Alias = 'qwen3.8-flash-next'
$HostAddress = '127.0.0.1'
$Port = 8826
$Executable = 'C:\AI\build\laurent-llamacpp-qwen4exp-rocmfpx\build-vulkan\bin\Release\llama-server.exe'
$Target = 'C:\AI\models\rocmfp4\Qwen3.8-Flash-Next-ROCmFP4-FAST-v2-ple16.gguf'
$Sidecar = 'C:\AI\models\rocmfp4-mtp\Qwen3.8-Flash-Next-MTP-ROCmFP4-FAST.gguf'
$RuntimeRoot = 'C:\AI\local-ai\flashnext'
$StatePath = Join-Path $RuntimeRoot 'state.json'
$StdOutPath = Join-Path $RuntimeRoot 'logs\server.stdout.log'
$StdErrPath = Join-Path $RuntimeRoot 'logs\server.stderr.log'

function Ensure-Asset([string]$Path, [long]$ExpectedBytes) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "BLOCKED_MISSING_MODEL_ASSETS: lokale Datei fehlt: $Path (kein Download wird ausgeführt)."
  }
  $actual = (Get-Item -LiteralPath $Path).Length
  if ($actual -ne $ExpectedBytes) {
    throw "BLOCKED_MISSING_MODEL_ASSETS: Dateigröße abweichend: $Path erwartet $ExpectedBytes Bytes, gefunden $actual Bytes."
  }
}

function Read-State {
  if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return $null }
  try { return Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json }
  catch { throw "Ungültiger Flash-Next-Zustand: $StatePath" }
}

function Get-ProcessCommandLine([int]$ProcessId) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
  if ($null -eq $process) { return $null }
  return [string]$process.CommandLine
}

function Get-OwnedProcess {
  $state = Read-State
  if ($null -eq $state -or $null -eq $state.pid) { return $null }
  $process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
  if ($null -eq $process) { return $null }
  $commandLine = Get-ProcessCommandLine ([int]$state.pid)
  if ([string]::IsNullOrWhiteSpace($commandLine)) { return $null }
  if (-not $commandLine.Contains($Executable) -or
      -not $commandLine.Contains($Target) -or
      -not $commandLine.Contains("--alias $Alias") -or
      -not $commandLine.Contains("--port $Port")) { return $null }
  return [pscustomobject]@{ Process = $process; State = $state; CommandLine = $commandLine }
}

function Get-PortOwner {
  $connections = @(Get-NetTCPConnection -State Listen -LocalAddress $HostAddress -LocalPort $Port -ErrorAction SilentlyContinue)
  foreach ($connection in $connections) {
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    [pscustomobject]@{ Connection = $connection; Process = $process; CommandLine = (Get-ProcessCommandLine $connection.OwningProcess) }
  }
}

function Ensure-Directories {
  New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot 'logs') | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot 'benchmarks') | Out-Null
}

function Get-Arguments([string]$SelectedProfile, [int]$SelectedContextSize) {
  $args = @(
    '-m', $Target,
    '--alias', $Alias,
    '--host', $HostAddress,
    '--port', [string]$Port,
    '--device', 'Vulkan0',
    '--ctx-size', [string]$SelectedContextSize,
    '--parallel', '1',
    '--flash-attn', 'on',
    '--cache-type-k', $CacheType,
    '--cache-type-v', $CacheType,
    '--batch-size', '512',
    '--ubatch-size', '512',
    '--threads', '16',
    '--threads-batch', '32',
    '--fit', $(if ($SelectedProfile -eq 'target-only-fit') { 'on' } else { 'off' }),
    '--ngram-on-disk',
    '--ngram-cache', '4096',
    '--jinja',
    '--reasoning-effort', 'medium',
    '--reasoning-budget', '2048',
    '--metrics',
    '--no-webui'
  )
  if ($SelectedProfile -ne 'target-only-fit') {
    $args = @($args[0..5] + @('--gpu-layers', 'all') + $args[6..($args.Count - 1)])
  }
  if ($SelectedProfile -eq 'mtp-2' -or $SelectedProfile -eq 'mtp-4') {
    $draftLength = if ($SelectedProfile -eq 'mtp-2') { '2' } else { '4' }
    $args += @(
      '--spec-type', 'draft-mtp',
      '--spec-draft-model', $Sidecar,
      '--spec-draft-ngl', 'all',
'--spec-draft-type-k', $CacheType,
'--spec-draft-type-v', $CacheType,
      '--spec-draft-n-max', $draftLength
    )
  }
  return $args
}

function Start-FlashNext([string]$SelectedProfile) {
  Ensure-Directories
  Ensure-Asset $Executable 10752
  Ensure-Asset $Target 93484237760
  if ($SelectedProfile -eq 'mtp-2' -or $SelectedProfile -eq 'mtp-4') { Ensure-Asset $Sidecar 2444519296 }

  $owned = Get-OwnedProcess
  if ($null -ne $owned) {
    $recordedCacheType = if ([string]::IsNullOrWhiteSpace([string]$owned.State.cacheType)) { 'q8_0' } else { [string]$owned.State.cacheType }
    if ([string]$owned.State.profile -eq $SelectedProfile -and [int]$owned.State.contextSize -eq $ContextSize -and $recordedCacheType -eq $CacheType) {
      Write-Output "Flash-Next läuft bereits: PID $($owned.Process.Id), Profil $SelectedProfile, http://$HostAddress`:$Port/v1"
      return
    }
    Stop-FlashNext
  }

  $foreign = @(Get-PortOwner)
  if ($foreign.Count -gt 0) {
    $details = ($foreign | ForEach-Object { "PID $($_.Connection.OwningProcess): $($_.CommandLine)" }) -join '; '
    throw "Port $Port ist bereits durch einen fremden Prozess belegt; nichts wird beendet. $details"
  }

  $arguments = Get-Arguments $SelectedProfile $ContextSize
  $process = Start-Process -FilePath $Executable -ArgumentList $arguments -WorkingDirectory (Split-Path $Executable) -WindowStyle Hidden -RedirectStandardOutput $StdOutPath -RedirectStandardError $StdErrPath -PassThru
  $state = [ordered]@{
    pid = $process.Id
    profile = $SelectedProfile
    contextSize = $ContextSize
    cacheType = $CacheType
    alias = $Alias
    endpoint = "http://$HostAddress`:$Port/v1"
    executable = $Executable
    target = $Target
    sidecar = if ($SelectedProfile -eq 'mtp-2' -or $SelectedProfile -eq 'mtp-4') { $Sidecar } else { $null }
    arguments = $arguments
    startedAt = (Get-Date).ToUniversalTime().ToString('o')
    ownership = 'flashnext-lane.ps1 only'
  }
  $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $StatePath -Encoding utf8

  $ready = $false
  for ($attempt = 0; $attempt -lt 180; $attempt++) {
    Start-Sleep -Seconds 2
    if ($process.HasExited) { break }
    try {
      $health = Invoke-RestMethod -Uri "http://$HostAddress`:$Port/health" -TimeoutSec 3
      if ($health.status -eq 'ok') { $ready = $true; break }
    } catch { }
  }
  if (-not $ready) {
    $tail = if (Test-Path -LiteralPath $StdErrPath) { Get-Content -LiteralPath $StdErrPath -Tail 40 -ErrorAction SilentlyContinue } else { @() }
    throw "Flash-Next wurde nicht innerhalb des Startfensters gesund. PID $($process.Id). Letzte stderr-Zeilen:`n$($tail -join "`n")"
  }
  Write-Output "Flash-Next gestartet: PID $($process.Id), Profil $SelectedProfile, http://$HostAddress`:$Port/v1"
}

function Stop-FlashNext {
  $owned = Get-OwnedProcess
  if ($null -eq $owned) {
    $state = Read-State
    if ($null -ne $state) { Remove-Item -LiteralPath $StatePath -Force }
    Write-Output 'Kein eigener Flash-Next-Prozess aktiv.'
    return
  }
  Stop-Process -Id $owned.Process.Id
  try { Wait-Process -Id $owned.Process.Id -Timeout 30 -ErrorAction Stop } catch {
    if (Get-Process -Id $owned.Process.Id -ErrorAction SilentlyContinue) {
      Stop-Process -Id $owned.Process.Id -Force
    }
  }
  for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if (@(Get-PortOwner).Count -eq 0) { break }
    Start-Sleep -Seconds 1
  }
  Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
  Write-Output "Eigener Flash-Next-Prozess PID $($owned.Process.Id) beendet."
}

function Show-FlashNextStatus {
  $owned = Get-OwnedProcess
  $portOwners = @(Get-PortOwner)
  if ($null -eq $owned) {
    Write-Output 'Flash-Next: nicht aktiv.'
    if ($portOwners.Count -gt 0) { $portOwners | ForEach-Object { Write-Output "Port $Port fremd belegt durch PID $($_.Connection.OwningProcess)." } }
    return
  }
  $props = $null
  $metrics = $null
  try { $props = Invoke-RestMethod -Uri "http://$HostAddress`:$Port/props" -TimeoutSec 5 } catch { }
  try { $metrics = Invoke-WebRequest -Uri "http://$HostAddress`:$Port/metrics" -TimeoutSec 5 -UseBasicParsing } catch { }
  [pscustomobject]@{
    status = 'active'
    pid = $owned.Process.Id
    profile = $owned.State.profile
    contextSize = $owned.State.contextSize
    endpoint = "http://$HostAddress`:$Port/v1"
    alias = $Alias
    health = 'ok'
    modelPath = $props.model_path
    modelFtype = $props.model_ftype
    metrics = if ($null -eq $metrics) { 'unavailable' } else { 'enabled' }
  } | ConvertTo-Json -Depth 5
}

function Invoke-FlashNextBenchmark {
  Ensure-Directories
  if ($null -eq (Get-OwnedProcess)) { Start-FlashNext 'target-only' }
  $benchmark = Join-Path $PSScriptRoot 'flashnext-benchmark.mjs'
  if (-not (Test-Path -LiteralPath $benchmark -PathType Leaf)) { throw "Benchmark-Datei fehlt: $benchmark" }
  & node $benchmark '--endpoint' "http://$HostAddress`:$Port/v1" '--model' $Alias '--output-dir' (Join-Path $RuntimeRoot 'benchmarks') '--long-prompts'
  if ($LASTEXITCODE -ne 0) { throw "Flash-Next-Benchmark beendet mit Exitcode $LASTEXITCODE." }
}

switch ($Action) {
  'start' { Start-FlashNext $Profile }
  'stop' { Stop-FlashNext }
  'status' { Show-FlashNextStatus }
  'benchmark' { Invoke-FlashNextBenchmark }
}
