#!/usr/bin/env bash
# scan-history-secrets.sh — scan every blob reachable from the branch that would be pushed.
# Run from the main repo (the linked worktree's .git file holds a Windows-only path).
set -u
BRANCH="${1:-eval/ornith15-20260911}"
cd /mnt/c/Projects/REV-N || exit 1

echo "repo:   $(pwd)"
echo "branch: $BRANCH"
echo "commits reachable: $(git rev-list --count "$BRANCH")"

git rev-list --objects "$BRANCH" | awk '{print $1}' | sort -u > /tmp/blobs.txt
echo "unique objects: $(wc -l < /tmp/blobs.txt)"

HITS=0
SCANNED=0
while read -r obj; do
    [ -n "$obj" ] || continue
    type=$(git cat-file -t "$obj" 2>/dev/null) || continue
    [ "$type" = "blob" ] || continue
    size=$(git cat-file -s "$obj" 2>/dev/null) || continue
    [ "$size" -gt 0 ] && [ "$size" -lt 2000000 ] || continue
    SCANNED=$((SCANNED+1))
    out=$(git cat-file -p "$obj" 2>/dev/null | grep -I -a -n -E \
      '-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{32,}|hf_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_-]{35}' \
      2>/dev/null | head -2)
    if [ -n "$out" ]; then
        HITS=$((HITS+1))
        echo "=== HIT $obj ==="
        echo "$out"
        git rev-list --objects "$BRANCH" | grep "^$obj " | head -1
    fi
done < /tmp/blobs.txt

echo
echo "text blobs scanned: $SCANNED"
echo "blobs with hits:    $HITS"
