#!/usr/bin/env bash
cd /home/revn/strix-llama || exit 1
echo "=== FILL dispatch in compute_forward ==="
sed -n '2430,2445p' ggml/src/ggml-cuda/ggml-cuda.cu
echo
echo "=== FILL in supports_op / backend ==="
sed -n '6212,6228p' ggml/src/ggml-cuda/ggml-cuda.cu
echo
echo "=== is there a FILL cuda kernel? ==="
grep -rn "GGML_OP_FILL\|ggml_cuda_op_fill\|fill_kernel" ggml/src/ggml-cuda/*.cu ggml/src/ggml-cuda/*.cuh 2>/dev/null | head -8
echo
echo "=== ggml_fill implementation (ggml.c) ==="
grep -n "ggml_fill\b" -A 12 ggml/src/ggml.c | head -20
echo
echo "=== set-rows.cu index handling ==="
sed -n '375,400p' ggml/src/ggml-cuda/set-rows.cu
