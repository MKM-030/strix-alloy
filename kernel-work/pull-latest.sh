#!/usr/bin/env bash
# pull-latest.sh — save our patches, fetch, and build the latest strix-halo branch.
set -u
cd /home/revn/strix-llama || exit 1

echo "=== 1. commit current work on op-timing ==="
git add -A
git -c user.name=revn -c user.email=revn@local commit -m "session: d2t FR-Spec port + PR28118 on-device spec checkpoints + op timing" 2>&1 | tail -2 || true
git log --oneline -1

echo "=== 2. fetch origin ==="
git fetch origin strix-halo 2>&1 | tail -3

echo "=== 3. new commits available ==="
git log --oneline HEAD..origin/strix-halo | head -15

echo "=== 4. create build branch from origin/strix-halo ==="
git branch -D strix-latest 2>/dev/null || true
git checkout -b strix-latest origin/strix-halo 2>&1 | tail -2
git log --oneline -1
