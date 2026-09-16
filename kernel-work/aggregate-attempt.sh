#!/usr/bin/env bash
# aggregate-attempt.sh — ONE careful attempt at per-op composition, with artifact verification
# at every step. Composition needs the aggregate timer (graphs-off path), which DID produce a
# validated result earlier; the only reason it later failed is that the env var did not reach
# the process and/or the build silently failed.
set -u
KW=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
W=/mnt/c/AI/build/strix-llama-win
S=/home/revn/strix-llama
DLL="$W/build-therock/bin/ggml-hip.dll"

echo "### 1. start from the CLEAN source"
BAK=$(ls -t "$W/ggml/src/ggml-cuda/ggml-cuda.cu.bak-"* 2>/dev/null | head -1)
cp "$BAK" "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
echo "    clean refs: $(grep -c 'op_timing' "$W/ggml/src/ggml-cuda/ggml-cuda.cu")"

echo "### 2. apply ONLY the aggregate instrumentation (c7cab982) via the WSL fork"
cd "$S"
git stash list | head -3
# take the aggregate-only file straight out of that commit
git show c7cab982:ggml/src/ggml-cuda/ggml-cuda.cu > /tmp/agg.cu 2>/dev/null
if [ -s /tmp/agg.cu ]; then
  echo "    extracted c7cab982 file: $(wc -l < /tmp/agg.cu) lines"
  # that commit was based on an older tree; instead apply just its diff onto the clean file
  git diff c7cab982~1 c7cab982 -- ggml/src/ggml-cuda/ggml-cuda.cu > /tmp/agg.patch 2>/dev/null
  echo "    patch lines: $(wc -l < /tmp/agg.patch)"
  cp "$W/ggml/src/ggml-cuda/ggml-cuda.cu" /tmp/clean.cu
  if patch -s -p1 /tmp/clean.cu < /tmp/agg.patch 2>/dev/null; then
    echo "    aggregate patch applied cleanly"
    cp /tmp/clean.cu "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
  else
    echo "    patch did not apply against the current tree"
  fi
fi
echo "    refs now: $(grep -c 'op_timing::' "$W/ggml/src/ggml-cuda/ggml-cuda.cu")"

echo "### 3. build with a REAL error check"
cd "$W"
cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target llama-server -j 16 > C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\agg-build.log 2>&1 && echo BUILD_OK" 2>/dev/null | tr -d '\0' | tail -2
ERRS=$(grep -ac 'error:' "$KW/results/agg-build.log" 2>/dev/null || echo 0)
echo "    compile errors: $ERRS"

echo "### 4. verify the ARTIFACT"
if [ "$ERRS" != "0" ]; then
  echo "    BUILD FAILED -- restoring clean and stopping"
  cp "$BAK" "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
  cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target llama-server -j 16 >nul 2>&1" 2>/dev/null
  exit 1
fi
if grep -a -q 'OP_TIMING aggregate' "$DLL" 2>/dev/null; then
  echo "    => DLL CONTAINS the aggregate timer  **READY TO MEASURE**"
else
  echo "    => DLL does NOT contain the timer"
fi
