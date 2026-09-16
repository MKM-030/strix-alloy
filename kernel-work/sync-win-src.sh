#!/usr/bin/env bash
# sync-win-src.sh — rsync the rebased WSL fork into the Windows build tree,
# excluding build outputs and VCS metadata. Windows tree keeps its own build-therock.
set -euo pipefail
W=/home/revn/strix-llama
V=/mnt/c/AI/build/strix-llama-win

echo "=== what will be excluded (build outputs) ==="
ls -d "$V"/build* 2>/dev/null || echo "  (no build dirs)"
ls -d "$V"/build-therock 2>/dev/null && echo "  -> build-therock preserved"

echo "=== rsync source -> windows tree ==="
rsync -a --delete \
  --exclude '/.git/' \
  --exclude '/build-*/' \
  --exclude '/build/' \
  --exclude '*.o' \
  --exclude '*.obj' \
  --exclude '*.a' \
  --exclude '__pycache__/' \
  "$W/" "$V/"

echo "=== verify the new kernels landed ==="
for f in ggml/src/ggml-cuda/mmb-quant.cuh ggml/src/ggml-cuda/mmb.cu ggml/src/ggml-cuda/ple-conv.cu \
         src/models/qwen4exp.cpp src/llama-lazy-reader.h tools/hidden-dump/hidden-dump.cpp; do
  if [ -f "$V/$f" ]; then echo "  OK   $f"; else echo "  MISS $f"; fi
done
echo "=== mmb-quant present in windows mmb.cu? ==="
grep -c 'mmb-quant' "$V/ggml/src/ggml-cuda/mmb.cu" || echo 0
echo "=== prefetch stub present? ==="
grep -c 'prefetch(const int32_t \*, int64_t) const {}' "$V/src/llama-lazy-reader.h" || echo 0
echo "=== d2t refs? ==="
grep -c 'd2t' "$V/src/models/qwen4exp.cpp" || echo 0
echo "=== build dir survived? ==="
ls -d "$V"/build-therock 2>/dev/null && echo "  build-therock OK"
