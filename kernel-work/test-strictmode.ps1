Set-StrictMode -Version Latest
Write-Output "--- test 1: [pscustomobject]@{} property enumeration under StrictMode Latest ---"
try {
    $s = [pscustomobject]@{}
    $r = ($s.PSObject.Properties.Name -contains 'OriginalId')
    Write-Output "ok, result=$r"
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
}

Write-Output "--- test 2: PSCustomObject with a property ---"
try {
    $s2 = [pscustomobject]@{ OriginalId = 'x'; TestIds = @() }
    $r2 = ($s2.PSObject.Properties.Name -contains 'OriginalId')
    Write-Output "ok, result=$r2"
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
}

Write-Output "--- test 3: hashtable approach ---"
try {
    $h = @{ OriginalId = $null; TestIds = @() }
    $r3 = $h.ContainsKey('OriginalId')
    Write-Output "ok, result=$r3"
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
}

Write-Output "--- test 4: the Show-State style property access on a DeviceGuard object ---"
try {
    $dg = Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard
    $joined = ($dg.SecurityServicesRunning -join ',')
    Write-Output "ok, SecurityServicesRunning='$joined'"
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
}
