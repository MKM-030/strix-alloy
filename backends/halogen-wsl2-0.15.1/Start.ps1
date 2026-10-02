#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('Serve','Trace4k','Single4k','Serve4k')][string]$Profile='Serve',
    [ValidateSet('w4b','v2')][string]$Checkpoint='w4b',
    [ValidateSet('Off','Exact','Flexible')][string]$PromptCache='Off',
    [ValidateRange(4096,262144)][int]$ContextSize=129024,
    [ValidateRange(1,3)][int]$DraftTokens,
    [ValidateSet(2048,4096,8192)][int]$PrefillChunk,
    [ValidateRange(0,604800)][int]$ServeSeconds=0,
    [ValidateRange(120,3600)][int]$StartupTimeoutSeconds=900,
    [switch]$PrintOnly, [switch]$Stop, [switch]$Status, [switch]$Logs
)
$ErrorActionPreference='Stop'
if (@($Stop,$Status,$Logs | Where-Object { $_ }).Count -gt 1) { throw 'Select only one of Stop, Status, Logs.' }
if ($Logs) {
    $state=Get-Content -LiteralPath (Join-Path $PSScriptRoot '.local/current-service.json') -Raw | ConvertFrom-Json
    Get-Content -LiteralPath $state.log_file -Tail 60 -Wait
    exit 0
}
if ($Profile -ne 'Serve') {
    if ($PSBoundParameters.ContainsKey('PrefillChunk') -or $PSBoundParameters.ContainsKey('DraftTokens') -or $PromptCache -ne 'Off' -or $Checkpoint -ne 'w4b' -or $PSBoundParameters.ContainsKey('PromptCache') -or $Stop -or $Status -or $PSBoundParameters.ContainsKey('ContextSize')) {
        throw 'Legacy 4K qualification profiles do not accept service controls or ContextSize.'
    }
    $duration=if($PSBoundParameters.ContainsKey('ServeSeconds')){$ServeSeconds}else{300}
    $arguments=@('-B',(Join-Path $PSScriptRoot 'scripts/runner.py'),'--profile',$Profile,'--serve-seconds',"$duration")
} else {
    $arguments=@('-u','-B',(Join-Path $PSScriptRoot 'scripts/service.py'),
        '--checkpoint',$Checkpoint,'--prompt-cache',$PromptCache,'--context-size',"$ContextSize",'--serve-seconds',"$ServeSeconds",'--startup-timeout',"$StartupTimeoutSeconds")
    if($PSBoundParameters.ContainsKey('DraftTokens')){$arguments+=@('--draft-tokens',"$DraftTokens")}
    if($PSBoundParameters.ContainsKey('PrefillChunk')){$arguments+=@('--prefill-chunk',"$PrefillChunk")}
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
