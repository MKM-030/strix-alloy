param([string]$Source = 'C:\Projects\strix-alloy-scc-voice\voice\Start-NativeModel.ps1')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Launcher parse errors' }
$functions = @($ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-ExactCacheHealth'}, $true))
if ($functions.Count -ne 1) { throw 'Exact cache health guard missing' }
. ([scriptblock]::Create($functions[0].Extent.Text))
$good = [pscustomobject]@{mode=1;enabled=$true;cap_mb=4096;bitwise_identical_to_cold=$true}
if (-not (Test-ExactCacheHealth $good)) { throw 'Healthy Exact rejected' }
$cases = @(
    $null,
    [pscustomobject]@{mode=0;enabled=$false;cap_mb=0;bitwise_identical_to_cold=$true},
    [pscustomobject]@{mode=1;enabled=$false;cap_mb=4096;bitwise_identical_to_cold=$true},
    [pscustomobject]@{mode=1;enabled=$true;cap_mb=0;bitwise_identical_to_cold=$true},
    [pscustomobject]@{mode=1;enabled=$true;cap_mb=4096;bitwise_identical_to_cold=$false},
    [pscustomobject]@{mode='1';enabled=$true;cap_mb=4096;bitwise_identical_to_cold=$true},
    [pscustomobject]@{mode=1;enabled='true';cap_mb=4096;bitwise_identical_to_cold=$true},
    [pscustomobject]@{mode=1;enabled=$true;cap_mb='4096';bitwise_identical_to_cold=$true},
    [pscustomobject]@{mode=1;enabled=$true;cap_mb=4096;bitwise_identical_to_cold=1},
    [pscustomobject]@{mode=1;enabled=$true;cap_mb=4096}
)
foreach ($case in $cases) { if (Test-ExactCacheHealth $case) { throw 'Unsafe/malformed Exact cache accepted' } }
Write-Output 'Exact cache guard: 11 cases passed; launcher parsed; no service started.'
