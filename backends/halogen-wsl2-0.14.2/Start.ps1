#requires -Version 7.0
[CmdletBinding()]
param([ValidateSet('Trace4k','Single4k','Serve4k')][string]$Profile='Single4k',
      [ValidateRange(30,300)][int]$ServeSeconds=300,[switch]$PrintOnly)
$ErrorActionPreference='Stop'
$arguments=@('-B',(Join-Path $PSScriptRoot 'scripts/runner.py'),
             '--profile',$Profile,'--serve-seconds',([string]$ServeSeconds))
if($PrintOnly){$arguments+='--print-only'}
& (Get-Command python -ErrorAction Stop).Source @arguments
exit $LASTEXITCODE
