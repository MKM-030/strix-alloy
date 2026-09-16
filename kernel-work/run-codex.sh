#!/usr/bin/env bash
cd /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
codex exec -s read-only -C /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work --skip-git-repo-check "$(cat codex-prompt.md)" > codex-review-raw-20260913.txt 2>&1
echo "codex exit=$?"
tail -5 codex-review-raw-20260913.txt
