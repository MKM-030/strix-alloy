param([string]$VoiceRoot = (Split-Path -Parent $PSScriptRoot),
      [string]$Python = 'C:\Projects\strix-alloy-scc-voice\voice\native-bridge\.venv\Scripts\python.exe')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$helper = Join-Path $PSScriptRoot 'model_deployment.py'
$binding = $null
foreach ($name in @('Start-NativeModel.ps1','Start-QueuedGateway.ps1')) {
    $source = Join-Path $VoiceRoot $name
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw "$name parse errors" }
    $function = @($ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Read-ReviewedModelDeployment'},$true))
    if ($function.Count -ne 1) { throw "$name reviewed deployment reader missing" }
    . ([scriptblock]::Create($function[0].Extent.Text))
    $match = [regex]::Match((Get-Content -LiteralPath $source -Raw),"\`$DeploymentScriptHash\s*=\s*'([a-f0-9]{64})'")
    if (-not $match.Success) { throw "$name deployment helper integrity pin missing" }
    $value = Read-ReviewedModelDeployment $Python $helper $match.Groups[1].Value
    if ($null -ne $binding -and ($value | ConvertTo-Json -Depth 30 -Compress) -ne ($binding | ConvertTo-Json -Depth 30 -Compress)) {
        throw 'Launchers selected different model deployments'
    }
    $binding = $value
    $rejected = $false
    try { Read-ReviewedModelDeployment $Python $helper ('0'*64) | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw "$name accepted changed helper" }
}
$gatewaySource = Join-Path $VoiceRoot 'Start-QueuedGateway.ps1'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($gatewaySource,[ref]$tokens,[ref]$errors)
foreach ($functionName in @('Test-ExactDeploymentValue','Test-ReviewedGatewayConfig','Test-SameGatewayCredential')) {
    $function = @($ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName},$true))
    if ($function.Count -ne 1) { throw 'Gateway profile consistency guard missing' }
    . ([scriptblock]::Create($function[0].Extent.Text))
}
$selected = Get-Content -LiteralPath $binding.profile -Raw | ConvertFrom-Json
$running = $selected | ConvertTo-Json -Depth 30 | ConvertFrom-Json
$running | Add-Member -NotePropertyName demo_no_thinking_model -NotePropertyValue '' -Force
$running | Add-Member -NotePropertyName queue_limit -NotePropertyValue 8 -Force
$running | Add-Member -NotePropertyName queue_seconds -NotePropertyValue 120 -Force
$running | Add-Member -NotePropertyName console_trace -NotePropertyValue $false -Force
$running | Add-Member -NotePropertyName native_sdk_proxy -NotePropertyValue $true -Force
$goodRunning = $running | ConvertTo-Json -Depth 30
if (-not (Test-ReviewedGatewayConfig $running $selected)) { throw 'Selected gateway profile rejected' }
$running.backend.expected.'version.api' = '0.18.1'
if (Test-ReviewedGatewayConfig $running $selected) { throw 'Stale API health expectation accepted' }
$running = $goodRunning | ConvertFrom-Json
$running.backend.expected.context = 8192
if (Test-ReviewedGatewayConfig $running $selected) { throw 'Wrong context accepted' }
foreach ($field in @('minimum_reserve_gib','concurrency')) {
    $running = $goodRunning | ConvertFrom-Json
    $running.$field = 0
    if (Test-ReviewedGatewayConfig $running $selected) { throw 'Changed gateway safety field accepted' }
}
foreach ($field in @('checkpoint','prefill_chunk','max_prefill_tokens','prompt_cache')) {
    $running = $goodRunning | ConvertFrom-Json
    $running.engine.$field = 'changed'
    if (Test-ReviewedGatewayConfig $running $selected) { throw 'Changed engine controls accepted' }
}
$running = $goodRunning | ConvertFrom-Json
$running.native_sdk_proxy = $false
if (Test-ReviewedGatewayConfig $running $selected) { throw 'Disabled SDK proxy accepted' }
$credentialTestRoot = Join-Path ([IO.Path]::GetTempPath()) ('scc-credential-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $credentialTestRoot | Out-Null
$first = Join-Path $credentialTestRoot 'first.txt'
$second = Join-Path $credentialTestRoot 'second.txt'
Set-Content -LiteralPath $first -Value 'synthetic-test-credential'
Set-Content -LiteralPath $second -Value 'synthetic-test-credential'
$old = [pscustomobject]@{token_file=$first}
$new = [pscustomobject]@{token_file=$second}
if (-not (Test-SameGatewayCredential $old $new $credentialTestRoot $credentialTestRoot)) { throw 'Equal API credential rejected' }
Set-Content -LiteralPath $second -Value 'different-synthetic-test-credential'
if (Test-SameGatewayCredential $old $new $credentialTestRoot $credentialTestRoot) { throw 'Public API credential rotation accepted' }
Write-Output 'Both launchers bind the same pinned profile; stale gateway/changed helper/safety drift/API credential rotation rejected; no service started.'
