param([Parameter(Mandatory=$true)][string]$Launcher)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Launcher,[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors|Out-String)}
$raw=Get-Content -LiteralPath $Launcher -Raw
$HistoricalProfileHash=[regex]::Match($raw,"\`$HistoricalProfileHash = '([0-9a-f]{64})'").Groups[1].Value
$ProfileHash=[regex]::Match($raw,"\`$ProfileHash = '([0-9a-f]{64})'").Groups[1].Value
if($HistoricalProfileHash -ne 'f62b654bd0cfd0bcd00b4ced7416b64584ca530e6be8120e5d61dc45b931c323' -or
   $ProfileHash -ne 'f1076479e51c4c8597ee8b90924748cce053e1dba85aa5e5169c650720e426cb'){throw 'Unexpected profile pins'}
$definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-KnownHistoricalController'},$true)
if($null -eq $definition){throw 'Historical profile guard missing'}
# Execute only the reviewed pure predicate, never the launcher or process functions.
Invoke-Expression $definition.Extent.Text
$old=[pscustomobject]@{phase='failed';run_id='ac678e51cef84d819a8fd276dcb93271';profile_sha256=$HistoricalProfileHash}
if(-not (Test-KnownHistoricalController $old)){throw 'Exact historical profile rejected'}
$new=[pscustomobject]@{phase='failed';run_id=$old.run_id;profile_sha256=$ProfileHash}
if(Test-KnownHistoricalController $new){throw 'New text profile accepted as historical incident'}
$old.phase='ready';if(Test-KnownHistoricalController $old){throw 'Live controller accepted'}
$old.phase='failed';$old.run_id='00000000000000000000000000000000';if(Test-KnownHistoricalController $old){throw 'Different run accepted'}
if(Test-KnownHistoricalController $null){throw 'Absent state accepted'}
Write-Output 'Historical profile predicate: 5 cases PASS; new text profile cannot qualify as historical incident. PowerShell parse PASS.'
