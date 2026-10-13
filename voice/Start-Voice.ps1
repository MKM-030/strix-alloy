param(
  [ValidateSet('Start','Stop','Status')][string]$Action = 'Status',
  [string]$Config = 'E:\SCC-Voice\bridge.json',
  [string]$VoiceProfile = 'E:\SCC-Voice\voices\scc-demo'
)
$ErrorActionPreference = 'Stop'
$voiceRoot = $PSScriptRoot
$logRoot = 'E:\SCC-Voice\logs'
$tokenFile = 'C:\Projects\strix-alloy-clean\server\.local\servicenow-api-token.txt'
$services = @(
  @{ Name='asr'; Port=8851; Exe='E:\SCC-Voice\asr-env\Scripts\python.exe'; Script=(Join-Path $voiceRoot 'audio_service.py'); Args=@('--mode','asr','--port','8851','--threads','6','--token-file',$tokenFile,'--cache-dir','E:\SCC-Voice\models') },
  @{ Name='tts'; Port=8852; Exe='E:\SCC-Voice\tts-env\Scripts\python.exe'; Script=(Join-Path $voiceRoot 'audio_service.py'); Args=@('--mode','tts','--port','8852','--threads','6','--dtype','bfloat16','--token-file',$tokenFile,'--cache-dir','E:\SCC-Voice\models') },
  @{ Name='bridge'; Port=8850; Exe='C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe'; Script=(Join-Path $voiceRoot 'bridge.py'); Args=@('--config',$Config) }
)
if ($VoiceProfile) {
  $services[1].Args += @('--voice-profile', $VoiceProfile)
}
function Get-OwnedProcesses($service) {
  $scriptMatch = '(?:^|\s)"?' + [regex]::Escape($service.Script) + '"?(?=\s|$)'
  @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match $scriptMatch -and ($service.Name -eq 'bridge' -or $_.CommandLine -match ('(?:^|\s)"?--mode"?\s+"?' + $service.Name + '"?(?=\s|$)'))
  })
}
if ($Action -eq 'Start') { & (Join-Path $voiceRoot 'Start-QueuedGateway.ps1') -Action Start }
foreach ($service in $services) {
  $owned = @(Get-OwnedProcesses $service)
  if ($Action -eq 'Stop') {
    foreach ($process in $owned) {
      Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
    }
    Write-Host ($service.Name + ': stopped owned worker processes only')
    continue
  }
  $listener = @(Get-NetTCPConnection -State Listen -LocalPort $service.Port -ErrorAction SilentlyContinue)
  if ($Action -eq 'Start' -and !$owned.Count -and !$listener.Count) {
    if (!(Test-Path $service.Exe) -or !(Test-Path $service.Script)) { Write-Warning ($service.Name + ': installation incomplete'); continue }
    if ($service.Name -eq 'bridge' -and !(Test-Path $Config)) { Write-Warning 'bridge: configuration missing; run Configure-Voice.ps1 first'; continue }
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $arguments = @('-u',('"' + $service.Script + '"')) + @($service.Args | ForEach-Object { '"' + $_ + '"' })
    $started = Start-Process -FilePath $service.Exe -ArgumentList $arguments -WorkingDirectory (Split-Path $voiceRoot) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot ($service.Name + '.stdout.log')) -RedirectStandardError (Join-Path $logRoot ($service.Name + '.stderr.log'))
    Write-Host ($service.Name + ': started PID ' + $started.Id + '; model loading can take time')
  } elseif ($listener.Count) {
    $ownedIds = @($owned | ForEach-Object { $_.ProcessId })
    $foreign = @($listener | Where-Object { $_.OwningProcess -notin $ownedIds })
    if ($foreign.Count) { Write-Warning ($service.Name + ': port occupied by another process; left unchanged') }
    else { Write-Host ($service.Name + ': listening on 127.0.0.1:' + $service.Port) }
  } elseif ($owned.Count) { Write-Host ($service.Name + ': process running, not yet listening (loading or startup error; see logs)') }
  else { Write-Host ($service.Name + ': stopped') }
}
Write-Host 'HaloGen and its gateway are managed separately and were not changed.'
