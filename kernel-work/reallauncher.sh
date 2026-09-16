#!/usr/bin/env bash
# reallauncher.sh — extract the author's gate exports + launcher from the local pwilkin install.
F=/home/revn/pwilkin/install.sh
echo "=== size: $(wc -l < "$F") lines ==="
echo
echo "=== every LLAMA_ line ==="
grep -nE 'LLAMA_[A-Z0-9_]+' "$F"
echo
echo "=== the flash-next launcher block (ctx_size/batch/exec) ==="
grep -nE 'CTX_SIZE|BATCH_SIZE|UBATCH_SIZE|exec |llama-server' "$F" | head -20
