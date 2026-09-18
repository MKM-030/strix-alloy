# launch-flash-next.ps1 - run Qwen3.8-Flash-Next with the llama-server you already use.
#
# This is deliberately NOT an application. It is a portable command template: it validates the
# model files, then invokes llama-server.exe directly with the flags that were measured for this
# model. There is no state store, no config wizard, no background service and no wrapper layer -
# stop the server the same way you stop any other llama-server.
#
# It exists because the flag set matters (device selection, cache types, load mode, the MTP draft
# wiring) and getting one of them wrong is the difference between a loaded model and an
# out-of-memory exit. The command it builds is printed, so you can copy it into your own launcher.
#
#   # serial (no speculation)
#   .\launch-flash-next.ps1 -ModelDir C:\AI\models\qwen38-flash\projfix
#
#   # with the shared MTP draft head
#   .\launch-flash-next.ps1 -ModelDir C:\AI\models\qwen38-flash\projfix `
#       -DraftPath C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
#
#   # what would run, without running it
#   .\launch-flash-next.ps1 -ModelDir <dir> -PrintOnly
#
#   # stop the server this script started (identified by port + command line, not by a pid file)
#   .\launch-flash-next.ps1 -Stop
[CmdletBinding()]
param(
    # Folder holding the target GGUF shards. The first shard of the -of-NNNNN set is selected.
    [string]$ModelDir,

    # Optional shared MTP draft head. Omit for the serial profile.
    [string]$DraftPath,

    # Optional explicit first shard, when the folder holds more than one shard family.
    [string]$ModelFile,

    # Runtime directory containing llama-server.exe and its DLLs. Defaults to the "runtime"
    # folder beside this script's parent, which is how the release archive is laid out.
    [string]$RuntimeDir,

    [int]$Port = 8826,
    [int]$ContextSize = 32768,
    [int]$Ubatch = 2048,
    [string]$Device = 'ROCm0',

    # Model id reported by /v1/models. Set explicitly so a client's configured model name keeps
    # working no matter which quant or folder the weights came from.
    [string]$Alias = 'Qwen3.8-Flash-Next',

    # Print the resolved command and exit without starting anything.
    [switch]$PrintOnly,

    # Stop the server listening on -Port, if it is running this model.
    [switch]$Stop,

    # Health wait budget in seconds.
    [int]$TimeoutSeconds = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-RuntimeDir {
    if ($RuntimeDir) { return (Resolve-Path -LiteralPath $RuntimeDir).Path }
    # <package>\app\launch-flash-next.ps1 -> <package>\runtime
    $candidate = Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime'
    if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
    throw "Could not find the runtime folder. Pass -RuntimeDir <folder containing llama-server.exe>."
}

function Get-ProcessCommandLine([int]$ProcessId) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return $null }
    return [string]$proc.CommandLine
}

# The port owner, with its command line so we can prove it is ours before touching anything.
function Get-PortOwner {
    foreach ($c in @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        [pscustomobject]@{
            Process     = $proc
            CommandLine = (Get-ProcessCommandLine $c.OwningProcess)
        }
    }
}

function Assert-ServerResponds {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5
        return $health.status -eq 'ok'
    } catch { return $false }
}

# The shard set is a family, not a single file: <name>-of-000NN. Starting the wrong one, or a
# half-downloaded set, wastes a 60+ GiB load before failing.
function Resolve-FirstShard {
    if (-not $ModelDir) { throw 'Pass -ModelDir <folder with the GGUF shards>, or -Stop.' }
    if (-not (Test-Path -LiteralPath $ModelDir)) { throw "Model folder not found: $ModelDir" }

    if ($ModelFile) {
        $explicit = Join-Path $ModelDir $ModelFile
        if (-not (Test-Path -LiteralPath $explicit)) { throw "Shard not found: $explicit" }
        return $explicit
    }

    $shards = @(Get-ChildItem -LiteralPath $ModelDir -Filter '*-of-*.gguf' -File | Sort-Object Name)
    if ($shards.Count -eq 0) {
        throw "No '-of-NNNNN' GGUF shards in $ModelDir. Pass -ModelFile for a single-file model."
    }

    $first = $shards[0]
    if ($first.Name -notmatch '-of-(\d{5})\.gguf$') {
        throw "Cannot read the shard count from '$($first.Name)'."
    }
    $expected = [int]$Matches[1]
    $family = ($shards | Where-Object { $_.Name -match '-of-' + ('{0:D5}' -f $expected) + '\.gguf$' })
    if ($family.Count -ne $expected) {
        throw ("Shard set is incomplete: {0} of {1} present in {2}. Finish the download before starting." -f `
            $family.Count, $expected, $ModelDir)
    }
    return $first.FullName
}

$serverExe = Join-Path (Resolve-RuntimeDir) 'llama-server.exe'
if (-not (Test-Path -LiteralPath $serverExe)) {
    throw "llama-server.exe not found. Pass -RuntimeDir <folder containing it>."
}

# ---------------------------------------------------------------------------
# -Stop: no pid file. Find the listener on this port and remove it only if its
# command line shows it is this model under this llama-server.
# ---------------------------------------------------------------------------
if ($Stop) {
    $owners = @(Get-PortOwner)
    if ($owners.Count -eq 0) { Write-Host "Nothing is listening on 127.0.0.1:$Port."; return }
    foreach ($o in $owners) {
        $cmd = $o.CommandLine
        if ([string]::IsNullOrWhiteSpace($cmd) -or $cmd -notlike "*$serverExe*") {
            Write-Warning "Port $Port is held by PID $($o.Process.Id), which is not this llama-server. Leaving it alone."
            Write-Warning "Command line: $cmd"
            continue
        }
        Write-Host "Stopping llama-server PID $($o.Process.Id) (port $Port)..."
        Stop-Process -Id $o.Process.Id -ErrorAction SilentlyContinue
        try { Wait-Process -Id $o.Process.Id -Timeout 60 -ErrorAction Stop } catch {
            if (Get-Process -Id $o.Process.Id -ErrorAction SilentlyContinue) {
                Write-Warning 'Graceful stop timed out; forcing. The process releases several GB of device memory, which takes a moment.'
                Stop-Process -Id $o.Process.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }
    # Give the device memory back before anything tries to claim it again.
    for ($i = 0; $i -lt 60; $i++) {
        if (@(Get-PortOwner).Count -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    Write-Host 'Stopped.'
    return
}

# ---------------------------------------------------------------------------
# Single instance: if this port already serves, do not load a second 60+ GiB model.
# ---------------------------------------------------------------------------
$existing = @(Get-PortOwner)
if ($existing.Count -gt 0) {
    $cmd = $existing[0].CommandLine
    $isOurs = ($cmd -like "*$serverExe*")
    if ($isOurs -and (Assert-ServerResponds)) {
        Write-Host "Already running on http://127.0.0.1:$Port (PID $($existing[0].Process.Id)) - reusing it."
        Write-Host "Chat:  http://127.0.0.1:$Port"
        Write-Host "API:   http://127.0.0.1:$Port/v1"
        return
    }
    throw "Port $Port is already in use by PID $($existing[0].Process.Id): $cmd`nStop that first, or choose another -Port."
}

$target = Resolve-FirstShard

$serverArgs = @(
    '-m', $target,
    '--alias', $Alias,
    '-dev', $Device,
    '-ngl', '99',
    '-fa', 'on',
    '-fit', 'off',
    '--load-mode', 'none',
    '-ctk', 'f16', '-ctv', 'f16',
    '-c', "$ContextSize",
    '-b', "$Ubatch",
    '-ub', "$Ubatch",
    '--parallel', '1',
    '--host', '127.0.0.1',
    '--port', "$Port",
    '--seed', '1234',
    '--jinja'
)

$profile = 'serial'
if ($DraftPath) {
    if (-not (Test-Path -LiteralPath $DraftPath)) { throw "Draft model not found: $DraftPath" }
    $serverArgs += @(
        '-md', $DraftPath,
        '--spec-type', 'draft-mtp',
        '--spec-draft-device', $Device,
        '--spec-draft-ngl', '99',
        '--spec-draft-n-max', '2'
    )
    $profile = 'mtp-2'
}

Write-Host "runtime : $serverExe"
Write-Host "model   : $(Split-Path $target -Leaf)"
Write-Host "profile : $profile"
Write-Host "endpoint: http://127.0.0.1:$Port/v1"
Write-Host ''
Write-Host 'command :'
Write-Host ("  `"{0}`" {1}" -f $serverExe, (($serverArgs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '))
Write-Host ''

if ($PrintOnly) { return }

# DLLs live beside the executable, and rocBLAS loads its kernel library from a path relative to
# the working directory. Start in the runtime folder rather than relying on the caller's cwd.
Push-Location (Split-Path $serverExe -Parent)
try {
    $env:HSA_OVERRIDE_GFX_VERSION = '11.5.1'
    $proc = Start-Process -FilePath $serverExe -ArgumentList $serverArgs -PassThru -NoNewWindow
} finally {
    Pop-Location
}

Write-Host "loading (this takes a minute or two for ~100 GB of weights)..."
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { throw "llama-server exited during load with code $($proc.ExitCode). Check the messages above." }
    if (Assert-ServerResponds) { $ready = $true; break }
    Start-Sleep -Seconds 2
}

if (-not $ready) {
    Write-Warning "No healthy /health after $TimeoutSeconds s. The server may still be loading; check the window."
    return
}

Write-Host ''
Write-Host "ready - http://127.0.0.1:$Port"
Write-Host "chat UI : http://127.0.0.1:$Port"
Write-Host "API     : http://127.0.0.1:$Port/v1  (model id: $(Split-Path $target -Leaf))"
Write-Host ''
Write-Host 'Leave this window open while you use the model; closing it stops the server.'
