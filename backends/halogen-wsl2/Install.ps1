#requires -Version 7.0
param([switch]$Install, [string]$Distribution='Ubuntu-24.04', [string]$LinuxUser,
      [Parameter(Mandatory)][string]$ModelDirectory, [string]$DxgLibrary,
      [string]$AmdWheel, [switch]$VerifyModelHash)
$ErrorActionPreference='Stop'
$python=(Get-Command python -ErrorAction Stop).Source
$arguments=@('-B',(Join-Path $PSScriptRoot 'scripts/package.py'),'install','--distro',$Distribution,'--models',$ModelDirectory)
if($LinuxUser){$arguments+=@('--user',$LinuxUser)}
if($DxgLibrary){$arguments+=@('--dxg',$DxgLibrary)}
if($AmdWheel){$arguments+=@('--wheel',$AmdWheel)}
if($Install){$arguments+='--install'}
if($VerifyModelHash){$arguments+='--verify-model-hash'}
& $python @arguments
if($LASTEXITCODE -ne 0){throw 'Package preflight or installation failed; see the message above.'}
