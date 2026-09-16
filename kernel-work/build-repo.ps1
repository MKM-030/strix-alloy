# build-repo.ps1 — materialise the publishable repo from the worktree's tracked + untracked-but-not-ignored
# files into a FRESH git history (no inherited commits, so nothing from product history can leak).
$ErrorActionPreference = 'Stop'
$src = 'C:\Projects\REV-N-ornith-eval-20260911'
$dst = 'C:\Projects\tungsten'
$list = Join-Path $src 'kernel-work\repo-filelist.txt'

if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Path $dst | Out-Null

$files = Get-Content $list | Where-Object { $_ -and $_.Trim() -ne '' -and $_ -notmatch 'repo-filelist\.txt$' }
$copied = 0; $bytes = 0; $failed = @(); $skipped = @()
foreach ($rel in $files) {
    $rel = $rel.Trim()
    # BCD export artifacts (bcdedit /export writes *.LOG1/*.LOG2 with a trailing dot) plus zero-byte
    # scratch: junk, not repo content.
    if ($rel -match 'bcd-backup-.*\.LOG[12]$' -or $rel -match '\\iq4nl-parse\.err$' -or $rel -match 'lbench-help\.txt$') { $skipped += $rel; continue }
    $s = Join-Path $src $rel
    $item = Get-Item -LiteralPath $s -ErrorAction SilentlyContinue
    if (-not $item) { $failed += $rel; continue }
    $d = Join-Path $dst $rel
    $dd = Split-Path $d -Parent
    if (-not (Test-Path -LiteralPath $dd)) { New-Item -ItemType Directory -Path $dd -Force | Out-Null }
    try {
        Copy-Item -LiteralPath $s -Destination $d -Force -ErrorAction Stop
        $copied++
        $bytes += $item.Length
    } catch { $failed += $rel }
}
Write-Output ("copied {0} files, {1:N1} MB" -f $copied, ($bytes/1MB))
Write-Output ("skipped junk: {0}" -f $skipped.Count)
if ($failed.Count) { Write-Output ("FAILED ({0}):" -f $failed.Count); $failed | Select-Object -First 10 | ForEach-Object { "  $_" } }
