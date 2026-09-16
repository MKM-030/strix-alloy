#!/usr/bin/env bash
# Why is ninja not rebuilding ggml-cuda.cu even though the source is newer?
set -u
W=/mnt/c/AI/build/strix-llama-win
S="$W/ggml/src/ggml-cuda/ggml-cuda.cu"
OBJ="$W/build-therock/ggml/src/ggml-hip/CMakeFiles/ggml-hip.dir/__/ggml-cuda/ggml-cuda.cu.obj"

echo "=== mtimes (with nanoseconds) ==="
stat -c '%Y.%y  %n' "$S" "$OBJ" 2>/dev/null
echo
echo "=== what ninja thinks ==="
cd "$W"
cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target ggml-hip 2>&1" 2>/dev/null | tr -d '\0' | tail -20
echo
echo "=== after ==="
stat -c '%y  %n' "$S" "$OBJ" 2>/dev/null
