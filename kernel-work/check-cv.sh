#!/usr/bin/env bash
F=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/cv.err
echo "=== cv.err size ==="
wc -c "$F" 2>/dev/null || echo missing
echo
echo "=== OP_TIMING / graph / disable lines ==="
grep -aiE 'OP_TIMING|graph|DISABLE' "$F" | head -15
echo
echo "=== does the code read GGML_CUDA_DISABLE_GRAPHS at all? ==="
grep -rn 'GGML_CUDA_DISABLE_GRAPHS' /home/revn/strix-llama/ggml/src/ggml-cuda/ 2>/dev/null | head
echo
echo "=== how does is_enabled() decide? ==="
grep -n -A12 'bool is_enabled()' /home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu | head -20
