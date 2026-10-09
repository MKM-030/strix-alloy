param(
    [ValidateSet('verify','bench')][string]$Mode = 'verify',
    [ValidateRange(5,101)][int]$Samples = 31,
    [ValidateRange(1,64)][int]$Batch = 8,
    [string]$FixtureVerificationPath = 'C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/ple0172-native-worker-candidate-v1/verification.json'
)
$ErrorActionPreference = 'Stop'
$screenRoot = $PSScriptRoot
$verificationPath = $FixtureVerificationPath
if (!(Test-Path -LiteralPath $verificationPath)) { throw 'Offline fixture receipt missing; see README.md and pass -FixtureVerificationPath for relocated archived inputs.' }
$archiveReceipt = Get-Content -LiteralPath $verificationPath -Raw | ConvertFrom-Json
$archivedArguments = @($archiveReceipt.scalar_run.command)
$tokensPath = $archivedArguments[1]
$historyPath = $archivedArguments[2]
$constantsPath = $archivedArguments[3]
$oraclePath = $archivedArguments[4]
$inputs = [ordered]@{
    tokens = @{path=$tokensPath; expected=$archiveReceipt.bound_inputs.tokens_sha256}
    history = @{path=$historyPath; expected=$archiveReceipt.bound_inputs.history_sha256}
    constants = @{path=$constantsPath; expected=$archiveReceipt.bound_inputs.constants_sha256}
    oracle = @{path=$oraclePath; expected=$archiveReceipt.archived_suffix_ids.sha256}
}
foreach ($inputName in $inputs.Keys) {
    $entry = $inputs[$inputName]
    $actualHash = (Get-FileHash -LiteralPath $entry.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $entry.expected) { throw "Pinned $inputName SHA256 mismatch" }
    $entry.actual = $actualHash
}
$buildReceipt = Get-Content -LiteralPath (Join-Path $screenRoot 'build-receipt.json') -Raw | ConvertFrom-Json
$executablePath = Join-Path $screenRoot 'screen.exe'
$executableHash = (Get-FileHash -LiteralPath $executablePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($executableHash -ne $buildReceipt.executable_sha256) { throw 'Executable build SHA256 mismatch' }
$outputPrefix = Join-Path $screenRoot $Mode
$screenArguments = @("--$Mode",$tokensPath,$historyPath,$constantsPath,$oraclePath,$outputPrefix)
if ($Mode -eq 'bench') { $screenArguments += @("$Samples","$Batch") }
$screenOutput = @(& $executablePath @screenArguments 2>&1 | ForEach-Object { "$_" })
$screenExitCode = $LASTEXITCODE
if ($screenExitCode -ne 0) { throw ($screenOutput -join "`n") }
$screenResult = ($screenOutput -join "`n") | ConvertFrom-Json
$outputHashes = [ordered]@{}
foreach ($kind in @('baseline','literal')) {
    $outputPath = "$outputPrefix.$kind-ids-i64.bin"
    $outputHash = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($outputHash -ne $archiveReceipt.archived_suffix_ids.sha256) { throw "$kind output SHA256 differs from oracle" }
    $outputHashes[$kind] = @{path=$outputPath;sha256=$outputHash;exact_oracle_match=$true}
}
$receipt = [ordered]@{
    schema = 'ple-id-reciprocal-cpu-screen-run-v1'
    utc = [DateTime]::UtcNow.ToString('o')
    mode = $Mode
    command = @($executablePath) + $screenArguments
    exit_code = $screenExitCode
    executable_sha256 = $executableHash
    build_receipt_sha256 = (Get-FileHash -LiteralPath (Join-Path $screenRoot 'build-receipt.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    archived_receipt_path = $verificationPath
    archived_receipt_sha256 = (Get-FileHash -LiteralPath $verificationPath -Algorithm SHA256).Hash.ToLowerInvariant()
    pinned_inputs = $inputs
    output_ids = $outputHashes
    result = $screenResult
    benchmark_executed = ($Mode -eq 'bench')
    component_only = $true
    engine_accelerator_table_access = $false
    live_integration_or_patch = $false
    serving_throughput_claim = $false
}
[IO.File]::WriteAllText((Join-Path $screenRoot "$Mode-receipt.json"),($receipt | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
$screenOutput | Write-Output
