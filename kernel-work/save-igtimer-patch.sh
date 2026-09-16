#!/usr/bin/env bash
set -e
cd /home/revn/strix-llama
OUT=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/op-timing-igtimer-diagnosed.patch
git stash show -p 'stash@{0}' > "$OUT"
echo "patch bytes: $(wc -c < "$OUT")"
echo "--- win-native working tree (empty = clean) ---"
git status --short
echo "--- op-timing refs on win-native (expect 0) ---"
grep -c 'LLAMA_OP_TIMING' ggml/src/ggml-cuda/ggml-cuda.cu || true
echo "--- stash list ---"
git stash list
