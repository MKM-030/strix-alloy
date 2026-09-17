<#
  start-strix-alloy.ps1 — ordinary-user launcher for the installed strix-alloy package.

  Design rules (from the release handover):
    * paths derive from the install location + per-user config, never from C:\AI\build or a repo
    * bind 127.0.0.1 only; never open a firewall rule or a LAN listener
    * single instance: verify executable identity, not just the port
    * stop only the process we started (recorded by pid + creation time); never kill by name
    * no admin required; no machine-wide policy changes
    * runtime PATH additions are process-local
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status', 'logs', 'configure')]
    [string]$Action = 'start',
    [switch]$NoBrowser,
    [switch]$NoWait
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Paths: install dir is where this script lives; user data is under LOCALAPPDATA.
# ---------------------------------------------------------------------------
$InstallDir = Split-Path -Parent $PSScriptRoot
$AppDir     = Join-Path $InstallDir 'app'
$BinDir     = Join-Path $InstallDir 'runtime'
$UserRoot   = Join-Path $env:LOCALAPPDATA 'strix-alloy'
$ConfigPath = Join-Path $UserRoot 'config.json'
$LogDir     = Join-Path $UserRoot 'logs'
$StatePath  = Join-Path $UserRoot 'state.json'

New-Item -ItemType Directory -Path $UserRoot, $LogDir -Force | Out-Null

$ServerExe  = Join-Path $BinDir 'llama-server.exe'
$DefaultPort = 8899

function Write-Log([string]$msg) {
    $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -Path (Join-Path $LogDir 'launcher.log') -Value $line
}

function Read-Json([string]$path) {
    if (Test-Path $path) {
        try { return Get-Content $path -Raw | ConvertFrom-Json } catch { return $null }
    }
    return $null
}

function Get-Config {
    $cfg = Read-Json $ConfigPath
    if ($null -eq $cfg) { return $null }
    return $cfg
}

function Save-Config($cfg) {
    $cfg | ConvertTo-Json -Depth 6 | Set-Content $ConfigPath -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Owned-process tracking: pid + creation time, so a reused pid is not mistaken for ours.
# ---------------------------------------------------------------------------
function Get-OwnedProcess {
    $st = Read-Json $StatePath
    if ($null -eq $st -or -not $st.pid) { return $null }
    $p = Get-Process -Id $st.pid -ErrorAction SilentlyContinue
    if ($null -eq $p) { return $null }
    try {
        $created = $p.StartTime.ToUniversalTime()
        $recorded = ([datetime]$st.startedAt).ToUniversalTime()
        if ([Math]::Abs(($created - $recorded).TotalSeconds) -gt 5) { return $null }  # pid reuse
    } catch { return $null }
    return $p
}

# ---------------------------------------------------------------------------
# Runtime DLL discovery: report the ACTUAL loaded paths, not just filenames.
# ---------------------------------------------------------------------------
function Show-RuntimeDlls {
    Write-Log "runtime directory: $BinDir"
    foreach ($d in 'amdhip64_7.dll', 'amd_comgr.dll', 'amdocl64.dll') {
        $p = Join-Path $BinDir $d
        if (Test-Path $p) {
            $v = (Get-Item $p).VersionInfo.FileVersion
            Write-Log ("  {0}  version={1}" -f $d, $(if ($v) { $v } else { '(none)' }))
        } else {
            Write-Log ("  {0}  MISSING from runtime/" -f $d)
        }
    }
}

# ---------------------------------------------------------------------------
# Model discovery / validation
# ---------------------------------------------------------------------------
function Find-ModelShards([string]$dir) {
    if (-not (Test-Path $dir)) { return @() }
    return @(Get-ChildItem $dir -Filter '*.gguf' -File -ErrorAction SilentlyContinue |
             Where-Object { $_.Name -notmatch 'mtp|MTP' } | Sort-Object Name)
}

function Validate-Selection($cfg) {
    $problems = @()
    if (-not $cfg.modelDir) { $problems += 'no model directory configured'; return $problems }
    if (-not (Test-Path $cfg.modelDir)) { $problems += "model directory not found: $($cfg.modelDir)"; return $problems }

    $shards = Find-ModelShards $cfg.modelDir
    if ($shards.Count -eq 0) { $problems += "no .gguf target model in $($cfg.modelDir)" }

    # shard-set consistency: if the files are `-00001-of-000NN`, all NN must be present
    $first = $shards | Where-Object { $_.Name -match '-(\d{5})-of-(\d{5})\.gguf$' } | Select-Object -First 1
    if ($first) {
        $null = $first.Name -match '-(\d{5})-of-(\d{5})\.gguf$'
        $total = [int]$Matches[2]
        if ($shards.Count -ne $total) {
            $problems += "expected $total shards, found $($shards.Count) in $($cfg.modelDir)"
        }
    }

    if ($cfg.draftPath) {
        if (-not (Test-Path $cfg.draftPath)) {
            $problems += "draft sidecar not found: $($cfg.draftPath)"
        }
    }
    return $problems
}

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
function Invoke-Configure {
    Write-Host ''
    Write-Host 'strix-alloy first-run configuration'
    Write-Host '---------------------------------'
    Write-Host 'Point this at the folder containing your Qwen3.8-Flash-Next GGUF shards.'
    Write-Host "Known model folders on this machine:"
    foreach ($c in 'C:\AI\models\qwen38-flash\projfix', 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS') {
        if (Test-Path $c) { Write-Host ("   " + $c) }
    }
    Write-Host ''
    $dir = Read-Host 'Model folder (blank = keep current)'
    $cfg = Get-Config
    if ($null -eq $cfg) { $cfg = [pscustomobject]@{} }

    if ($dir) {
        if (-not (Test-Path $dir)) { throw "folder not found: $dir" }
        $cfg | Add-Member -NotePropertyName modelDir -NotePropertyValue $dir -Force
    }
    Write-Host ''
    $draft = Read-Host 'Draft head (.gguf) for speculative decoding (blank = serial only)'
    if ($draft) {
        if (-not (Test-Path $draft)) { throw "draft not found: $draft" }
        $cfg | Add-Member -NotePropertyName draftPath -NotePropertyValue $draft -Force
    } else {
        $cfg | Add-Member -NotePropertyName draftPath -NotePropertyValue '' -Force
    }
    $cfg | Add-Member -NotePropertyName port -NotePropertyValue $DefaultPort -Force
    $cfg | Add-Member -NotePropertyName contextSize -NotePropertyValue 32768 -Force
    $cfg | Add-Member -NotePropertyName ubatch -NotePropertyValue 2048 -Force
    Save-Config $cfg
    Write-Host ''
    Write-Host ("Saved to {0}" -f $ConfigPath)
    $probs = Validate-Selection $cfg
    if ($probs.Count) { $probs | ForEach-Object { Write-Host ("  ! " + $_) } }
    else { Write-Host '  Configuration validates.' }
}

function Invoke-Start {
    $existing = Get-OwnedProcess
    if ($existing) {
        Write-Log ("already running (pid {0}); opening the existing UI instead of loading the model again" -f $existing.Id)
        $cfg = Get-Config
        $port = if ($cfg.port) { $cfg.port } else { $DefaultPort }
        if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$port" }
        return
    }

    $cfg = Get-Config
    if ($null -eq $cfg -or -not $cfg.modelDir) {
        Write-Log 'no configuration yet; running first-run setup'
        Invoke-Configure
        $cfg = Get-Config
    }

    $probs = Validate-Selection $cfg
    if ($probs.Count) {
        Write-Host ''
        Write-Host 'Cannot start - model selection problem:' -ForegroundColor Red
        $probs | ForEach-Object { Write-Host ("  ! " + $_) -ForegroundColor Red }
        Write-Host ''
        Write-Host "Edit $ConfigPath or run:  $($MyInvocation.MyCommand.Name) -Action configure"
        exit 2
    }

    Show-RuntimeDlls

    $port = if ($cfg.port) { $cfg.port } else { $DefaultPort }
    $ctx  = if ($cfg.contextSize) { $cfg.contextSize } else { 32768 }
    $ub   = if ($cfg.ubatch) { $cfg.ubatch } else { 2048 }
    $first = (Find-ModelShards $cfg.modelDir)[0]

    # Validated inference flags. Serial profile when no draft is configured - never silently
    # change mode; the log states which profile ran.
    $argv = @(
        '-m', $first.FullName,
        '-dev', 'ROCm0', '-ngl', '99', '-fa', 'on', '-fit', 'off', '--load-mode', 'none',
        '-ctk', 'f16', '-ctv', 'f16',
        '-c', "$ctx", '-b', "$ub", '-ub', "$ub",
        '--parallel', '1', '--host', '127.0.0.1', '--port', "$port",
        '--seed', '1234', '--jinja'
    )
    $profile = 'serial'
    if ($cfg.draftPath -and (Test-Path $cfg.draftPath)) {
        $argv += @('-md', $cfg.draftPath, '--spec-type', 'draft-mtp',
                   '--spec-draft-device', 'ROCm0', '--spec-draft-ngl', '99', '--spec-draft-n-max', '2')
        $profile = 'mtp-2'
    }
    Write-Log ("profile: {0}" -f $profile)
    Write-Log ("starting: {0} on 127.0.0.1:{1} ctx={2} ub={3}" -f $first.Name, $port, $ctx, $ub)

    # process-local runtime PATH only; the user's environment is untouched
    $env:PATH = "$BinDir;$env:PATH"
    $env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'

    $stdout = Join-Path $LogDir 'server.stdout.log'
    $stderr = Join-Path $LogDir 'server.stderr.log'
    $p = Start-Process -FilePath $ServerExe -ArgumentList $argv -PassThru -NoNewWindow `
                       -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    [pscustomobject]@{ pid = $p.Id; startedAt = $p.StartTime.ToUniversalTime().ToString('o');
                       port = $port; profile = $profile; model = $first.FullName } |
        ConvertTo-Json | Set-Content $StatePath -Encoding UTF8

    if ($NoWait) { Write-Log "started (pid $($p.Id)); not waiting"; return }

    Write-Host ''
    Write-Host 'Loading the model - this can take a couple of minutes on first start.' -ForegroundColor Cyan
    $ready = $false
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt 900) {
        if ($p.HasExited) { break }
        try {
            if ((Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 4 -UseBasicParsing).StatusCode -eq 200) {
                $ready = $true; break
            }
        } catch { Start-Sleep -Seconds 3 }
    }

    if ($ready) {
        Write-Log ("ready after {0}s" -f [int]((Get-Date) - $t0).TotalSeconds)
        Write-Host ''
        Write-Host ("strix-alloy is running: http://127.0.0.1:{0}" -f $port) -ForegroundColor Green
        Write-Host ("logs: {0}" -f $LogDir)
        if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$port" }
    } else {
        Write-Host ''
        Write-Host 'The server did not become ready.' -ForegroundColor Red
        Write-Host ("See {0}" -f $stderr)
        Get-Content $stderr -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('  ' + $_) }
        exit 3
    }
}

function Invoke-Stop {
    $p = Get-OwnedProcess
    if (-not $p) {
        Write-Log 'no owned server is running (nothing stopped)'
        Remove-Item $StatePath -Force -ErrorAction SilentlyContinue
        return
    }
    Write-Log ("stopping owned server pid {0}" -f $p.Id)
    # Graceful first, then escalate. A console app has no main window, so CloseMainWindow() is a
    # no-op and `taskkill /T` without /F only posts a close request that a windowless process
    # ignores -- verified: it fails with "could not be terminated". Escalate to /F once we have
    # confirmed ownership (pid AND creation time), which is what makes force-terminating safe.
    try { $p.CloseMainWindow() | Out-Null } catch {}
    Start-Sleep -Seconds 3
    if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) {
        Write-Log 'graceful close had no effect (console process); terminating the owned process tree'
        & taskkill /F /T /PID $p.Id 2>&1 | Out-Null
        # The process takes a moment to actually exit after taskkill returns (it is still releasing
        # several GB of device memory). Poll instead of sleeping a fixed 2s, otherwise this logs a
        # false "still alive" warning for a stop that in fact succeeded.
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline -and (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
            Start-Sleep -Milliseconds 500
        }
    }
    if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) {
        Write-Log ("WARNING: pid {0} is still alive after force kill" -f $p.Id)
    } else {
        Write-Log 'stopped'
    }
    Remove-Item $StatePath -Force -ErrorAction SilentlyContinue
}

function Invoke-Status {
    $p = Get-OwnedProcess
    $cfg = Get-Config
    $port = if ($cfg -and $cfg.port) { $cfg.port } else { $DefaultPort }
    if ($p) {
        Write-Host ("running   pid={0}  started={1}" -f $p.Id, $p.StartTime)
        Write-Host ("endpoint  http://127.0.0.1:{0}" -f $port)
        try {
            $h = Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 4 -UseBasicParsing
            Write-Host ("health    {0}" -f $h.StatusCode)
        } catch { Write-Host 'health    not responding' }
    } else {
        Write-Host 'not running'
        # distinguish "someone else owns this port" from "nothing there"
        $conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if ($conn) {
            $other = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            Write-Host ("note      port {0} is used by '{1}' (pid {2}) which this launcher does not own" -f `
                        $port, $other.ProcessName, $conn.OwningProcess)
        }
    }
    if ($cfg) {
        Write-Host ("config    {0}" -f $ConfigPath)
        Write-Host ("modelDir  {0}" -f $cfg.modelDir)
        Write-Host ("draft     {0}" -f $(if ($cfg.draftPath) { $cfg.draftPath } else { '(none - serial profile)' }))
    } else {
        Write-Host 'config    not configured yet'
    }
    Write-Host ("logs      {0}" -f $LogDir)
}

switch ($Action) {
    'start'     { Invoke-Start }
    'stop'      { Invoke-Stop }
    'status'    { Invoke-Status }
    'configure' { Invoke-Configure }
    'logs'      { Get-ChildItem $LogDir -File | ForEach-Object { Write-Host $_.FullName } }
}
