#requires -Version 7.0
[CmdletBinding()]
param([string]$Distribution='Ubuntu-24.04',[string]$LinuxUser,
      [Parameter(Mandatory)][string]$ModelDirectory,[string]$DxgLibrary,[string]$NgramSource,
      [string]$AmdWheel,[ValidateSet('w4b','v2')][string]$Checkpoint='w4b',[switch]$Install,[switch]$VerifyModelHash)
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
& (Get-Command python -ErrorAction Stop).Source @arguments
exit $LASTEXITCODE
