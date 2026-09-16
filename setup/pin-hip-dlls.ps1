#requires -Version 5.1
# pin-hip-dlls.ps1 — copy the SDK's HIP runtime DLLs beside llama-server.exe.
#
# WHY THIS IS NOT OPTIONAL:
#   ggml-hip.dll imports "amdhip64_7.dll" BY NAME. Windows resolves a DLL by searching
#     (1) the executable's own directory, (2) System32, (3) PATH.
#   With no local copy, the GPU driver's older copy in C:\Windows\System32 shadows the SDK's, and HIP
#   fails at device init with a misleading error:
#       cudaMemGetInfo failed (invalid argument), returning 0/0
#   The SDK's own hipInfo.exe still works (it resolves its own directory), which makes this very hard
#   to diagnose by hand. Placing the SDK runtime beside the exe makes the correct pair win.
#
# This is a LOADING-ORDER fix, not a security pin: it makes the search find the SDK's copy first. It
# does not validate that the copy is authentic, and it cannot override an already-loaded module or a
# loader redirection rule. To confirm what actually loaded, check the modules of the running process
# (see -Verify below).
#
# Integrity and rollback:
#   - comparison is by SHA-256, not file length (equal-length files are not equal files)
#   - a missing SDK file is an ERROR before anything is touched, not a warning mid-way
#   - existing files are backed up on first use; -Revert restores those backups
param(
    [Parameter(Mandatory = $true)][string]$Sdk,      # e.g. C:\AI\sdk\therock1151
    [Parameter(Mandatory = $true)][string]$BinDir,   # e.g. <build>\bin  (where llama-server.exe lives)
    [switch]$Revert,
    [switch]$Verify
)
$ErrorActionPreference = 'Stop'

$files  = @('amdhip64_7.dll', 'amd_comgr.dll', 'amdocl64.dll')
$sdkBin = Join-Path $Sdk 'bin'
$bakDir = Join-Path $BinDir '.hip-dll-backup'

function Get-Sha([string]$p) { return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }

if ($Verify) {
    # Report which module paths the running process actually loaded. The executable directory is not
    # the first consideration in every case (loaded modules, redirection and loader config can all
    # affect resolution), so observe rather than assume.
    $procs = Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue
    if (-not $procs) { Write-Output 'no running llama-server to inspect'; exit 0 }
    foreach ($p in $procs) {
        Write-Output "llama-server pid=$($p.Id)"
        $p.Modules | Where-Object { $_.ModuleName -match 'amdhip|amdocl|amd_comgr' } | ForEach-Object {
            Write-Output ("  {0,-22} {1}" -f $_.ModuleName, $_.FileName)
        }
    }
    exit 0
}

if ($Revert) {
    if (-not (Test-Path -LiteralPath $bakDir)) {
        Write-Output "no backup directory at $bakDir - nothing to restore."
        Write-Output "(-Revert restores a previous run's files; it does not simply delete.)"
        exit 0
    }
    foreach ($f in $files) {
        $bak = Join-Path $bakDir $f
        $dst = Join-Path $BinDir $f
        if (Test-Path -LiteralPath $bak) {
            Copy-Item -LiteralPath $bak -Destination $dst -Force
            Write-Output "restored $f from backup"
        } elseif (Test-Path -LiteralPath $dst) {
            # nothing was there before this tool ran -> the backup is an explicit "absent" marker
            Remove-Item -LiteralPath $dst -Force
            Write-Output "removed $f (no prior file existed)"
        } else {
            Write-Output "${f}: nothing to do"
        }
    }
    Write-Output 'restored.'
    exit 0
}

if (-not (Test-Path -LiteralPath $sdkBin)) { throw "SDK bin not found: $sdkBin" }
if (-not (Test-Path -LiteralPath $BinDir)) { throw "target bin not found: $BinDir" }

# fail BEFORE modifying anything if the SDK set is incomplete
$missing = $files | Where-Object { -not (Test-Path -LiteralPath (Join-Path $sdkBin $_)) }
if ($missing) {
    throw "SDK runtime incomplete; missing: $($missing -join ', ') in $sdkBin. Refusing to pin a partial set."
}

New-Item -ItemType Directory -Force -Path $bakDir | Out-Null

$changed = 0
foreach ($f in $files) {
    $src = Join-Path $sdkBin $f
    $dst = Join-Path $BinDir $f
    $bak = Join-Path $bakDir $f

    if (Test-Path -LiteralPath $dst) {
        if ((Get-Sha $src) -eq (Get-Sha $dst)) { Write-Output "$f already matches SDK (sha256)"; continue }
        if (-not (Test-Path -LiteralPath $bak)) { Copy-Item -LiteralPath $dst -Destination $bak -Force }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Write-Output "pinned $f ($(Get-Sha $dst | ForEach-Object { $_.Substring(0,12) }))"
        $changed++
    } else {
        # record that there was no prior file, so -Revert can put it back to absent
        Set-Content -LiteralPath (Join-Path $bakDir "$f.absent") -Value 'absent' -Encoding ASCII
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Write-Output "pinned $f (new, $(Get-Sha $dst | ForEach-Object { $_.Substring(0,12) }))"
        $changed++
    }
}
Write-Output "done ($changed changed). Backups in $bakDir; -Revert restores them."
