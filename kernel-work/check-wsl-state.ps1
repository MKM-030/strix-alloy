$v = Get-Process vmmemWSL -ErrorAction SilentlyContinue
if ($v) { Write-Output ("vmmemWSL still present: {0} MB" -f [int]($v.WorkingSet64/1MB)) }
else    { Write-Output 'vmmemWSL gone - WSL is down' }
$os = Get-CimInstance Win32_OperatingSystem
Write-Output ("host free {0:N1} GB / total {1:N1} GB" -f ($os.FreePhysicalMemory/1MB), ($os.TotalVisibleMemorySize/1MB))
Write-Output "HypervisorPresent = $((Get-CimInstance Win32_ComputerSystem).HypervisorPresent)"
foreach ($n in @('wslservice','vmcompute')) {
    $s = Get-Service -Name $n -ErrorAction SilentlyContinue
    if ($s) { Write-Output ("  {0}: {1}" -f $s.Name, $s.Status) }
}
