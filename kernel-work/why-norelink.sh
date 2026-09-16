#!/usr/bin/env bash
# Why does `cmake --build` say OK but not relink?
set -u
W=/mnt/c/AI/build/strix-llama-win
LOG=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/ple-build.log

echo "=== what did the build log actually say? ==="
tail -25 "$LOG" 2>/dev/null | tr -d '\0'
echo
echo "=== mtimes: source vs its object ==="
stat -c '%y  %n' "$W/src/models/qwen4exp.cpp" 2>/dev/null
find "$W/build-therock" -name 'qwen4exp.cpp.obj' -exec stat -c '%y  %n' {} \; 2>/dev/null
echo
echo "=== is the DLL newer than the object? ==="
stat -c '%y  %n' "$W/build-therock/bin/ggml-hip.dll" 2>/dev/null
echo
echo "=== which target actually compiles qwen4exp.cpp? ==="
grep -rl 'qwen4exp' "$W/build-therock"/*.ninja 2>/dev/null | head
grep -c 'qwen4exp' "$W/build-therock/build.ninja" 2>/dev/null || echo "  (not in build.ninja)"
