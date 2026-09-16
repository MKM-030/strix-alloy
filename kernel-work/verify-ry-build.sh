#!/usr/bin/env bash
LOG=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/ry-build.log
D=/mnt/c/AI/build/strix-llama-win/build-therock/bin/llama-server-impl.dll
echo "compile errors: $(grep -ac 'error:' "$LOG" 2>/dev/null)"
echo "dll mtime: $(stat -c '%y' "$D" | cut -d. -f1)"
if grep -a -q 'target_ms/round' "$D" 2>/dev/null; then
  echo "=> binary CONTAINS the round/yield accounting  **READY**"
else
  echo "=> binary MISSING it"
fi
echo
echo "=== engine dlls (llama.dll carries qwen4exp) clean of earlier instrumentation? ==="
for f in llama.dll ggml-hip.dll llama-server-impl.dll; do
  P="/mnt/c/AI/build/strix-llama-win/build-therock/bin/$f"
  printf '  %-24s PLE=%s OP=%s ROUNDS=%s\n' "$f" \
    "$(grep -ac 'PLE_TIMING' "$P" 2>/dev/null || true)" \
    "$(grep -ac 'OP_TIMING' "$P" 2>/dev/null || true)" \
    "$(grep -ac 'target_ms/round' "$P" 2>/dev/null || true)"
done
