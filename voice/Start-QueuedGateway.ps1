[CmdletBinding()]
param(
    [ValidateSet('Start','Stop','Status')]
    [string]$Action = 'Start',
    [string]$ProfileConfig = '',
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
$DeploymentScript = Join-Path $PSScriptRoot 'native-start\model_deployment.py'
$DeploymentScriptHash = 'b43e8f65e9c48a441063d98259bda12c3d3755ff3b4ec01d09e633601ff3aa7e'

function Read-ReviewedModelDeployment($Python, $DeploymentScript, $ExpectedHash) {
    if (-not (Test-Path -LiteralPath $DeploymentScript -PathType Leaf) -or
        (Get-FileHash -LiteralPath $DeploymentScript -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) {
        throw 'Reviewed model deployment loader changed; refusing startup.'
    }
    $text = & $Python -B $DeploymentScript
    if ($LASTEXITCODE -ne 0) { throw 'Reviewed model deployment/profile validation failed.' }
    return ($text -join [Environment]::NewLine) | ConvertFrom-Json
}

function Test-ExactDeploymentValue($Actual, $Expected) {
    if ($null -eq $Actual -or $null -eq $Expected) { return $null -eq $Actual -and $null -eq $Expected }
    if ($Actual.GetType() -ne $Expected.GetType()) { return $false }
    if ($Expected -is [pscustomobject]) {
        $names = @($Expected.PSObject.Properties.Name)
        if (@($Actual.PSObject.Properties.Name).Count -ne $names.Count) { return $false }
        foreach ($name in $names) {
            if ($name -cnotin @($Actual.PSObject.Properties.Name) -or
                -not (Test-ExactDeploymentValue $Actual.$name $Expected.$name)) { return $false }
        }
        return $true
    }
    if ($Expected -is [array]) {
        if ($Actual.Count -ne $Expected.Count) { return $false }
        for ($index=0; $index -lt $Expected.Count; $index++) {
            if (-not (Test-ExactDeploymentValue $Actual[$index] $Expected[$index])) { return $false }
        }
        return $true
    }
    return $Actual -ceq $Expected
}

function Test-ReviewedGatewayConfig($Running, $Selected, [string]$DemoAlias = '') {
    $expected = $Selected | ConvertTo-Json -Depth 30 | ConvertFrom-Json
    $expected | Add-Member -NotePropertyName demo_no_thinking_model -NotePropertyValue $DemoAlias -Force
    $expected | Add-Member -NotePropertyName queue_limit -NotePropertyValue 8 -Force
    $expected | Add-Member -NotePropertyName queue_seconds -NotePropertyValue 120 -Force
    $expected | Add-Member -NotePropertyName console_trace -NotePropertyValue $false -Force
    $expected | Add-Member -NotePropertyName native_sdk_proxy -NotePropertyValue $true -Force
    return Test-ExactDeploymentValue $Running $expected
}

function Test-SameGatewayCredential($Existing, $Selected, [string]$ExistingDirectory, [string]$SelectedDirectory) {
    $values = @()
    foreach ($entry in @(@($Existing,$ExistingDirectory),@($Selected,$SelectedDirectory))) {
        if ('token_file' -notin @($entry[0].PSObject.Properties.Name)) { throw 'Gateway API credential reference missing; migration refused.' }
        $path = [string]$entry[0].token_file
        if (-not [IO.Path]::IsPathRooted($path)) { $path = Join-Path $entry[1] $path }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -gt 8192) {
            throw 'Gateway API credential file missing or malformed; migration refused.'
        }
        $value = (Get-Content -LiteralPath $path -Raw).Trim()
        if (-not $value -or $value.Length -gt 8192) { throw 'Gateway API credential is malformed; migration refused.' }
        $values += $value
    }
    return [string]::Equals($values[0],$values[1],[StringComparison]::Ordinal)
}

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
$Python = (Resolve-Path -LiteralPath $Python).Path
$deployment = Read-ReviewedModelDeployment $Python $DeploymentScript $DeploymentScriptHash
if ($ProfileConfig -and (Resolve-Path -LiteralPath $ProfileConfig).Path -ne $deployment.profile) {
    throw 'Requested gateway profile differs from the reviewed model deployment.'
}
$ProfileConfig = [string]$deployment.profile
$config = Get-Content -LiteralPath $ProfileConfig -Raw | ConvertFrom-Json
foreach ($field in @('token_file','backend_token_file')) {
    if ($config.PSObject.Properties.Name -contains $field -and $config.$field) {
        $tokenPath = [string]$config.$field
        if (-not [IO.Path]::IsPathRooted($tokenPath)) { $tokenPath = Join-Path (Split-Path -Parent $ProfileConfig) $tokenPath }
        $config.$field = (Resolve-Path -LiteralPath $tokenPath).Path
    }
}
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    $previousConfig = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    if (-not (Test-SameGatewayCredential $previousConfig $config (Split-Path -Parent $ConfigPath) (Split-Path -Parent $ProfileConfig))) {
        throw 'Selected profile changes the public gateway credential; explicit credential preservation is required before migration.'
    }
}
if ($null -ne $owned) {
    $runningConfig = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    $runningState = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    $requestedDemoAlias = $(if ($DemoNoThinking) { 'halogen-v2' } else { '' })
    if ('profile_sha256' -notin @($runningState.PSObject.Properties.Name) -or
        'profile' -notin @($runningState.PSObject.Properties.Name) -or
        $runningState.profile_sha256 -ne $deployment.profile_sha256 -or
        $runningState.profile -ne $ProfileConfig -or
        -not (Test-ReviewedGatewayConfig $runningConfig $config $requestedDemoAlias)) {
        throw 'Running gateway profile differs from the reviewed deployment; wait for idle, then replace only the owned sidecar.'
    }
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
$ProfileConfig = (Resolve-Path -LiteralPath $ProfileConfig).Path
if ($config.backend.upstream -ne 'http://127.0.0.1:8731') {
    throw 'This sidecar is restricted to the existing loopback backend on 8731.'
}
if ($DemoNoThinking -and $config.backend.identifier -ne 'halogen-v2') {
    throw 'Demo no-thinking mode is restricted to the reviewed ServiceNow public alias halogen-v2.'
}
$demoAlias = $(if ($DemoNoThinking) { 'halogen-v2' } else { '' })
$config | Add-Member -NotePropertyName demo_no_thinking_model -NotePropertyValue $demoAlias -Force
$config | Add-Member -NotePropertyName queue_limit -NotePropertyValue 8 -Force
$config | Add-Member -NotePropertyName queue_seconds -NotePropertyValue 120 -Force
$config | Add-Member -NotePropertyName console_trace -NotePropertyValue $false -Force
$config | Add-Member -NotePropertyName native_sdk_proxy -NotePropertyValue $true -Force
New-Item -ItemType Directory -Path $LocalDirectory -Force | Out-Null
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
$arguments = @('-u', ('"{0}"' -f $GatewayPath), '--config', ('"{0}"' -f $ConfigPath),
               '--port', "$Port", '--log', ('"{0}"' -f $LogPath))
$child = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $RepoRoot -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -WindowStyle Hidden -PassThru
[pscustomobject]@{
    pid=$child.Id; started_ticks=$child.StartTime.ToUniversalTime().Ticks.ToString()
    port=$Port; python=$Python; gateway=$GatewayPath; config=$ConfigPath
    profile=$ProfileConfig; profile_sha256=$deployment.profile_sha256
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
