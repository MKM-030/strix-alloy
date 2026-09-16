#!/usr/bin/env bash
# build-ple-timing.sh — sync, build, VERIFY THE ARTIFACT, and restore clean on failure.
set -u
KW=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
W=/mnt/c/AI/build/strix-llama-win
S=/home/revn/strix-llama
DLL="$W/build-therock/bin/ggml-hip.dll"

echo "### 1. sync source"
cp "$S/src/models/qwen4exp.cpp" "$W/src/models/qwen4exp.cpp"
echo "    ple_timing refs in win source: $(grep -c 'ple_timing' "$W/src/models/qwen4exp.cpp")"

echo "### 2. build"
cd "$W"
cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target llama-server -j 16 > C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\ple-build.log 2>&1 && echo BUILD_OK" 2>/dev/null | tr -d '\0' | tail -2
E=$(grep -ac 'error:' "$KW/results/ple-build.log" 2>/dev/null); E=${E:-0}
echo "    compile errors: $E"
if [ "$E" != "0" ]; then
  echo "    --- errors ---"
  grep -a 'error:' "$KW/results/ple-build.log" | head -8
  echo "    --- restoring clean qwen4exp.cpp ---"
  cd "$S" && git checkout -- src/models/qwen4exp.cpp
  exit 1
fi

echo "### 3. VERIFY ARTIFACT"
echo "    dll mtime: $(stat -c '%y' "$DLL")"
if grep -a -q 'PLE_TIMING' "$DLL" 2>/dev/null; then
  echo "    => DLL CONTAINS the PLE timer  **READY TO MEASURE**"
else
  echo "    => DLL MISSING the PLE timer  **BUILD DID NOT TAKE**"
  exit 1
fi
