#!/usr/bin/env bash
# rebuild-and-verify.sh — sync, build, then VERIFY THE BINARY (not the log) contains the timer.
set -u
KW=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
W=/mnt/c/AI/build/strix-llama-win
DLL="$W/build-therock/bin/ggml-hip.dll"

echo "### 1. sync source"
cp /home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
echo "    src refs: $(grep -c 'op_timing::record' "$W/ggml/src/ggml-cuda/ggml-cuda.cu")"

echo "### 2. force-rebuild the target"
export KW
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\Projects\REV-N-ornith-eval-20260911\kernel-work\build-win-therock.ps1' >/dev/null 2>&1
echo "    build rc=$?"

echo "### 3. VERIFY THE ARTIFACT"
echo "    src mtime: $(stat -c '%y' "$W/ggml/src/ggml-cuda/ggml-cuda.cu")"
echo "    dll mtime: $(stat -c '%y' "$DLL")"
if grep -a -q 'OP_TIMING aggregate' "$DLL" 2>/dev/null; then
  echo "    => DLL CONTAINS the aggregate timer  **OK**"
else
  echo "    => DLL MISSING the timer  **BUILD DID NOT TAKE**"
  exit 1
fi
