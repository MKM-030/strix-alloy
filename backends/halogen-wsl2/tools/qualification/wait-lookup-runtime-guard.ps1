function Wait-LookupRuntimeGuard {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][string]$LogPath,
        [Parameter(Mandatory)][string]$ContainerId,
        [Parameter(Mandatory)][DateTime]$NotBeforeUtc,
        [int]$TimeoutSeconds = 30,
        [int]$PollMilliseconds = 100
    )
    if ($ContainerId -notmatch '^[0-9a-f]{64}$') { throw 'Invalid runtime guard container ID' }
    $deadline = [System.Diagnostics.Stopwatch]::StartNew()
    while ($deadline.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "Runtime guard exited before handoff (code $($Process.ExitCode))" }
        if (Test-Path -LiteralPath $LogPath) {
            $validated = $false
            $sampled = $false
            try { $lines = @(Get-Content -LiteralPath $LogPath -ErrorAction Stop) }
            catch [System.IO.IOException] { $lines = @() }
            foreach ($line in $lines) {
                try { $record = $line | ConvertFrom-Json -ErrorAction Stop }
                catch { continue } # A concurrent append may leave the final line incomplete.
                if (-not $record.utc) { throw 'Runtime guard record has no timestamp' }
                try {
                    $eventUtc = if ($record.utc -is [DateTime]) { $record.utc.ToUniversalTime() }
                        else { [DateTimeOffset]::Parse([string]$record.utc, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime }
                }
                catch { throw 'Runtime guard record has an invalid timestamp' }
                if ($eventUtc -lt $NotBeforeUtc -or $eventUtc -gt [DateTime]::UtcNow.AddSeconds(5)) {
                    throw 'Stale or future runtime guard record'
                }
                switch ($record.event) {
                    'validated' {
                        if ($record.container_id -cne $ContainerId -or $record.phase -cne 'runtime' -or
                            $record.duration_seconds -ne 900) {
                            throw 'Runtime guard validated a different target or phase'
                        }
                        $validated = $true
                    }
                    'sample' {
                        if (-not $validated) { throw 'Runtime guard sampled before validation' }
                        if ($record.action -cne 'wait' -or $null -eq $record.available_bytes -or
                            [int64]$record.available_bytes -lt (24 * 1GB)) {
                            throw 'Runtime guard first sample was unsafe'
                        }
                        $sampled = $true
                    }
                    { $_ -in @('failed', 'stopped', 'stop_failed', 'runtime_complete') } {
                        throw "Runtime guard terminated during handoff: $($record.event)"
                    }
                }
            }
            if ($validated -and $sampled) {
                $Process.Refresh()
                if ($Process.HasExited) { throw "Runtime guard exited before handoff (code $($Process.ExitCode))" }
                return
            }
        }
        Start-Sleep -Milliseconds $PollMilliseconds
    }
    throw 'Runtime guard did not validate and sample before handoff timeout'
}
