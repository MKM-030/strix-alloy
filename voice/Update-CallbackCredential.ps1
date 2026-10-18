param([string]$Config = 'E:\SCC-Voice\bridge.json')
$ErrorActionPreference = 'Stop'
$voiceConfig = Get-Content $Config -Raw | ConvertFrom-Json
$secretPath = $voiceConfig.callback_token_file
if (!(Test-Path -LiteralPath $secretPath -PathType Leaf)) { throw 'Run Configure-Voice.ps1 first.' }
$currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$acl = Get-Acl -LiteralPath $secretPath
if (!$acl.AreAccessRulesProtected) { throw 'Credential file permissions are not protected. Run Configure-Voice.ps1.' }
foreach ($rule in $acl.Access) {
    $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
    if ($sid -notin @($currentSid,'S-1-5-18')) { throw 'Unexpected credential file access. Run Configure-Voice.ps1.' }
}
Write-Host ('Callback user: ' + $voiceConfig.settings.callback_username)
Write-Host 'Enter the EXACT password saved in ServiceNow: SCC Local Voice Callback.'
$secure = Read-Host 'Callback password (hidden; not the inbound token)' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ($plain.Length -lt 24 -or $plain.Contains("`r") -or $plain.Contains("`n")) { throw 'Use the same password of at least 24 characters configured in ServiceNow.' }
    [IO.File]::WriteAllText($secretPath,$plain,[Text.UTF8Encoding]::new($false))
} finally {
    $plain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secure.Dispose()
}
Write-Host 'Callback password saved locally. Tell Codex to resume; the bridge must reload it.'
