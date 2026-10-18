#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BinaryDirectory,
    [Parameter(Mandatory = $true)][string]$BuildReceipt,
    [Parameter(Mandatory = $true)][string]$ModelPath,
    [Parameter(Mandatory = $true)][string]$StatePath,
    [Parameter(Mandatory = $true)][string]$ApiKeyFile,
    [ValidateRange(1, 64)][int]$Readers = 1,
    [string]$HipSdkPath = 'C:\Program Files\AMD\ROCm\7.2',
    [string]$ListenAddress = '127.0.0.1',
    [ValidateRange(1, 65535)][int]$Port = 11439,
    [ValidateRange(512, 1048576)][int]$MaxSequence = 32768
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Get-ExistingFile([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    if ($item.PSIsContainer) { throw "Expected a file: $Path" }
    return $item.FullName
}
function Assert-CandidateReceipt([string]$Path, [string]$Cli, [string]$Daemon) {
    $receiptFile = Get-ExistingFile $Path
    $receipt = Get-Content -LiteralPath $receiptFile -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($name in @('terminal', 'build_completed')) {
        $property = $receipt.PSObject.Properties[$name]
        if ($null -eq $property -or $property.Value -isnot [bool] -or -not $property.Value) {
            throw "Candidate build receipt must report ${name}=true."
        }
    }
    if (($receipt.exit_code -isnot [int32] -and $receipt.exit_code -isnot [int64]) -or $receipt.exit_code -ne 0) {
        throw 'Candidate build receipt must report integer exit_code=0.'
    }
    $sourcePins = [ordered]@{
        'modified_source' = @('04d19e6d3cbd30ad095dc83f94dab8b3a9c5269c91957724e66cf504cf67a2e3', 107197, 'crates\hipfire-runtime\src\ple_hot_store.rs');
        'new_module' = @('eb23561ec2f7d7e26b06facacbfff593bb80fa007d21a27d296e85ecc58c5aed', 5621, 'crates\hipfire-runtime\src\windows_rank_readers.rs')
    }
    $sourceRoot = [IO.Path]::GetFullPath([string]$receipt.source)
    foreach ($entry in $sourcePins.GetEnumerator()) {
        $pin = $receipt.PSObject.Properties[$entry.Key].Value
        $expected = $entry.Value
        if (($pin.bytes -isnot [int32] -and $pin.bytes -isnot [int64]) -or
            $pin.sha256 -cne $expected[0] -or $pin.bytes -ne $expected[1]) {
            throw "Candidate build receipt has the wrong $($entry.Key) source pin."
        }
        $expectedPath = [IO.Path]::GetFullPath((Join-Path $sourceRoot $expected[2]))
        if (-not [string]::Equals([IO.Path]::GetFullPath([string]$pin.path), $expectedPath, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Candidate build receipt has an inconsistent $($entry.Key) source path."
        }
    }
    $artifacts = @($receipt.artifacts)
    if ($artifacts.Count -ne 2) { throw 'Candidate build receipt must contain exactly hipfire.exe and daemon.exe.' }
    foreach ($selected in @($Cli, $Daemon)) {
        $name = [IO.Path]::GetFileName($selected)
        $artifactMatches = @($artifacts | Where-Object { [IO.Path]::GetFileName([string]$_.path) -ceq $name })
        if ($artifactMatches.Count -ne 1) { throw "Candidate build receipt must contain one $name artifact." }
        $pin = $artifactMatches[0]
        $recordedPath = [IO.Path]::GetFullPath([string]$pin.path)
        if (-not [string]::Equals($recordedPath, $selected, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Candidate $name is not the artifact recorded for the selected BinaryDirectory."
        }
        if (($pin.bytes -isnot [int32] -and $pin.bytes -isnot [int64]) -or $pin.bytes -le 0 -or
            [string]$pin.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
            throw "Candidate build receipt contains an invalid $name artifact pin."
        }
        if ((Get-Item -LiteralPath $selected).Length -ne $pin.bytes -or
            (Get-FileHash -LiteralPath $selected -Algorithm SHA256).Hash -ine [string]$pin.sha256) {
            throw "Candidate $name size or SHA256 does not match the completed build receipt."
        }
    }
}
$bin = (Get-Item -LiteralPath $BinaryDirectory).FullName
$cli = Get-ExistingFile (Join-Path $bin 'hipfire.exe')
$daemon = Get-ExistingFile (Join-Path $bin 'daemon.exe')
# Validate the completed candidate build before private state or CLI side effects.
Assert-CandidateReceipt $BuildReceipt $cli $daemon
$model = Get-ExistingFile $ModelPath
# Hipfire appends this suffix to the full model name; no conversion or download.
$ple = Get-ExistingFile ($model + '.ple-q4')
$keyFile = Get-ExistingFile $ApiKeyFile
$sdk = (Get-Item -LiteralPath $HipSdkPath).FullName
foreach ($file in @((Join-Path $sdk 'bin\amdhip64_7.dll'), (Join-Path $sdk 'bin\hipcc.exe'))) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required installed HIP SDK file missing: $file" }
}
$state = [IO.Path]::GetFullPath($StatePath)
if (Test-Path -LiteralPath $state) {
    if (@(Get-ChildItem -LiteralPath $state -Force).Count -ne 0) {
        throw 'StatePath must be a fresh or empty private directory; use a new directory for this launch.'
    }
}
if ($env:HSA_OVERRIDE_GFX_VERSION) { throw 'Unset HSA_OVERRIDE_GFX_VERSION before native hardware qualification.' }
New-Item -ItemType Directory -Path $state -Force | Out-Null
$names = @('PATH', 'ROCM_PATH', 'HIP_PATH', 'HIP_VISIBLE_DEVICES') + @(Get-ChildItem Env: | Where-Object { $_.Name -like 'HIPFIRE_*' } | ForEach-Object { $_.Name })
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    # A private config must not inherit unrelated experimental HIPFIRE overrides.
    foreach ($entry in @(Get-ChildItem Env: | Where-Object { $_.Name -like 'HIPFIRE_*' })) {
        [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process')
    }
    $env:HIPFIRE_WINDOWS_PLE_READERS = [string]$Readers
    $env:HIPFIRE_HOME = $state
    $env:HIPFIRE_DAEMON_BIN = $daemon
    $env:HIPFIRE_KERNEL_CACHE = Join-Path $state 'kernels'
    $env:HIPFIRE_ROCM_PATH = $sdk
    $env:HIPFIRE_ROCM_STRICT = '1'
    $env:HIPFIRE_HIPCC = Join-Path $sdk 'bin\hipcc.exe'
    $env:ROCM_PATH = $sdk
    $env:HIP_PATH = $sdk
    $env:HIP_VISIBLE_DEVICES = '0'
    $env:PATH = (Join-Path $sdk 'bin') + ';' + $bin + ';' + $env:PATH
    $env:HIPFIRE_ALLOW_MQ2 = '1'
    $settings = [ordered]@{
        'memory.kv_backend' = 'legacy'; 'memory.oom_guard' = 'true';
        'memory.ple_format' = 'q4'; 'memory.ple_hot_store_bytes' = '0';
        'memory.ple_prewarm_bytes' = '0'; 'memory.ple_load_fill_bytes' = '0';
        'replay.backend' = 'hip'; 'fusions.npu_trunk' = 'off'; 'vision.mode' = 'off';
        'speculation.dflash' = 'off'; 'serve.continuous_batch_size' = '1';
        'speculation.mtp_k' = '2'; 'speculation.mtp_ngram' = 'off';
        'speculation.mtp_ngram_copy' = 'off';
        'developer.qwen4_gdn_q8_inline' = '1'
    }
    foreach ($setting in $settings.GetEnumerator()) {
        & $cli config set $setting.Key $setting.Value | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not set private config key: $($setting.Key)" }
    }
    # Bind address and port are positionals in this pinned CLI, not flags.
    $serveArgs = @('serve', '--model', $model, $ListenAddress, [string]$Port,
        '--kv-backend', 'legacy', '--spec', 'mtp', '--max-seq', [string]$MaxSequence,
        '--continuous-batch-size', '1', '--api-key-file', $keyFile)
    Write-Output "Starting experimental native Hipfire with $Readers rank readers on ${ListenAddress}:$Port; qualification pending."
    # The bearer value is never read, echoed or placed on the command line.
    & $cli @serveArgs
    if ($LASTEXITCODE -ne 0) { throw "Native service exited ($LASTEXITCODE)." }
} finally {
    foreach ($entry in @(Get-ChildItem Env: | Where-Object { $_.Name -like 'HIPFIRE_*' })) {
        [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process')
    }
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
