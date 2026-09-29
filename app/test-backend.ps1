#requires -Version 7.0
# Basic local API smoke test, not model quality, streaming or lifecycle qualification.
[CmdletBinding(PositionalBinding=$false)]
param(
    [Parameter(Mandatory)][ValidateSet('Native','Projfix','Halogen','GUFO')]
    [string]$Backend,
    [uri]$ApiBase,
    [ValidateRange(1,120)][int]$TimeoutSeconds = 60
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Backend -eq 'GUFO') {
    [Console]::Error.WriteLine('refused: GUFO persistent service is not qualified by this checkpoint.')
    exit 2
}
$native = $Backend -in @('Native','Projfix')
$model = if ($native) { 'Qwen3.8-Flash-Next' } else { 'halogen-qwen3.8-flash-next' }
if ($null -eq $ApiBase) {
    $ApiBase = [uri]$(if ($native) { 'http://127.0.0.1:8826/v1' } else { 'http://127.0.0.1:8731/v1' })
}
if (-not $ApiBase.IsAbsoluteUri -or $ApiBase.Scheme -ne 'http' -or
    -not $ApiBase.IsLoopback -or $ApiBase.AbsolutePath.TrimEnd('/') -ne '/v1' -or
    $ApiBase.UserInfo -or $ApiBase.Query -or $ApiBase.Fragment) {
    throw 'ApiBase must be loopback HTTP /v1 without credentials, query, or fragment.'
}
$base = $ApiBase.AbsoluteUri.TrimEnd('/')
$listing = Invoke-RestMethod "$base/models" -TimeoutSec $TimeoutSeconds -MaximumRedirection 0 -NoProxy
if ($listing.PSObject.Properties.Name -notcontains 'data' -or $model -cnotin @($listing.data.id)) {
    throw "Expected advertised model '$model' is not ready. Inspect the server logs."
}
$request = @{
    model=$model; messages=@(@{role='user'; content='Reply with exactly: OK'})
    temperature=0; max_tokens=128; stream=$false
}
if ($native) { $request.chat_template_kwargs = @{enable_thinking=$false} }
else { $request.enable_thinking = $false }
$watch = [Diagnostics.Stopwatch]::StartNew()
try {
    $response = Invoke-RestMethod "$base/chat/completions" -Method Post `
        -ContentType 'application/json; charset=utf-8' -Body ($request | ConvertTo-Json -Depth 5) `
        -TimeoutSec $TimeoutSeconds -MaximumRedirection 0 -NoProxy
} finally { $watch.Stop() }
if ($response.PSObject.Properties.Name -notcontains 'choices' -or @($response.choices).Count -eq 0) {
    throw 'No chat choice was returned.'
}
$text = $response.choices[0].message.content
if ($text -isnot [string] -or [string]::IsNullOrWhiteSpace($text)) {
    throw 'No plain final answer text; inspect reasoning limits and server logs.'
}
@{
    result='PASS: basic non-streaming inference only'
    advertised_model=$model; answer=$text; exact_ok=($text.Trim() -ceq 'OK')
    request_seconds=[math]::Round($watch.Elapsed.TotalSeconds,3)
    note='Wall time is not decode speed. Advertised model name is not proof of backend identity.'
} | ConvertTo-Json -Depth 4
