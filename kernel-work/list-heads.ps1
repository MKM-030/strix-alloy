# list-heads.ps1 — show available MTP head files and their sizes.
Write-Output '--- unsloth MTP dir ---'
Get-ChildItem 'C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\' -ErrorAction SilentlyContinue |
  ForEach-Object { "{0,-52} {1,7:N2} GB" -f $_.Name, ($_.Length/1GB) }
Write-Output '--- drluoto-frspec dir ---'
Get-ChildItem 'C:\AI\models\qwen38-flash\drluoto-frspec\' -ErrorAction SilentlyContinue |
  ForEach-Object { "{0,-52} {1,7:N2} GB" -f $_.Name, ($_.Length/1GB) }
Write-Output '--- heads staged in kernel-work ---'
Get-ChildItem 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\' -Filter 'mtp*' -ErrorAction SilentlyContinue |
  ForEach-Object { "{0,-52} {1,7:N2} GB" -f $_.Name, ($_.Length/1GB) }
Write-Output '--- top-level qwen38-flash ---'
Get-ChildItem 'C:\AI\models\qwen38-flash\*.gguf' -ErrorAction SilentlyContinue |
  ForEach-Object { "{0,-52} {1,7:N2} GB" -f $_.Name, ($_.Length/1GB) }
