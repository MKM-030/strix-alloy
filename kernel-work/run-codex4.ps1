# run-codex4.ps1 — run Codex with the prompt via argv (worked previously for prompts with metacharacters).
$ErrorActionPreference = 'Continue'
$promptFile = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\codex-prompt-4.md'
$outFile    = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\codex-plan-4.txt'
$dir        = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$prompt     = Get-Content -Raw -LiteralPath $promptFile
Set-Location $dir
& codex exec -s read-only -C $dir --skip-git-repo-check $prompt *> $outFile
"EXIT=$LASTEXITCODE" | Add-Content $outFile
"size: $((Get-Item $outFile).Length)"
