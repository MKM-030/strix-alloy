# build-strix-alloy-clean.ps1 — rebuild strix-alloy containing ONLY the Qwen3.8-Flash-Next (Strix Halo)
# work. REV-N product code and the ornith/ciru eval material stay in the REV-N repo.
#
# Rule: this repo is the Flash-Next engine + its measurement trail + setup. Nothing else.
$ErrorActionPreference = 'Stop'
$src = 'C:\Projects\REV-N-ornith-eval-20260911'
$dst = 'C:\Projects\strix-alloy-clean'

# ---- 1. Flash-Next benchmark docs: everything EXCEPT docs about other engines/models ----
$excludeDocs = @(
    'ciru-research-and-params-20260912.md',        # ciru engine (different project)
    'ciru-wsl-bringup-20260911.md',                # ciru engine
    'brain-world-engine-combination-matrix-20260912.md', # REV-N world engine
    'ornith-vs-flashnext-throughput-20260911.md',  # ornith eval
    'ornith15-strix-halo-evaluation.md'            # ornith eval
)

if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Path $dst | Out-Null

function Copy-Tree([string]$rel, [string[]]$excludeNames = @()) {
    $s = Join-Path $src $rel
    if (-not (Test-Path -LiteralPath $s)) { Write-Output "SKIP (absent): $rel"; return }
    $files = Get-ChildItem -LiteralPath $s -Recurse -File
    $n = 0
    foreach ($f in $files) {
        if ($excludeNames -contains $f.Name) { continue }
        $r = $f.FullName.Substring($src.Length + 1)
        $t = Join-Path $dst $r
        $td = Split-Path $t -Parent
        if (-not (Test-Path -LiteralPath $td)) { New-Item -ItemType Directory -Path $td -Force | Out-Null }
        Copy-Item -LiteralPath $f.FullName -Destination $t -Force
        $n++
    }
    Write-Output ("copied {0,5} files from {1}" -f $n, $rel)
}

# Flash-Next engine work
Copy-Tree 'kernel-work'
Copy-Tree 'setup'
Copy-Tree 'docs\benchmarks' $excludeDocs

# engine-related scripts only
New-Item -ItemType Directory -Path (Join-Path $dst 'scripts') -Force | Out-Null
Get-ChildItem (Join-Path $src 'scripts') -File | Where-Object { $_.Name -match '^flashnext-' } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dst 'scripts') -Force
    Write-Output ("copied script {0}" -f $_.Name)
}

# the README is written separately (Flash-Next focused)
Write-Output ''
Write-Output '--- result ---'
$all = Get-ChildItem $dst -Recurse -File
Write-Output ("{0} files, {1:N1} MB" -f $all.Count, (($all | Measure-Object Length -Sum).Sum / 1MB))
Get-ChildItem $dst -Directory | Select-Object -ExpandProperty Name | ForEach-Object { "  dir: $_" }
