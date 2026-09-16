Write-Output "--- test A: direct call with {current} ---"
$o1 = & bcdedit.exe /enum "{current}" 2>&1 | Out-String
Write-Output ("exit=" + $LASTEXITCODE)
Write-Output $o1.Trim()

Write-Output ""
Write-Output "--- test B: via cmd.exe /c (braces passed verbatim) ---"
$o2 = & cmd.exe /c 'bcdedit /enum {current}' 2>&1 | Out-String
Write-Output ("exit=" + $LASTEXITCODE)
Write-Output $o2.Trim()

Write-Output ""
Write-Output "--- test C: bare /enum (all entries) ---"
$o3 = & bcdedit.exe /enum 2>&1 | Out-String
Write-Output ("exit=" + $LASTEXITCODE)
Write-Output ($o3.Trim().Substring(0, [Math]::Min(600, $o3.Trim().Length)))
