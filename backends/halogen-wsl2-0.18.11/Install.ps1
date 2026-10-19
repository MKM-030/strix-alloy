#requires -Version 5.1
[CmdletBinding()]
param([string]$Distribution='Ubuntu-24.04',[string]$LinuxUser,
      [Parameter(Mandatory)][string]$ModelDirectory,[string]$DxgLibrary,[string]$NgramSource,
      [string]$AmdWheel,[ValidateSet('w4b','v2')][string]$Checkpoint='v2',[switch]$Install,[switch]$VerifyModelHash)
$ErrorActionPreference='Stop'
$arguments=@('-B',(Join-Path $PSScriptRoot 'scripts/portable.py'),'install',
             '--distro',$Distribution,'--models',$ModelDirectory)
if($LinuxUser){$arguments+=@('--user',$LinuxUser)}
if($DxgLibrary){$arguments+=@('--dxg',$DxgLibrary)}
if($NgramSource){$arguments+=@('--ngram-source',$NgramSource)}
if($AmdWheel){$arguments+=@('--wheel',$AmdWheel)}
$arguments+=@('--checkpoint',$Checkpoint)
if($Install){$arguments+='--install'}
if($VerifyModelHash){$arguments+='--verify-model-hash'}
$nativePowerShell=Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
$originalPowerShellHost=$env:ALLOY_POWERSHELL_HOST
try {
    $env:ALLOY_POWERSHELL_HOST=$nativePowerShell
    & (Get-Command python -ErrorAction Stop).Source @arguments
    $code=$LASTEXITCODE
} finally { $env:ALLOY_POWERSHELL_HOST=$originalPowerShellHost }
exit $code
