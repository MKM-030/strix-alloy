#!/usr/bin/env bash
set -e
cd /home/revn/strix-llama
echo "=== backup current win-native ==="
git branch -f win-native-backup-20260915 HEAD
git log --oneline -1 win-native-backup-20260915
echo "=== rebase our commits onto origin/strix-halo (40a9f4d0) ==="
git rebase --onto origin/strix-halo d67d5883 win-native 2>&1 | tail -30 || {
  echo "!!! REBASE CONFLICT -- listing ==="
  git status --short
  exit 1
}
echo "=== result ==="
git log --oneline -6
