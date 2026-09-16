# run-codex-plan.ps1 — run Codex with a prompt file, avoiding shell metacharacter parsing.
$ErrorActionPreference = 'Continue'
$promptFile = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\codex-prompt-3.md'
$outFile    = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\codex-plan-20260914.txt'
$dir        = 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work'
$prompt     = Get-Content -Raw -LiteralPath $promptFile
Set-Location $dir
# pipe the prompt on stdin: avoids any argv metacharacter interpretation
$prompt | & codex exec -s read-only -C $dir --skip-git-repo-check - *> $outFile
"EXIT=$LASTEXITCODE" | Add-Content $outFile
