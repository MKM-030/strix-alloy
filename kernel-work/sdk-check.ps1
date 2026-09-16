# sdk-check.ps1 — verify the TheRock Windows gfx1151 SDK: clang version and tool paths.
$sdk = 'C:\AI\sdk\therock1151'
Write-Output "=== top level ==="
Get-ChildItem $sdk | Select-Object -ExpandProperty Name
Write-Output "=== clang / clang++ candidates ==="
Get-ChildItem $sdk -Recurse -Filter 'clang*.exe' -ErrorAction SilentlyContinue | Select-Object -First 8 -ExpandProperty FullName
Write-Output "=== hipcc ==="
Get-ChildItem $sdk -Recurse -Filter 'hipcc*' -ErrorAction SilentlyContinue | Select-Object -First 5 -ExpandProperty FullName
Write-Output "=== version ==="
$clang = Get-ChildItem $sdk -Recurse -Filter 'clang.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($clang) { & $clang.FullName --version 2>&1 | Select-Object -First 2 }
Write-Output "=== amdgcn bitcode (device libs) ==="
Get-ChildItem $sdk -Recurse -Directory -Filter 'amdgcn' -ErrorAction SilentlyContinue | Select-Object -First 3 -ExpandProperty FullName
