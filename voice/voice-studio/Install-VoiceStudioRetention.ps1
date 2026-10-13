[CmdletBinding()]
param([switch]$InspectOnly)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $project 'voice\native-bridge\.venv\Scripts\python.exe'
$cleanup = Join-Path $PSScriptRoot 'retention_cleanup.py'
$policy = Join-Path $PSScriptRoot 'retention-policy.json'
foreach ($file in @($python, $cleanup, $policy)) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw 'Retention-Datei oder Python fehlt.' }
}
$config = Get-Content -LiteralPath $policy -Raw | ConvertFrom-Json
if ($config.schema_version -ne 1 -or $config.due_at_utc -ne '2026-10-16T06:00:00Z' -or
    $config.timezone -ne 'Europe/Berlin' -or $config.keep_access_codes -ne $true) {
    throw 'Die Retention-Policy entspricht nicht der geprueften Messekonfiguration.'
}
$name = 'SCC Voice Studio - Messeaufnahmen entfernen'
$description = 'SCC Voice Studio: nur lokale Messe-Aufnahmekopien ab 16.10.2026 08:00 Europe/Berlin entfernen; aktive Gespraeche aufschieben; keine Prozesse stoppen.'
$arguments = '-u "' + $cleanup + '" --apply'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function Get-PrincipalSid([string]$identity) {
    if ($identity -match '^S-1-') { return $identity }
    return (New-Object Security.Principal.NTAccount($identity)).Translate([Security.Principal.SecurityIdentifier]).Value
}
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Description -ne $description -or $existing.Actions.Count -ne 1 -or
        $existing.Actions[0].Execute -ne $python -or $existing.Actions[0].Arguments -ne $arguments -or
        (Get-PrincipalSid $existing.Principal.UserId) -ne $sid -or $existing.Principal.RunLevel -ne 'Limited') {
        throw 'Ein anderer Task verwendet diesen Namen. Er wurde nicht veraendert.'
    }
}
if ($InspectOnly) {
    [pscustomobject]@{TaskName=$name; Exists=[bool]$existing; DueUTC=$config.due_at_utc; Execute=$python; Arguments=$arguments}
    return
}
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $project
$daily = New-ScheduledTaskTrigger -Daily -At '08:00'
$daily.StartBoundary = '2026-10-16T08:00:00+02:00'
$logon = New-ScheduledTaskTrigger -AtLogOn -User $sid
$principal = New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
$task = New-ScheduledTask -Action $action -Trigger @($daily, $logon) -Principal $principal -Settings $settings -Description $description
Register-ScheduledTask -TaskName $name -InputObject $task -Force | Out-Null
$installed = Get-ScheduledTask -TaskName $name
if ($installed.Actions[0].Execute -ne $python -or $installed.Actions[0].Arguments -ne $arguments -or
    (Get-PrincipalSid $installed.Principal.UserId) -ne $sid -or $installed.Principal.LogonType -ne 'Interactive' -or
    $installed.Principal.RunLevel -ne 'Limited') {
    throw 'Task-Verifikation fehlgeschlagen. Es wurde keine Bereinigung gestartet.'
}
Write-Host ('Retention-Task eingerichtet: ' + $name)
Write-Host 'Fruehestens 16.10.2026 08:00 Berlin; taeglicher Aufholversuch und bei Anmeldung.'
