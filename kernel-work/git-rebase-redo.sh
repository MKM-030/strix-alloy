#!/usr/bin/env bash
set -e
cd /home/revn/strix-llama
echo "=== abort half-finished rebase ==="
git rebase --abort 2>/dev/null || true
git status --short | head
echo "=== confirm we are back on win-native ==="
git log --oneline -1
echo "=== redo rebase non-interactively ==="
export GIT_EDITOR=true GIT_SEQUENCE_EDITOR=true
git config user.name 'kernel-work'
git config user.email 'kernel@local'
git rebase --onto origin/strix-halo d67d5883 win-native 2>&1 | tail -25
echo "=== result ==="
git log --oneline -6
echo "=== status ==="
git status --short | head
