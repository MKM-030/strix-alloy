#requires -Version 7.0
[CmdletBinding()]
param([string]$Distribution='Ubuntu-24.04',[string]$LinuxUser,
      [Parameter(Mandatory)][string]$ModelDirectory,[string]$DxgLibrary,
      [string]$AmdWheel,[switch]$Install,[switch]$VerifyModelHash)
$ErrorActionPreference='Stop'
$arguments=@('-B',(Join-Path $PSScriptRoot 'scripts/portable.py'),'install',
             '--distro',$Distribution,'--models',$ModelDirectory)
if($LinuxUser){$arguments+=@('--user',$LinuxUser)}
if($DxgLibrary){$arguments+=@('--dxg',$DxgLibrary)}
if($AmdWheel){$arguments+=@('--wheel',$AmdWheel)}
if($Install){$arguments+='--install'}
if($VerifyModelHash){$arguments+='--verify-model-hash'}
& (Get-Command python -ErrorAction Stop).Source @arguments
exit $LASTEXITCODE
