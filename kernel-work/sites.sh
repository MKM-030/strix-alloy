#!/usr/bin/env bash
# sites.sh — show all spec-checkpoint call sites with context, to classify tgt/dft.
F=/home/revn/strix-llama/tools/server/server-context.cpp
grep -n 'LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY' "$F" | while IFS=: read -r ln rest; do
  echo "===== line $ln ====="
  sed -n "$((ln-6)),$((ln+2))p" "$F"
done
