param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $destination) { throw 'Output directory already exists' }
$probe = Join-Path $PSScriptRoot 'windows_probe.ps1'
$counters = Join-Path $PSScriptRoot 'windows_counters.cs'
$entry = Join-Path $PSScriptRoot 'windows_probe_main.cs'
$inputPaths = @($probe, $counters, $entry, $PSCommandPath)
$before = @($inputPaths | ForEach-Object {
    [pscustomobject]@{path=$_; sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash}
})
$probeText = Get-Content -Raw -LiteralPath $probe
$matches = [regex]::Matches($probeText, "(?ms)^\`$source = @'\r?\n(?<source>.*?)\r?\n'@\r?`$")
if ($matches.Count -ne 1) { throw 'Expected exactly one literal DXGI source block' }
$framework = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319'
$compiler = Join-Path $framework 'csc.exe'
$web = Join-Path $framework 'System.Web.Extensions.dll'
foreach ($path in @($compiler, $web)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Framework compiler/reference missing' }
}
New-Item -ItemType Directory -Path $destination | Out-Null
$generated = Join-Path $destination 'dxgi-extracted.cs'
# Mechanical build intermediate extracted verbatim from the existing probe.
[IO.File]::WriteAllText($generated, $matches[0].Groups['source'].Value, [Text.UTF8Encoding]::new($false))
$executable = Join-Path $destination 'gufo-memory-probe.exe'
& $compiler /nologo /target:exe /platform:x64 /optimize+ /checked- "/reference:$web" "/out:$executable" $generated $counters $entry
if ($LASTEXITCODE -ne 0) { throw 'Probe compiler failed' }
foreach ($record in $before) {
    if ((Get-FileHash -LiteralPath $record.path -Algorithm SHA256).Hash -ne $record.sha256) {
        throw 'Probe source changed during compilation'
    }
}
$manifest = [ordered]@{
    purpose='Read-only native telemetry; not inference or model qualification'
    sources=$before
    extractedDxgiSha256=(Get-FileHash -LiteralPath $generated -Algorithm SHA256).Hash
    compiler=[ordered]@{path=$compiler; sha256=(Get-FileHash -LiteralPath $compiler -Algorithm SHA256).Hash}
    reference=[ordered]@{path=$web; sha256=(Get-FileHash -LiteralPath $web -Algorithm SHA256).Hash}
    executable=[ordered]@{path=$executable; sha256=(Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash}
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $destination 'build-manifest.json') -Encoding UTF8
$manifest | ConvertTo-Json -Depth 6
