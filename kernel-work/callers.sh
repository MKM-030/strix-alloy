#!/usr/bin/env bash
# callers.sh — who calls qwen4exp_use_block_selection?
cd /home/revn/strix-llama || exit 1
grep -rn 'use_block_selection' src/ --include='*.cpp' --include='*.h'
echo
echo "--- context of each caller ---"
grep -rn 'use_block_selection' src/ --include='*.cpp' | grep -v 'static bool' | cut -d: -f1-2 | while IFS=: read -r f l; do
  echo "== $f:$l"
  sed -n "$((l-6)),$((l+3))p" "$f"
done
