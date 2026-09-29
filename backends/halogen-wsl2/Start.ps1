#requires -Version 7.0
param([ValidateSet('Trace32k','Single32k','Single256k','Sessions32k','Serve32k')][string]$Profile='Serve32k',
      [ValidateRange(30,300)][int]$ServeSeconds=300)
$ErrorActionPreference='Stop'
$mode=@{Trace32k='PreflightTrace32k';Single32k='PreflightPinned32k';Single256k='PreflightPinned256k';Sessions32k='PreflightSessions32k';Serve32k='PreflightServe32k'}[$Profile]
& (Join-Path $PSScriptRoot 'tools/qualification/qualify-hybrid48-model.ps1') -Mode $mode -ServeSeconds $ServeSeconds
