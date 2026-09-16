#!/usr/bin/env bash
cd /home/revn/strix-llama
echo "=== op-timing commits ==="
git log --oneline -4 op-timing
echo
echo "=== diff stat: what op-timing adds over our base d67d5883 ==="
git diff --stat d67d5883 op-timing | tail -20
echo
echo "=== t_draft_us plumbing ==="
grep -rn 't_draft_us' common/*.cpp tools/server/*.cpp tools/server/*.h 2>/dev/null | head -20
echo
echo "=== common_speculative_print_stats ==="
grep -n -A25 'void common_speculative_print_stats' common/speculative.cpp | head -40
echo
echo "=== LLAMA_OP_TIMING references ==="
grep -rn 'LLAMA_OP_TIMING' ggml/src/ common/ tools/ 2>/dev/null | head -20
