#!/usr/bin/env bash
D=/mnt/c/AI/build/strix-llama-win/build-therock/bin/llama.dll
echo "llama.dll mtime: $(stat -c '%y' "$D")"
if grep -a -q 'PLE_TIMING' "$D" 2>/dev/null; then
  echo "=> llama.dll CONTAINS the PLE timer  **READY TO MEASURE**"
else
  echo "=> llama.dll MISSING the timer"
fi
echo
echo "### which dll actually holds which change? (for the record) ###"
for f in llama.dll ggml-hip.dll llama-common.dll; do
  p="/mnt/c/AI/build/strix-llama-win/build-therock/bin/$f"
  [ -f "$p" ] || continue
  printf '  %-18s %s   PLE=%s OP=%s\n' "$f" "$(stat -c '%y' "$p" | cut -d. -f1)" \
    "$(grep -ac 'PLE_TIMING' "$p" 2>/dev/null || echo 0)" \
    "$(grep -ac 'OP_TIMING' "$p" 2>/dev/null || echo 0)"
done
