#!/usr/bin/env bash
# run-codex-plan.sh — invoke Codex with the prompt file's contents as ONE argv element.
# Runs inside WSL where the Windows codex exe is reachable via /mnt/c.
cd /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work || exit 1
CODEX=/mnt/c/Users/Marcel/AppData/Roaming/npm/codex
PROMPT="$(cat codex-prompt-3.md)"
"$CODEX" exec -s read-only -C 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work' --skip-git-repo-check -- "$PROMPT" > codex-plan-20260914.txt 2>&1
echo "EXIT=$?" >> codex-plan-20260914.txt
tail -3 codex-plan-20260914.txt
