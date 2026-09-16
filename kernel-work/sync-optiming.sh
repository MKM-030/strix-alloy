#!/usr/bin/env bash
# sync-optiming.sh — copy the op-timing ggml-cuda.cu into the Windows build tree.
set -euo pipefail
SRC=/home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu
DST=/mnt/c/AI/build/strix-llama-win/ggml/src/ggml-cuda/ggml-cuda.cu
echo "=== sanity on source ==="
echo "LLAMA_OP_TIMING refs: $(grep -c LLAMA_OP_TIMING "$SRC")"
echo "op_timing_ig present: $(grep -c 'namespace op_timing_ig' "$SRC")"
echo "=== back up + install ==="
cp "$DST" "$DST.bak-$(date +%s)"
cp "$SRC" "$DST"
echo "installed refs: $(grep -c LLAMA_OP_TIMING "$DST")"
echo done
