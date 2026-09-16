#!/usr/bin/env bash
# Confirm the dense -> sparse QSA transition is spanned by our measured range.
cd /home/revn/strix-llama
echo "=== the sparse gate ==="
grep -n -B6 -A6 'qwen4exp_use_block_selection' src/models/qwen4exp.cpp | head -40
