#!/usr/bin/env bash
# agg-only.sh — cherry-pick ONLY c7cab982 (aggregate per-op timer), build, VERIFY the artifact.
set -u
KW=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
W=/mnt/c/AI/build/strix-llama-win
S=/home/revn/strix-llama
DLL="$W/build-therock/bin/ggml-hip.dll"

echo "### 0. make sure win-native is clean, then cherry-pick the aggregate commit only"
cd "$S"
git checkout -- ggml/src/ggml-cuda/ggml-cuda.cu 2>/dev/null || true
git stash list | head -3
git status --short | head -5
git cherry-pick -n c7cab982 2>&1 | tail -3
echo "    refs after cherry-pick: $(grep -c 'op_timing::' ggml/src/ggml-cuda/ggml-cuda.cu)"
echo "    in-graph refs (want 0): $(grep -c 'op_timing_ig' ggml/src/ggml-cuda/ggml-cuda.cu)"

echo
echo "### 1. sync + build"
cp "$S/ggml/src/ggml-cuda/ggml-cuda.cu" "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
cd "$W"
cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target llama-server -j 16 > C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\agg-build.log 2>&1 && echo BUILD_OK" 2>/dev/null | tr -d '\0' | tail -2
ERRS=$(grep -ac 'error:' "$KW/results/agg-build.log" 2>/dev/null)
ERRS=${ERRS:-0}
echo "    compile errors: $ERRS"
if [ "$ERRS" != "0" ]; then
  echo "    --- first errors ---"
  grep -a 'error:' "$KW/results/agg-build.log" | head -6
fi

echo
echo "### 2. VERIFY THE ARTIFACT"
echo "    dll mtime: $(stat -c '%y' "$DLL" 2>/dev/null)"
if grep -a -q 'OP_TIMING aggregate' "$DLL" 2>/dev/null; then
  echo "    => DLL CONTAINS the aggregate timer **READY**"
else
  echo "    => DLL does NOT contain the timer **NOT READY**"
fi
