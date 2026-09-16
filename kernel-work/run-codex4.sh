#!/usr/bin/env bash
# run-codex4.sh — pass the whole prompt as ONE argv element after -- (the form that worked for plan 3).
cd /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work || exit 1
CODEX=/mnt/c/Users/Marcel/AppData/Roaming/npm/codex
PROMPT="$(cat codex-prompt-4.md)"
"$CODEX" exec -s read-only \
  -C 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work' \
  --skip-git-repo-check -- "$PROMPT" > codex-plan-4.txt 2>&1
echo "EXIT=$?" >> codex-plan-4.txt
tail -3 codex-plan-4.txt
