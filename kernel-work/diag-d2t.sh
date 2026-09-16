#!/usr/bin/env bash
# diag-d2t.sh — why does the d2t logit-expansion fault on HIP?
cd /home/revn/strix-llama || exit 1
echo "=== set_rows CUDA/HIP kernel: which index types are supported? ==="
grep -rn "set_rows" ggml/src/ggml-cuda/*.cu ggml/src/ggml-cuda/*.cuh 2>/dev/null | head -12
echo
echo "=== the set_rows launch switch (index dtype handling) ==="
grep -rn "GGML_TYPE_I32\|GGML_TYPE_I64" ggml/src/ggml-cuda/set-rows.cu 2>/dev/null | head -12
echo
echo "=== GGML_OP_FILL on cuda? ==="
grep -rn "GGML_OP_FILL" ggml/src/ggml-cuda/ggml-cuda.cu | head -4
echo
echo "=== the d2t code as compiled (win-native) ==="
grep -n "d2t" src/models/qwen4exp.cpp | head -20
