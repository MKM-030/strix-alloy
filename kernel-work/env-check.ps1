# env-check.ps1 — disk space, ROCm installs, existing TheRock artifacts.
$d = Get-PSDrive C
"Disk C free: {0:N1} GB" -f ($d.Free/1GB)
"--- ROCm for Windows installs ---"
Get-ChildItem 'C:\Program Files\AMD\ROCm' -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }
"--- ROCm 7.2 clang version ---"
& 'C:\Program Files\AMD\ROCm\7.2\bin\clang.exe' --version 2>&1 | Select-Object -First 1
"--- any gfx1151 SDK tarballs / TheRock on disk ---"
Get-ChildItem 'C:\AI' -Recurse -Depth 3 -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match 'therock|gfx1151.*tar|rocm.*windows' } |
  Select-Object -First 8 -ExpandProperty FullName
"--- WSL-side models we might copy to Windows ---"
if (Test-Path '\\wsl.localhost\Ubuntu-24.04\home\revn\models\flash-next-strix') {
  Get-ChildItem '\\wsl.localhost\Ubuntu-24.04\home\revn\models\flash-next-strix' -Filter '*.gguf' -ErrorAction SilentlyContinue |
    ForEach-Object { "{0,-58} {1,7:N1} GB" -f $_.Name, ($_.Length/1GB) }
}
