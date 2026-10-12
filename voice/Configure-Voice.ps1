param([switch]$AudioOnly)
$ErrorActionPreference = 'Stop'
$root = 'E:\SCC-Voice'
$secretRoot = Join-Path $root 'secrets'
function Set-PrivateAcl($Path, $Directory) {
  $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
  $systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
  # Change only the DACL; preserve owner and audit rules without SeSecurityPrivilege.
  $acl = Get-Acl -LiteralPath $Path
  $acl.SetAccessRuleProtection($true,$false)
  foreach ($oldRule in @($acl.GetAccessRules($true,$false,[Security.Principal.SecurityIdentifier]))) {
    $acl.RemoveAccessRuleSpecific($oldRule)
  }
  foreach ($identity in @($sid,$systemSid)) {
    if ($Directory) {
      $rule = [Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
    } else { $rule = [Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','Allow') }
    $acl.AddAccessRule($rule)
  }
  if ($Directory) { [IO.Directory]::SetAccessControl($Path,$acl) } else { [IO.File]::SetAccessControl($Path,$acl) }
  $actual = Get-Acl -LiteralPath $Path
  $rules = @($actual.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
  if (!$actual.AreAccessRulesProtected -or $rules.Count -ne 2 -or @($rules | Where-Object {$_.IdentityReference.Value -notin @($sid.Value,$systemSid.Value)}).Count) { throw 'Credential ACL verification failed' }
}
New-Item -ItemType Directory -Path $secretRoot -Force | Out-Null
Set-PrivateAcl $secretRoot $true
foreach ($name in @('servicenow-token.txt','callback-password.txt')) {
  $path = Join-Path $secretRoot $name
  if (Test-Path -LiteralPath $path) { Set-PrivateAcl $path $false }
}
function Save-Secret($prompt, $path) {
  $secure = Read-Host $prompt -AsSecureString
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plain) -or $plain.Length -lt 24) { throw 'Use a secret with at least 24 characters' }
    if (!(Test-Path -LiteralPath $path)) { [IO.File]::WriteAllText($path,'',[Text.UTF8Encoding]::new($false)) }
    Set-PrivateAcl $path $false
    [IO.File]::WriteAllText($path,$plain,[Text.UTF8Encoding]::new($false))
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $plain = $null
  }
}
$settings = [ordered]@{
  service_now_enabled = !$AudioOnly
  user_id = ''
  email = ''
  inbound_id = 'scc-local-voice'
  ui_port = 8850
  callback_port = 8853
  callback_username = 'scc-voice'
  session_seconds = 1800
  turn_seconds = 180
  max_sessions = 1
}
if (!$AudioOnly) {
  Write-Host 'Use the two credentials you have configured in ServiceNow. Nothing is sent to chat.'
  $settings.user_id = Read-Host 'Stable demo user ID (for example scc-demo)'
  $settings.email = Read-Host 'Email of the authorized active ServiceNow demo user'
  if ([string]::IsNullOrWhiteSpace($settings.user_id) -or $settings.email -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw 'A user ID and valid demo email are required' }
  Save-Secret 'ServiceNow inbound static token (hidden)' (Join-Path $secretRoot 'servicenow-token.txt')
  Save-Secret 'ServiceNow callback password for scc-voice (hidden)' (Join-Path $secretRoot 'callback-password.txt')
}
$config = [ordered]@{
  settings = $settings
  servicenow_token_file = (Join-Path $secretRoot 'servicenow-token.txt')
  audio_token_file = 'C:\Projects\strix-alloy-clean\server\.local\servicenow-api-token.txt'
  callback_token_file = (Join-Path $secretRoot 'callback-password.txt')
}
[IO.File]::WriteAllText((Join-Path $root 'bridge.json'),($config | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
Write-Host 'Configuration saved. Start with .\Start-Voice.ps1 -Action Start.'
