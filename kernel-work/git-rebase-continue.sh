#!/usr/bin/env bash
set -e
cd /home/revn/strix-llama
git config user.name 'kernel-work'
git config user.email 'kernel@local'
echo "=== rebase status before ==="
git status --short | head
echo "=== continue ==="
GIT_EDITOR=true git rebase --continue 2>&1 | tail -20 || {
  echo "!!! still conflicting ==="
  git status --short | head -30
  exit 1
}
# handle further steps
while [ -d .git/rebase-merge ]; do
  GIT_EDITOR=true git rebase --continue 2>&1 | tail -5 || { git status --short | head -30; exit 1; }
done
echo "=== result ==="
git log --oneline -6
