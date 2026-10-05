#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('Serve','Trace4k','Single4k','Serve4k')][string]$Profile='Serve',
    [ValidateSet('w4b','v2')][string]$Checkpoint='w4b',
    [ValidateSet('Off','Exact','Flexible')][string]$PromptCache='Off',
    [ValidateRange(4096,262144)][int]$ContextSize=129024,
    [ValidateRange(1,3)][int]$DraftTokens,
    [ValidateSet(2048,4096,8192,16384,32768)][int]$PrefillChunk,
    [ValidateSet(2048,4096,8192,16384,32768)][int]$MaxPrefillTokens,
    [switch]$PrefillKeepTrunk, [ValidateRange(1,1024)][int]$AdmitTicks,
    [string]$KernelControlsJson, [string]$MatmulTuningJson, [string]$SpeculationPolicyJson,
    [string]$LookupReceipt, [string]$LookupReceiptSha256,
    [string]$PrivateHsaReceipt, [string]$PrivateHsaReceiptSha256,
    [ValidateRange(0,604800)][int]$ServeSeconds=0,
    [ValidateRange(120,3600)][int]$StartupTimeoutSeconds=900,
    [switch]$PrintOnly, [switch]$Stop, [switch]$Status, [switch]$Logs
)
$ErrorActionPreference='Stop'
if ($PSBoundParameters.ContainsKey('LookupReceipt') -ne $PSBoundParameters.ContainsKey('LookupReceiptSha256')) { throw 'LookupReceipt and LookupReceiptSha256 must be supplied together.' }
if ($PSBoundParameters.ContainsKey('LookupReceipt') -and ($Profile -ne 'Serve' -or $Checkpoint -ne 'v2')) { throw 'Standalone lookup experiments require Serve with the v2 checkpoint.' }
if ($PSBoundParameters.ContainsKey('PrivateHsaReceipt') -ne $PSBoundParameters.ContainsKey('PrivateHsaReceiptSha256')) { throw 'PrivateHsaReceipt and PrivateHsaReceiptSha256 must be supplied together.' }
if ($PSBoundParameters.ContainsKey('PrivateHsaReceipt') -and ($Profile -ne 'Serve' -or $Checkpoint -ne 'v2')) { throw 'Private HSA experiments require Serve with the v2 checkpoint.' }
if (@($Stop,$Status,$Logs | Where-Object { $_ }).Count -gt 1) { throw 'Select only one of Stop, Status, Logs.' }
if ($Logs) {
    $state=Get-Content -LiteralPath (Join-Path $PSScriptRoot '.local/current-service.json') -Raw | ConvertFrom-Json
    Get-Content -LiteralPath $state.log_file -Tail 60 -Wait
    exit 0
}
if ($Profile -ne 'Serve') {
    if ($PSBoundParameters.ContainsKey('SpeculationPolicyJson') -or $PSBoundParameters.ContainsKey('MatmulTuningJson') -or $PSBoundParameters.ContainsKey('KernelControlsJson') -or $PSBoundParameters.ContainsKey('PrefillChunk') -or $PSBoundParameters.ContainsKey('MaxPrefillTokens') -or $PrefillKeepTrunk -or $PSBoundParameters.ContainsKey('AdmitTicks') -or $PSBoundParameters.ContainsKey('DraftTokens') -or $PromptCache -ne 'Off' -or $Checkpoint -ne 'w4b' -or $PSBoundParameters.ContainsKey('PromptCache') -or $Stop -or $Status -or $PSBoundParameters.ContainsKey('ContextSize')) {
        throw 'Legacy 4K qualification profiles do not accept service controls or ContextSize.'
    }
    $duration=if($PSBoundParameters.ContainsKey('ServeSeconds')){$ServeSeconds}else{300}
    $arguments=@('-B',(Join-Path $PSScriptRoot 'scripts/runner.py'),'--profile',$Profile,'--serve-seconds',"$duration")
} else {
    $arguments=@('-u','-B',(Join-Path $PSScriptRoot 'scripts/service.py'),
        '--checkpoint',$Checkpoint,'--prompt-cache',$PromptCache,'--context-size',"$ContextSize",'--serve-seconds',"$ServeSeconds",'--startup-timeout',"$StartupTimeoutSeconds")
    if($PSBoundParameters.ContainsKey('DraftTokens')){$arguments+=@('--draft-tokens',"$DraftTokens")}
    if($PSBoundParameters.ContainsKey('PrefillChunk')){$arguments+=@('--prefill-chunk',"$PrefillChunk")}
    if($PSBoundParameters.ContainsKey('MaxPrefillTokens')){$arguments+=@('--max-prefill-tokens',"$MaxPrefillTokens")}
    if($PrefillKeepTrunk){$arguments+='--prefill-keep-trunk'}
    if($PSBoundParameters.ContainsKey('AdmitTicks')){$arguments+=@('--admit-ticks',"$AdmitTicks")}
    if($PSBoundParameters.ContainsKey('KernelControlsJson')){$arguments+=@('--kernel-controls-json',$KernelControlsJson)}
    if($PSBoundParameters.ContainsKey('MatmulTuningJson')){$arguments+=@('--matmul-tuning-json',$MatmulTuningJson)}
    if($PSBoundParameters.ContainsKey('SpeculationPolicyJson')){$arguments+=@('--speculation-policy-json',$SpeculationPolicyJson)}
    if($PSBoundParameters.ContainsKey('LookupReceipt')){$arguments+=@('--lookup-receipt',$LookupReceipt,'--lookup-receipt-sha256',$LookupReceiptSha256)}
    if($PSBoundParameters.ContainsKey('PrivateHsaReceipt')){$arguments+=@('--private-hsa-receipt',$PrivateHsaReceipt,'--private-hsa-receipt-sha256',$PrivateHsaReceiptSha256)}
    if($Stop){$arguments+='--stop'}
    if($Status){$arguments+='--status'}
}
if($PrintOnly){$arguments+='--print-only'}
$pythonExecutable = (Get-Command python -ErrorAction Stop).Source
$originalPath = $env:PATH
try {
    $machineFile = Join-Path $PSScriptRoot '.local/machine.json'
    if (Test-Path -LiteralPath $machineFile -PathType Leaf) {
        $machine = Get-Content -LiteralPath $machineFile -Raw | ConvertFrom-Json
        $recordedDirectory = Split-Path -Parent $machine.pwsh
        $env:PATH = $recordedDirectory + [IO.Path]::PathSeparator + $originalPath
    }
    & $pythonExecutable @arguments
    $code = $LASTEXITCODE
} finally { $env:PATH = $originalPath }
exit $code
