#!/usr/bin/env bash
# final: restore clean source, rebuild, verify artifact, and check for a vendor profiler.
set -u
W=/mnt/c/AI/build/strix-llama-win
SDK=/mnt/c/AI/sdk/therock1151
DLL="$W/build-therock/bin/ggml-hip.dll"

echo "### 1. restore clean ggml-cuda.cu from the pre-instrumentation backup"
BAK=$(ls -t "$W/ggml/src/ggml-cuda/ggml-cuda.cu.bak-"* 2>/dev/null | tail -1)
echo "    using backup: $BAK"
if [ -n "$BAK" ]; then
  grep -c 'LLAMA_OP_TIMING' "$BAK" | sed 's/^/    backup op-timing refs: /'
  cp "$BAK" "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
else
  # no backup: take it from the clean WSL branch
  cp /home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
fi
echo "    now: $(grep -c 'LLAMA_OP_TIMING' "$W/ggml/src/ggml-cuda/ggml-cuda.cu") op-timing refs"
cp "$W/ggml/src/ggml-cuda/ggml-cuda.cu" /home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu 2>/dev/null || true

echo
echo "### 2. rebuild with a REAL exit code"
cd "$W"
cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target llama-server -j 16 > C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\final-build.log 2>&1 && echo BUILD_OK" 2>/dev/null | tr -d '\0' | tail -3
echo "    errors: $(grep -ac 'error:' /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/final-build.log 2>/dev/null)"

echo
echo "### 3. verify artifact"
echo "    dll mtime: $(stat -c '%y' "$DLL" 2>/dev/null)"
if grep -a -q 'OP_TIMING' "$DLL" 2>/dev/null; then echo "    timer strings present (expected absent now)"; else echo "    clean DLL (no timer) **OK**"; fi

echo
echo "### 4. is there a vendor profiler in the SDK?"
for t in rocprof rocprofv2 rocprofv3 rocprofiler-sdk rocminfo hipInfo; do
  found=$(find "$SDK" -maxdepth 3 -iname "*${t}*" 2>/dev/null | head -3)
  if [ -n "$found" ]; then echo "    $t:"; echo "$found" | sed 's/^/       /'; else echo "    $t: not found"; fi
done
