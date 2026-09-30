#requires -Version 7.0
# Parse source only. Never invoke a launcher or an installer.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$files = @(
    Get-ChildItem -LiteralPath (Join-Path $root 'app') -Filter '*.ps1' -File
    Get-ChildItem -LiteralPath (Join-Path $root 'backends/halogen-wsl2') -Filter '*.ps1' -File -Recurse
    Get-ChildItem -LiteralPath (Join-Path $root 'backends/halogen-wsl2-0.14.2') -Filter '*.ps1' -File -Recurse | Where-Object { ([IO.Path]::GetRelativePath($root, $_.FullName).Replace([char]92,[char]47)) -notmatch '/[.]local/' }
    Get-ChildItem -LiteralPath (Join-Path $root 'backends/halogen-wsl2-0.15.0') -Filter '*.ps1' -File -Recurse | Where-Object { ([IO.Path]::GetRelativePath($root, $_.FullName).Replace([char]92,[char]47)) -notmatch '/[.]local/' }
    Get-ChildItem -LiteralPath (Join-Path $root 'backends/halogen-wsl2-0.15.1') -Filter '*.ps1' -File -Recurse | Where-Object { ([IO.Path]::GetRelativePath($root, $_.FullName).Replace([char]92,[char]47)) -notmatch '/[.]local/' }
    Get-ChildItem -LiteralPath (Join-Path $root 'server') -Filter '*.ps1' -File
    Get-Item -LiteralPath $PSCommandPath
)
$failures = @()
foreach ($file in $files) {
    $tokens = $null
    $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    foreach ($errorRecord in $errors) { $failures += "$($file.FullName): $errorRecord" }
}
if ($failures.Count) {
    $failures | ForEach-Object { [Console]::Error.WriteLine($_) }
    exit 1
}
Write-Output "PASS: parsed $($files.Count) PowerShell source files; none were executed."
