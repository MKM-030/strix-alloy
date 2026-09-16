#!/usr/bin/env bash
# restore-all.sh — revert EVERYTHING to clean and rebuild, verifying the artifact.
set -u
KW=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
W=/mnt/c/AI/build/strix-llama-win
S=/home/revn/strix-llama

echo "### 1. revert both touched files in the WSL fork"
cd "$S"
git reset -q HEAD ggml/src/ggml-cuda/ggml-cuda.cu 2>/dev/null || true
git checkout -- ggml/src/ggml-cuda/ggml-cuda.cu src/models/qwen4exp.cpp
echo "    qwen4exp ple_timing refs: $(grep -c 'ple_timing' src/models/qwen4exp.cpp || echo 0)"
echo "    ggml-cuda op_timing refs: $(grep -c 'op_timing' ggml/src/ggml-cuda/ggml-cuda.cu || echo 0)"
git status --short | head -5
echo "    (empty above = clean)"

echo
echo "### 2. sync both files to the Windows tree"
cp "$S/src/models/qwen4exp.cpp" "$W/src/models/qwen4exp.cpp"
cp "$S/ggml/src/ggml-cuda/ggml-cuda.cu" "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
echo "    win qwen4exp ple_timing: $(grep -c 'ple_timing' "$W/src/models/qwen4exp.cpp" || echo 0)"

echo
echo "### 3. rebuild with a real error check"
cd "$W"
cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target llama-server -j 16 > C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\restore-all.log 2>&1 && echo BUILD_OK" 2>/dev/null | tr -d '\0' | tail -2
E=$(grep -ac 'error:' "$KW/results/restore-all.log" 2>/dev/null); E=${E:-0}
echo "    compile errors: $E"

echo
echo "### 4. VERIFY ARTIFACTS ARE CLEAN (both dlls)"
for f in llama.dll ggml-hip.dll; do
  P="$W/build-therock/bin/$f"
  echo "  $f  mtime=$(stat -c '%y' "$P" | cut -d. -f1)  PLE=$(grep -ac 'PLE_TIMING' "$P" 2>/dev/null || echo 0)  OP=$(grep -ac 'OP_TIMING' "$P" 2>/dev/null || echo 0)"
done
