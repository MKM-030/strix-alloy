# contention-check.ps1 — is something else on the GPU / is the box being shared?
"=== llama-server procs ==="
Get-Process llama-server -ErrorAction SilentlyContinue | ForEach-Object { 'pid {0}  WS {1:N1} GB  CPU {2:N0}s  start {3}' -f $_.Id, ($_.WorkingSet64/1GB), $_.CPU, $_.StartTime }
"=== all processes >300MB ==="
Get-Process | Where-Object { $_.WorkingSet64 -gt 300MB } | Sort-Object WorkingSet64 -Descending |
  ForEach-Object { '{0,-22} pid {1,-7} {2,7:N2} GB' -f $_.Name, $_.Id, ($_.WorkingSet64/1GB) }
"=== memory ==="
$os = Get-CimInstance Win32_OperatingSystem
"total {0:N1} GB  free {1:N1} GB" -f ($os.TotalVisibleMemorySize/1MB), ($os.FreePhysicalMemory/1MB)
"=== device pool ==="
& 'C:\AI\runtimes\strix-vulkan-ba5354d\llama-server.exe' --list-devices 2>&1 | Select-Object -Last 1
"=== uptime ==="
(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
