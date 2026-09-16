#!/usr/bin/env bash
cd /home/revn/strix-llama
echo "=== all PLE-related symbols in src ==="
grep -rn 'ple' src/llama-graph.h | head -20
echo
echo "=== PLE in llama-graph.cpp ==="
grep -rn 'ple_embd\|build_ple\|per_layer_token_embd' src/llama-graph.cpp | head -20
echo
echo "=== PLE in the model file ==="
grep -n 'ple\|per_layer_token' src/models/qwen4exp.cpp | head -30
