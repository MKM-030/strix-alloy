#!/usr/bin/env bash
cd /home/revn/strix-llama
echo "=== PLE graph input class + set_input (search whole src tree) ==="
grep -rn 'llm_graph_input_ple\|struct.*ple.*set_input\|ple_ngram\|build_ple' src/*.h src/*.cpp src/models/*.cpp 2>/dev/null | head -25

echo
echo "=== how does the PLE row lookup happen? (hash / gather / pread) ==="
grep -rn 'hash\|ngram\|gather\|pread\|lazy' src/models/qwen4exp.cpp | grep -i 'ple\|ngram\|hash' | head -20

echo
echo "=== is there a CPU-side loop producing PLE indices? ==="
grep -n -B3 -A18 'ple_indices\|ple_rows\|ple_ids' src/models/qwen4exp.cpp | head -60
