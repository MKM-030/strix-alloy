#!/usr/bin/env bash
# Is there disk I/O in the per-token decode path? (PLE table paging)
cd /home/revn/strix-llama
echo "=== our run configs: lazy-mode / load-mode usage ==="
grep -rn 'lazy-mode\|load-mode' /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/*.ps1 2>/dev/null | head -10

echo
echo "=== PLE prefetch / lazy reader implementation ==="
grep -n 'prefetch\|lazy' src/llama-lazy-reader.h | head -20

echo
echo "=== how PLE rows are gathered (get_rows on per_layer_token_embd) ==="
grep -n 'per_layer_token_embd\|ple_' src/models/qwen4exp.cpp | head -25

echo
echo "=== does llm_graph_input_embd_h / ple gather read from host buffer? ==="
grep -rn 'PLE\|ple_' src/llama-hparams.h | head -15

echo
echo "=== is there any disk write / checkpoint in the server? ==="
grep -rn 'ofstream\|fwrite\|std::fstream' tools/server/server-context.cpp | head -10

echo
echo "=== reading the lazy reader header (first 90 lines) ==="
sed -n '1,90p' src/llama-lazy-reader.h
