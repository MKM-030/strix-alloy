#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BinaryDirectory,
    [Parameter(Mandatory = $true)][string]$ModelPath,
    [Parameter(Mandatory = $true)][string]$StatePath,
    [Parameter(Mandatory = $true)][string]$ApiKeyFile,
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
$bin = (Get-Item -LiteralPath $BinaryDirectory).FullName
$cli = Get-ExistingFile (Join-Path $bin 'hipfire.exe')
$daemon = Get-ExistingFile (Join-Path $bin 'daemon.exe')
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
    Write-Output "Starting native Hipfire foreground service on ${ListenAddress}:$Port; qualification pending."
    # The bearer value is never read, echoed or placed on the command line.
    & $cli @serveArgs
    if ($LASTEXITCODE -ne 0) { throw "Native service exited ($LASTEXITCODE)." }
} finally {
    foreach ($entry in @(Get-ChildItem Env: | Where-Object { $_.Name -like 'HIPFIRE_*' })) {
        [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process')
    }
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
