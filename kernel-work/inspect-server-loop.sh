#!/usr/bin/env bash
# Inspect the server generate loop for the phase boundaries we can time WITHOUT adding a sync.
cp /home/revn/strix-llama/tools/server/server-context.cpp \
   /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/src-server-context.cpp
cd /home/revn/strix-llama/tools/server
echo "=== llama_decode call sites ==="
grep -n 'llama_decode' server-context.cpp
echo
echo "=== spec process / accept / begin sites ==="
grep -n 'common_speculative_process\|common_speculative_accept\|common_speculative_begin\|common_sampler_sample' server-context.cpp
echo
echo "=== print_timing block start ==="
grep -n 'print_timing\|t_prompt_total\|t_gen_total' server-context.cpp | head -20
echo
echo "=== file length ==="
wc -l server-context.cpp
