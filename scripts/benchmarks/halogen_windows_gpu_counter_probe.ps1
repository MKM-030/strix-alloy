<#
Read-only Windows GPU Engine counter acquisition. The caller owns the logger
process, its memory guard and cleanup. This script never starts/stops an engine
or provider, changes a setting, or reads a process command line/model payload.
It writes only new evidence at OutFile and the derived atomic ready receipt.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutFile,
    [Parameter(Mandatory = $true)][string]$StopFile,
    [ValidateRange(1, 1200)][int]$MaximumSeconds = 1200,
    [ValidateRange(1000, 10000)][int]$IntervalMilliseconds = 1000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$taskEncoding = [System.Text.UTF8Encoding]::new($false)
$taskMaximumRows = 4096
$taskMaximumBytes = 256L * 1024L * 1024L
$taskCounterPath = '\GPU Engine(*)\Utilization Percentage'
$taskFrequency = [Diagnostics.Stopwatch]::Frequency
$taskOutputPath = [IO.Path]::GetFullPath($OutFile)
$taskStopPath = [IO.Path]::GetFullPath($StopFile)
$taskReadyPath = $taskOutputPath + '.ready.json'
$taskDirectory = [IO.Path]::GetDirectoryName($taskOutputPath)
if (-not [IO.Directory]::Exists($taskDirectory)) { throw 'Output directory must already exist.' }
if ($taskOutputPath -eq $taskStopPath -or $taskReadyPath -eq $taskStopPath) {
    throw 'StopFile must differ from evidence paths.'
}
if ([IO.File]::Exists($taskReadyPath)) { throw 'Ready receipt already exists.' }
$taskSourceSha = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskSeenPids = [Collections.Generic.HashSet[int]]::new()
$taskBytesWritten = 0L
$taskSamplesWritten = 0
$taskReadyWritten = $false
$taskExitCode = 0
$taskStopReason = 'deadline'
$taskWriter = $null
$taskStream = $null
$taskStartedQpc = [Diagnostics.Stopwatch]::GetTimestamp()
$taskDeadlineQpc = $taskStartedQpc + [long]($MaximumSeconds * $taskFrequency)
$taskPhase = 'output_setup'

function Get-TaskEpochNanoseconds {
    return [long](([DateTime]::UtcNow.Ticks - 621355968000000000L) * 100L)
}

function Get-TaskErrorIdentity([System.Exception]$Exception) {
    $taskInner = $Exception
    while ($null -ne $taskInner.InnerException) { $taskInner = $taskInner.InnerException }
    $taskErrorRecord = [ordered]@{ exception_type = $taskInner.GetType().FullName }
    if ($taskInner -is [ComponentModel.Win32Exception]) {
        $taskErrorRecord.native_error_code = $taskInner.NativeErrorCode
    }
    return $taskErrorRecord
}

function Write-TaskRecord($Record) {
    $taskLine = $Record | ConvertTo-Json -Depth 7 -Compress
    $taskLineBytes = [long]$taskEncoding.GetByteCount($taskLine) + 1L
    # Leave room for a bounded terminal record even when the evidence ceiling is reached.
    if ($script:taskBytesWritten + $taskLineBytes -gt $taskMaximumBytes - 8192L) {
        throw 'Evidence byte ceiling exceeded.'
    }
    $taskWriter.WriteLine($taskLine)
    $script:taskBytesWritten += $taskLineBytes
}

function Get-TaskProcessIdentity([int]$ProcessId) {
    $taskIdentity = [ordered]@{
        pid = $ProcessId
        first_seen_qpc = [Diagnostics.Stopwatch]::GetTimestamp()
        first_seen_epoch_ns = Get-TaskEpochNanoseconds
        name = $null
        executable_basename = $null
        creation_time_utc = $null
        identity_valid = $false
        acquired_once_per_pid = $true
        errors = @()
    }
    $taskProcess = $null
    try {
        $taskProcess = [Diagnostics.Process]::GetProcessById($ProcessId)
        try { $taskIdentity.name = $taskProcess.ProcessName }
        catch { $taskIdentity.errors += @{ operation = 'ProcessName'; error = Get-TaskErrorIdentity $_.Exception } }
        try {
            $taskIdentity.creation_time_utc = $taskProcess.StartTime.ToUniversalTime().ToString('o')
            $taskIdentity.identity_valid = $true
        }
        catch { $taskIdentity.errors += @{ operation = 'StartTime'; error = Get-TaskErrorIdentity $_.Exception } }
        try {
            $taskExecutable = $taskProcess.MainModule.FileName
            $taskIdentity.executable_basename = [IO.Path]::GetFileName($taskExecutable)
            $taskExecutableInfo = [IO.FileInfo]::new($taskExecutable)
            if ($taskExecutableInfo.Exists) {
                $taskIdentity.executable_size_bytes = $taskExecutableInfo.Length
                $taskIdentity.executable_mtime_utc = $taskExecutableInfo.LastWriteTimeUtc.ToString('o')
            }
        }
        catch { $taskIdentity.errors += @{ operation = 'ExecutableMetadata'; error = Get-TaskErrorIdentity $_.Exception } }
    }
    catch { $taskIdentity.errors += @{ operation = 'GetProcessById'; error = Get-TaskErrorIdentity $_.Exception } }
    finally { if ($null -ne $taskProcess) { $taskProcess.Dispose() } }
    $taskIdentity.after_qpc = [Diagnostics.Stopwatch]::GetTimestamp()
    $taskIdentity.after_epoch_ns = Get-TaskEpochNanoseconds
    return $taskIdentity
}

function Write-TaskReady($FirstSample) {
    $taskReady = [ordered]@{
        schema = 'halogen.windows-gpu-engine-ready.v1'
        source_sha256 = $taskSourceSha
        logger_pid = $PID
        first_sample_index = $FirstSample.sample_index
        first_sample_rows = $FirstSample.counters.Count
        first_sample_qpc_start = $FirstSample.qpc_start
        first_sample_qpc_end = $FirstSample.qpc_end
        qpc_frequency = $taskFrequency
        output_flushed = $true
        ready_epoch_ns = Get-TaskEpochNanoseconds
    }
    $taskTemporaryPath = $taskReadyPath + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($taskTemporaryPath, (($taskReady | ConvertTo-Json -Depth 4 -Compress) + "`n"), $taskEncoding)
        [IO.File]::Move($taskTemporaryPath, $taskReadyPath)
    }
    finally {
        if ([IO.File]::Exists($taskTemporaryPath)) { [IO.File]::Delete($taskTemporaryPath) }
    }
    $script:taskReadyWritten = $true
}

try {
    $taskStream = [IO.FileStream]::new($taskOutputPath, [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $taskWriter = [IO.StreamWriter]::new($taskStream, $taskEncoding)
    $taskWriter.NewLine = "`n"
    Write-TaskRecord ([ordered]@{
        schema = 'halogen.windows-gpu-engine-header.v1'
        source_sha256 = $taskSourceSha
        logger_pid = $PID
        counter = $taskCounterPath
        maximum_seconds = $MaximumSeconds
        interval_milliseconds = $IntervalMilliseconds
        maximum_rows_per_sample = $taskMaximumRows
        maximum_output_bytes = $taskMaximumBytes
        qpc_frequency = $taskFrequency
        started_qpc = $taskStartedQpc
        started_epoch_ns = Get-TaskEpochNanoseconds
        settings_changed = $false
        model_payload_bytes_read = 0
        process_identity_scope = 'One getter acquisition at first seen PID; PID reuse is not revalidated.'
    })
    while ($true) {
        if ([IO.File]::Exists($taskStopPath)) { $taskStopReason = 'stopfile'; break }
        if ([Diagnostics.Stopwatch]::GetTimestamp() -ge $taskDeadlineQpc) { break }
        $taskQueryStartQpc = [Diagnostics.Stopwatch]::GetTimestamp()
        $taskQueryStartEpochNs = Get-TaskEpochNanoseconds
        $taskPhase = 'counter_query'
        $taskCounterErrors = @()
        # Nonterminating PDH errors can accompany a batch containing invalid
        # instance statuses. Keep that batch and its errors for coverage analysis.
        $taskBatch = Get-Counter -Counter $taskCounterPath -MaxSamples 1 `
            -ErrorAction SilentlyContinue -ErrorVariable taskCounterErrors
        $taskQueryEndEpochNs = Get-TaskEpochNanoseconds
        $taskQueryEndQpc = [Diagnostics.Stopwatch]::GetTimestamp()
        $taskRawRows = @()
        $taskBatchTimestamp = $null
        if ($null -ne $taskBatch) {
            $taskRawRows = @($taskBatch.CounterSamples)
            $taskBatchTimestamp = $taskBatch.Timestamp.ToUniversalTime().ToString('o')
        }
        $taskQueryErrors = @($taskCounterErrors | ForEach-Object { Get-TaskErrorIdentity $_.Exception })
        $taskPhase = 'counter_row_validation'
        if ($taskRawRows.Count -gt $taskMaximumRows) { throw 'Counter instance ceiling exceeded.' }
        $taskRows = @($taskRawRows | ForEach-Object {
            $taskCounter = $_
            foreach ($taskRequired in @('InstanceName', 'Path', 'Status', 'CounterType',
                'CookedValue', 'RawValue', 'Timestamp', 'Timestamp100NSec')) {
                if ($null -eq $taskCounter.PSObject.Properties[$taskRequired]) {
                    throw ('Missing counter property: ' + $taskRequired)
                }
            }
            $taskProcessId = $null
            if ($taskCounter.InstanceName -match '^pid_(\d+)_') { $taskProcessId = [int]$Matches[1] }
            [ordered]@{
                instance_name = [string]$taskCounter.InstanceName
                pid = $taskProcessId
                path = [string]$taskCounter.Path
                status = [long]$taskCounter.Status
                counter_type = [long]$taskCounter.CounterType
                cooked_value = $taskCounter.CookedValue
                raw_value = [string]$taskCounter.RawValue
                timestamp_utc = $taskCounter.Timestamp.ToUniversalTime().ToString('o')
                timestamp_100nsec = [string]$taskCounter.Timestamp100NSec
            }
        })
        $taskPhase = 'first_seen_process_identity'
        $taskIdentities = @()
        foreach ($taskRow in $taskRows) {
            if ($null -ne $taskRow.pid -and $taskSeenPids.Add($taskRow.pid)) {
                $taskIdentities += Get-TaskProcessIdentity $taskRow.pid
            }
        }
        $taskSample = [ordered]@{
            schema = 'halogen.windows-gpu-engine-sample.v1'
            sample_index = $taskSamplesWritten
            qpc_start = $taskQueryStartQpc
            qpc_end = $taskQueryEndQpc
            qpc_frequency = $taskFrequency
            epoch_ns_start = $taskQueryStartEpochNs
            epoch_ns_end = $taskQueryEndEpochNs
            batch_timestamp_utc = $taskBatchTimestamp
            counters = $taskRows
            counter_query_errors = $taskQueryErrors
            first_seen_processes = $taskIdentities
        }
        $taskPhase = 'sample_write'
        Write-TaskRecord $taskSample
        $taskSamplesWritten++
        $taskWriter.Flush()
        if (-not $taskReadyWritten) {
            $taskPhase = 'ready_admission'
            if (@($taskRows | Where-Object { $_.status -eq 0 }).Count -eq 0) {
                throw 'First sample has no valid GPU Engine counters.'
            }
            $taskStream.Flush($true)
            Write-TaskReady $taskSample
        }
        if ([IO.File]::Exists($taskStopPath)) { $taskStopReason = 'stopfile'; break }
        $taskNextQpc = $taskQueryStartQpc + [long]($IntervalMilliseconds * $taskFrequency / 1000.0)
        while ([Diagnostics.Stopwatch]::GetTimestamp() -lt $taskNextQpc) {
            if ([IO.File]::Exists($taskStopPath)) { $taskStopReason = 'stopfile'; break }
            if ([Diagnostics.Stopwatch]::GetTimestamp() -ge $taskDeadlineQpc) { break }
            Start-Sleep -Milliseconds 50
        }
        if ($taskStopReason -eq 'stopfile') { break }
    }
}
catch {
    $taskExitCode = 1
    $taskStopReason = 'error'
    $taskFailure = Get-TaskErrorIdentity $_.Exception
    $taskFailure.phase = $taskPhase
}
finally {
    if ($null -ne $taskWriter) {
        $taskTerminal = [ordered]@{
            schema = 'halogen.windows-gpu-engine-terminal.v1'
            reason = $taskStopReason
            exit_code = $taskExitCode
            samples_written = $taskSamplesWritten
            ready_written = $taskReadyWritten
            bytes_before_terminal = $taskBytesWritten
            finished_qpc = [Diagnostics.Stopwatch]::GetTimestamp()
            finished_epoch_ns = Get-TaskEpochNanoseconds
        }
        if ($taskExitCode -ne 0) { $taskTerminal.error = $taskFailure }
        try {
            $taskTerminalLine = $taskTerminal | ConvertTo-Json -Depth 5 -Compress
            $taskTerminalBytes = [long]$taskEncoding.GetByteCount($taskTerminalLine) + 1L
            if ($taskBytesWritten + $taskTerminalBytes -le $taskMaximumBytes) {
                $taskWriter.WriteLine($taskTerminalLine)
                $taskBytesWritten += $taskTerminalBytes
            }
            $taskWriter.Flush()
        }
        finally { $taskWriter.Dispose() }
    }
    elseif ($null -ne $taskStream) { $taskStream.Dispose() }
}
[ordered]@{ exit_code = $taskExitCode; reason = $taskStopReason;
    samples_written = $taskSamplesWritten; ready_written = $taskReadyWritten;
    bytes_written = $taskBytesWritten } | ConvertTo-Json -Compress
exit $taskExitCode
