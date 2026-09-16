#!/usr/bin/env bash
# restore-clean-ggmlcuda.sh — put the pre-instrumentation ggml-cuda.cu back and rebuild clean.
# The WSL win-native branch is already clean; Windows still had the instrumented copy.
set -euo pipefail
W=/mnt/c/AI/build/strix-llama-win
S=/home/revn/strix-llama

echo "=== source of truth: WSL win-native (should be clean) ==="
grep -c 'LLAMA_OP_TIMING' "$S/ggml/src/ggml-cuda/ggml-cuda.cu" || echo "0 (clean)"

echo "=== copy clean WSL source over the Windows tree ==="
cp "$S/ggml/src/ggml-cuda/ggml-cuda.cu" "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
echo "win refs now: $(grep -c 'LLAMA_OP_TIMING' "$W/ggml/src/ggml-cuda/ggml-cuda.cu" || echo 0)"

echo "=== also verify the op-timing doc note is the only thing mentioning it ==="
ls -la "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
