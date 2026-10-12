$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$failures = 0
function Load-Function($file, $name) {
  $tokens = $null; $errors = $null
  $ast = [Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors)
  $fn = $ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
  if (!$fn) { throw ('Missing function: ' + $name) }
  return $fn.Extent.Text
}
try {
  . ([scriptblock]::Create((Load-Function (Join-Path $root 'Start-Voice.ps1') 'Get-OwnedProcesses')))
  $service = @{Name='asr';Script=(Join-Path $root 'audio_service.py')}
  $script:fixtures = @(
    @{ProcessId=1;CommandLine=('python -u "' + $service.Script + '" "--mode" "asr" "--port" "8851"')},
    @{ProcessId=2;CommandLine=('python -u ' + $service.Script + ' --mode asr --port 8851')},
    @{ProcessId=3;CommandLine=('python -u "' + $service.Script + '" "--mode" "tts"')},
    @{ProcessId=4;CommandLine=('python -u "' + $service.Script + '.other" --mode asr')}
  )
  function Get-CimInstance { param($ClassName,$Filter) $script:fixtures }
  $ids = @((Get-OwnedProcesses $service) | ForEach-Object {$_.ProcessId})
  if (($ids -join ',') -ne '1,2') { throw ('Wrong owned PIDs: ' + ($ids -join ',')) }
  Write-Host 'PASS quoted/unquoted ownership and foreign-process exclusion'
} catch { $failures++; Write-Host ('FAIL ownership: ' + $_.Exception.Message) }
try {
  . ([scriptblock]::Create((Load-Function (Join-Path $root 'Configure-Voice.ps1') 'Set-PrivateAcl')))
  $testDir = Join-Path $env:TEMP ('scc-acl-test-' + [guid]::NewGuid())
  New-Item -ItemType Directory $testDir | Out-Null
  $testFile = Join-Path $testDir 'dummy.txt'
  [IO.File]::WriteAllText($testFile,'not-a-secret')
  $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
  foreach ($item in @($testDir,$testFile)) {
    $acl = Get-Acl $item
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-5-32-545'),'Read','Allow'))
    Set-Acl -LiteralPath $item -AclObject $acl
    Set-PrivateAcl $item (Test-Path -LiteralPath $item -PathType Container)
    $result = Get-Acl $item
    $rules = @($result.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
    if (!$result.AreAccessRulesProtected -or $rules.Count -ne 2 -or @($rules | Where-Object {$_.IdentityReference.Value -notin @($sid,'S-1-5-18')}).Count) { throw 'Unexpected access rule survived' }
  }
  Remove-Item -LiteralPath $testFile
  Remove-Item -LiteralPath $testDir
  Write-Host 'PASS directory/file ACL replaces pre-existing explicit access'
} catch { $failures++; Write-Host ('FAIL ACL: ' + $_.Exception.Message) }
if ($failures) { exit 1 }
