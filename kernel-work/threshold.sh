#!/usr/bin/env bash
# threshold.sh — find the 2048 cliff in the code.
cd /home/revn/strix-llama || exit 1
echo "=== remaining QSA/MTP env gates (d67d5883) ==="
grep -rhoE 'LLAMA_(QSA|MTP)_[A-Z0-9_]+' ggml/src/ggml-cuda/ src/ 2>/dev/null | sort -u
echo
echo "=== where indexer_top_k / selection width gates the draft path ==="
grep -rn 'indexer_top_k' src/models/qwen4exp.cpp src/llama-memory-hybrid-idx.cpp 2>/dev/null | head -10
echo
echo "=== sparse_decode conditional (from qwen4exp.cpp) ==="
grep -n 'sparse_decode' src/models/qwen4exp.cpp | head -12
