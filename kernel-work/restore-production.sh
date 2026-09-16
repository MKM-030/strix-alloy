#!/usr/bin/env bash
# RESTORE PRODUCTION: clean source, rebuild, verify artifact, then the benchmark runs separately.
set -u
KW=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
W=/mnt/c/AI/build/strix-llama-win
S=/home/revn/strix-llama
DLL="$W/build-therock/bin/ggml-hip.dll"

echo "### 1. drop the cherry-picked instrumentation on win-native"
cd "$S"
git checkout -- ggml/src/ggml-cuda/ggml-cuda.cu 2>/dev/null || true
git status --short | head -3
echo "    win-native op-timing refs: $(grep -c 'op_timing' ggml/src/ggml-cuda/ggml-cuda.cu)"

echo "### 2. take the known-good clean file (pre-instrumentation backup)"
BAK=$(ls -t "$W/ggml/src/ggml-cuda/ggml-cuda.cu.bak-"* | head -1)
cp "$BAK" "$S/ggml/src/ggml-cuda/ggml-cuda.cu"
cp "$BAK" "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
echo "    using $BAK -> refs: $(grep -c 'LLAMA_OP_TIMING' "$W/ggml/src/ggml-cuda/ggml-cuda.cu")"

echo "### 3. rebuild"
cd "$W"
cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target llama-server -j 16 > C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\restore-build.log 2>&1 && echo BUILD_OK" 2>/dev/null | tr -d '\0' | tail -2
E=$(grep -ac 'error:' "$KW/results/restore-build.log" 2>/dev/null); E=${E:-0}
echo "    compile errors: $E"

echo "### 4. verify artifact is CLEAN"
echo "    dll mtime: $(stat -c '%y' "$DLL")"
if grep -a -q 'OP_TIMING' "$DLL" 2>/dev/null; then
  echo "    => DLL STILL HAS TIMER  **PROBLEM**"
else
  echo "    => DLL CLEAN (no timer)  **OK**"
fi
