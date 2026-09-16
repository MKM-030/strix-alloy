#!/usr/bin/env bash
# What mode did the composition run actually execute in?
KW=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
F="$KW/results/cr.err"

echo "=== graphs reused (final) ==="
grep -a 'graphs reused' "$F" | tail -2

echo
echo "=== how many eager vs replay evals? (aggregate headers = eager flushes) ==="
grep -ac 'OP_TIMING aggregate' "$F"

echo
echo "=== decode timing from the run ==="
grep -aE 'eval time|tg = |n_gen = ' "$F" | tail -5

echo
echo "=== the last few aggregate blocks: totals per block ==="
grep -a 'OP_TIMING aggregate after' "$F" | tail -5

echo
echo "=== is GGML_CUDA_DISABLE_GRAPHS actually consulted in this build? ==="
grep -n 'GGML_CUDA_DISABLE_GRAPHS' /mnt/c/AI/build/strix-llama-win/ggml/src/ggml-cuda/common.cuh

echo
echo "=== compare: the ORIGINAL validated graphs-off run (opt-correct) ==="
if [ -f "$KW/results/opt-correct.err" ]; then
  echo "  headers: $(grep -ac 'OP_TIMING aggregate' "$KW/results/opt-correct.err")"
  echo "  graphs reused lines: $(grep -ac 'graphs reused' "$KW/results/opt-correct.err")"
  grep -a 'graphs reused' "$KW/results/opt-correct.err" | tail -1
  grep -aE 'eval time' "$KW/results/opt-correct.err" | tail -2
fi
