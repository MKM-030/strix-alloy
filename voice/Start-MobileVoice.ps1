param(
  [ValidateSet('Start','Restart','Stop','Status')][string]$Action = 'Status',
  [string]$Config = 'E:\SCC-Voice\bridge.json'
)
$ErrorActionPreference = 'Stop'
$voiceRoot = $PSScriptRoot
$logRoot = 'E:\SCC-Voice\logs'
$python = 'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe'
$services = @(
  @{ Name='bridge'; Ports=@(8850,8853); Script=(Join-Path $voiceRoot 'bridge.py'); Args=@('--config',$Config) },
  @{ Name='mobile-gateway'; Ports=@(8854); Script=(Join-Path $voiceRoot 'mobile_gateway.py'); Args=@('--password-file','E:\SCC-Voice\secrets\callback-password.txt','--public-origin','https://strix-alloy.tail7f425a.ts.net','--base-path','/scc-demo','--backend-origin','http://127.0.0.1:8850','--port','8854') }
)
function Get-OwnedProcesses($service) {
  $scriptMatch = '(?:^|\s)"?' + [regex]::Escape($service.Script) + '"?(?=\s|$)'
  @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -match $scriptMatch })
}
# Preflight every listener before any process is stopped. Never stop ASR/TTS,
# HaloGen, or a foreign process, even if it happens to hold one of these ports.
foreach ($service in $services) {
  if (!(Test-Path $service.Script)) { throw ('Missing script: ' + $service.Script) }
  $ownedIds = @(Get-OwnedProcesses $service | ForEach-Object { $_.ProcessId })
  $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $service.Ports -ErrorAction SilentlyContinue)
  if (@($listeners | Where-Object { $_.OwningProcess -notin $ownedIds }).Count) {
    throw ($service.Name + ': port occupied by another process; no processes changed')
  }
}
if ($Action -in @('Start','Restart')) {
  if (!(Test-Path $python) -or !(Test-Path $Config) -or !(Test-Path 'E:\SCC-Voice\secrets\callback-password.txt')) {
    throw 'Python, bridge configuration, or protected password file missing'
  }
}
if ($Action -in @('Stop','Restart')) {
  # Both processes share one backend session. Always restart them together.
  foreach ($service in @($services[1], $services[0])) {
    foreach ($process in @(Get-OwnedProcesses $service)) {
      Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
    }
  }
  Start-Sleep -Milliseconds 500
}
foreach ($service in $services) {
  $owned = @(Get-OwnedProcesses $service)
  if ($Action -in @('Start','Restart') -and !$owned.Count) {
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    foreach ($suffix in @('stdout','stderr')) {
      $oldLog = Join-Path $logRoot ($service.Name + '.' + $suffix + '.log')
      if (Test-Path $oldLog) { Copy-Item -LiteralPath $oldLog -Destination ($oldLog + '.' + $stamp) }
    }
    $arguments = @('-u',('"' + $service.Script + '"')) + @($service.Args | ForEach-Object { '"' + $_ + '"' })
    $started = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory (Split-Path $voiceRoot) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot ($service.Name + '.stdout.log')) -RedirectStandardError (Join-Path $logRoot ($service.Name + '.stderr.log'))
    Write-Host ($service.Name + ': started PID ' + $started.Id)
  } elseif ($owned.Count) {
    Write-Host ($service.Name + ': running; owned PIDs ' + (($owned | ForEach-Object { $_.ProcessId }) -join ','))
  } else {
    Write-Host ($service.Name + ': stopped')
  }
}
Write-Host 'ASR, TTS, HaloGen, credentials, and Funnel routes were not changed.'
