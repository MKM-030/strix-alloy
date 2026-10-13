[CmdletBinding()]
param(
    [ValidateSet('Start','Stop','Status')]
    [string]$Action = 'Start',
    [string]$ProfileConfig = 'C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\halogen0181-version-bracket-20261012\serving0181-full262-profile.json',
    [string]$Python = 'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe',
    [switch]$DemoNoThinking
)
# This sidecar only listens on 8841 and reuses the existing engine. It never
# controls the backend, the live gateway on 8840, or Tailscale/Funnel.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Port = 8841
$RepoRoot = Split-Path -Parent $PSScriptRoot
$GatewayPath = Join-Path $RepoRoot 'server\gateway.py'
$LocalDirectory = Join-Path $RepoRoot 'server\.local'
$ConfigPath = Join-Path $LocalDirectory 'scc-gateway.json'
$StatePath = Join-Path $LocalDirectory 'scc-gateway-state.json'
$LogPath = Join-Path $LocalDirectory 'scc-gateway.log'
$StdoutPath = Join-Path $LocalDirectory 'scc-gateway.stdout.log'
$StderrPath = Join-Path $LocalDirectory 'scc-gateway.stderr.log'

function Get-OwnedGateway {
    if (-not (Test-Path -LiteralPath $StatePath)) { return $null }
    $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    if ($state.port -ne $Port -or $state.gateway -ne $GatewayPath -or $state.config -ne $ConfigPath) {
        throw 'Sidecar state does not match this worktree and port; refusing process control.'
    }
    $owned = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if ($null -eq $owned) { return $null }
    $details = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $owned.Id)
    if ($owned.StartTime.ToUniversalTime().Ticks.ToString() -ne $state.started_ticks -or
        $details.ExecutablePath -ne $state.python -or
        -not $details.CommandLine.Contains($GatewayPath) -or
        -not $details.CommandLine.Contains($ConfigPath) -or
        $details.CommandLine -notmatch '--port\s+8841(?:\s|$)') {
        throw 'Saved PID no longer identifies the owned 8841 sidecar; refusing process control.'
    }
    return $owned
}

function Get-ServingGateway($Launcher) {
    # Windows venv python.exe may wrap a child python.exe that owns the socket.
    # Only adopt a direct child with this exact gateway/config/port command.
    $workers = @(Get-CimInstance Win32_Process -Filter ("ParentProcessId = {0}" -f $Launcher.Id) |
        Where-Object { $_.Name -eq 'python.exe' -and
            $_.CommandLine.Contains($GatewayPath) -and $_.CommandLine.Contains($ConfigPath) -and
            $_.CommandLine -match '--port\s+8841(?:\s|$)' })
    if ($workers.Count -gt 1) { throw 'Ambiguous sidecar child processes; refusing process control.' }
    if ($workers.Count -eq 1) { return Get-Process -Id $workers[0].ProcessId }
    return $Launcher
}

$owned = Get-OwnedGateway
$serving = $(if ($null -ne $owned) { Get-ServingGateway $owned } else { $null })
if ($Action -eq 'Status') {
    [pscustomobject]@{ running=($null -ne $owned); pid=$(if ($serving) { $serving.Id } else { $null }); launcher_pid=$(if ($owned) { $owned.Id } else { $null }); port=$Port }
    return
}
if ($Action -eq 'Stop') {
    if ($null -ne $owned) {
        if ($serving.Id -ne $owned.Id) { Stop-Process -InputObject $serving -Force }
        $owned.Refresh()
        if (-not $owned.HasExited) { Stop-Process -InputObject $owned -Force }
    }
    if (Test-Path -LiteralPath $StatePath) { Remove-Item -LiteralPath $StatePath }
    [pscustomobject]@{ running=$false; port=$Port }
    return
}
if ($null -ne $owned) {
    $runningConfig = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    $runningDemoAlias = $(if ($runningConfig.PSObject.Properties.Name -contains 'demo_no_thinking_model') { [string]$runningConfig.demo_no_thinking_model } else { '' })
    $requestedDemoAlias = $(if ($DemoNoThinking) { 'halogen-v2' } else { '' })
    if ($runningDemoAlias -ne $requestedDemoAlias) {
        throw 'Requested demo mode differs from running gateway; wait for idle, stop the owned sidecar, then start with the desired mode.'
    }
    [pscustomobject]@{ running=$true; pid=$serving.Id; launcher_pid=$owned.Id; port=$Port; config=$ConfigPath }
    return
}
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) { throw 'Port 8841 is occupied by a process not owned by this sidecar.' }
$Python = (Resolve-Path -LiteralPath $Python).Path
$ProfileConfig = (Resolve-Path -LiteralPath $ProfileConfig).Path
$config = Get-Content -LiteralPath $ProfileConfig -Raw | ConvertFrom-Json
if ($config.backend.upstream -ne 'http://127.0.0.1:8731') {
    throw 'This sidecar is restricted to the existing loopback backend on 8731.'
}
foreach ($field in @('token_file','backend_token_file')) {
    if ($config.PSObject.Properties.Name -contains $field -and $config.$field) {
        $tokenPath = [string]$config.$field
        if (-not [IO.Path]::IsPathRooted($tokenPath)) {
            $tokenPath = Join-Path (Split-Path -Parent $ProfileConfig) $tokenPath
        }
        $config.$field = (Resolve-Path -LiteralPath $tokenPath).Path
    }
}
if ($DemoNoThinking -and $config.backend.identifier -ne 'halogen-v2') {
    throw 'Demo no-thinking mode is restricted to the reviewed ServiceNow public alias halogen-v2.'
}
$demoAlias = $(if ($DemoNoThinking) { 'halogen-v2' } else { '' })
$config | Add-Member -NotePropertyName demo_no_thinking_model -NotePropertyValue $demoAlias -Force
$config | Add-Member -NotePropertyName queue_limit -NotePropertyValue 8 -Force
$config | Add-Member -NotePropertyName queue_seconds -NotePropertyValue 120 -Force
$config | Add-Member -NotePropertyName console_trace -NotePropertyValue $false -Force
New-Item -ItemType Directory -Path $LocalDirectory -Force | Out-Null
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
$arguments = @('-u', ('"{0}"' -f $GatewayPath), '--config', ('"{0}"' -f $ConfigPath),
               '--port', "$Port", '--log', ('"{0}"' -f $LogPath))
$child = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $RepoRoot -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -WindowStyle Hidden -PassThru
[pscustomobject]@{
    pid=$child.Id; started_ticks=$child.StartTime.ToUniversalTime().Ticks.ToString()
    port=$Port; python=$Python; gateway=$GatewayPath; config=$ConfigPath
} | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
for ($attempt=0; $attempt -lt 30; $attempt++) {
    $child.Refresh()
    if ($child.HasExited) { throw "Sidecar exited; inspect $StderrPath" }
    $worker = Get-ServingGateway $child
    $listener = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
                  Where-Object { $_.OwningProcess -eq $worker.Id -and $_.LocalAddress -eq '127.0.0.1' })
    if ($listener.Count -gt 0) {
        [pscustomobject]@{ running=$true; pid=$worker.Id; launcher_pid=$child.Id; port=$Port; config=$ConfigPath; log=$LogPath }
        return
    }
    Start-Sleep -Milliseconds 100
}
throw 'Sidecar did not become ready; use -Action Status or -Action Stop to inspect or stop the owned process.'
