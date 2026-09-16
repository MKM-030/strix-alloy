# state-64.ps1 — verify the 64 GB carve: Windows RAM, device pool, and whether the model is loadable.
$os = Get-CimInstance Win32_OperatingSystem
"Windows total : {0:N1} GB" -f ($os.TotalVisibleMemorySize/1MB)
"Windows free  : {0:N1} GB" -f ($os.FreePhysicalMemory/1MB)
"--- device pool ---"
& 'C:\AI\runtimes\strix-vulkan-ba5354d\llama-server.exe' --list-devices 2>&1 | Select-Object -Last 1
"--- what is holding RAM ---"
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 6 |
  ForEach-Object { "{0,-16} {1,7:N2} GB" -f $_.Name, ($_.WorkingSet64/1GB) }
"--- WSL state ---"
wsl -l --running
