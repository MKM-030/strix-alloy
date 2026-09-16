#!/usr/bin/env bash
cd /home/revn/strix-llama || exit 1
echo "=== fork state ==="
git log --oneline -3
echo "--- working tree (empty = clean) ---"
git status --short
echo
echo "=== production binaries free of instrumentation? ==="
for f in llama.dll ggml-hip.dll llama-server-impl.dll; do
  p="/mnt/c/AI/build/strix-llama-win/build-therock/bin/$f"
  [ -f "$p" ] || continue
  printf '  %-24s mtime=%s  PLE=%s  OP=%s\n' "$f" \
    "$(stat -c '%y' "$p" | cut -d. -f1)" \
    "$(grep -ac 'PLE_TIMING' "$p" 2>/dev/null || echo 0)" \
    "$(grep -ac 'OP_TIMING' "$p" 2>/dev/null || echo 0)"
done
echo
echo "=== docs written this turn ==="
ls -t /mnt/c/Projects/REV-N-ornith-eval-20260911/docs/benchmarks/*20260915*.md 2>/dev/null | head -8 | while read x; do basename "$x"; done
