#!/usr/bin/env bash
cd /home/revn/strix-llama

echo "=== A. qwen4exp_query_strip — the claimed 4x flattened width ==="
grep -n -B4 -A25 'static.*qwen4exp_query_strip' src/models/qwen4exp.cpp | head -50

echo
echo "=== B. where score_strip / strip is used (the indexer scoring path) ==="
grep -n 'score_strip\|query_strip\|n_tps' src/models/qwen4exp.cpp | head -30

echo
echo "=== C. the matvec cap of 8 — MMVF/MMF dispatch ==="
grep -rn 'ncols_dst\|<= 8\|> 8\b' ggml/src/ggml-cuda/mmvf.cu 2>/dev/null | head -12
echo "--- mmf ---"
grep -rn 'NCOLS\|ncols' ggml/src/ggml-cuda/mmf.cuh 2>/dev/null | head -8
