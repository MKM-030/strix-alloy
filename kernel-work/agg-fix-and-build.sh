#!/usr/bin/env bash
# agg-fix-and-build.sh — fix the 2 unaliased cuda* names, build, VERIFY artifact.
set -u
KW=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
W=/mnt/c/AI/build/strix-llama-win
S=/home/revn/strix-llama
DLL="$W/build-therock/bin/ggml-hip.dll"
F="$S/ggml/src/ggml-cuda/ggml-cuda.cu"

echo "### fix unaliased names (hip.* have no hip* alias in vendors/hip.h)"
python3 - "$F" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
# only inside the op_timing namespace block
start = s.index('namespace op_timing {')
end   = s.index('} // namespace op_timing', start)
blk   = s[start:end]
n1 = blk.count('cudaEventCreate(')
n2 = blk.count('cudaEventElapsedTime(')
blk = blk.replace('cudaEventCreate(', 'hipEventCreate(')
blk = blk.replace('cudaEventElapsedTime(', 'hipEventElapsedTime(')
s = s[:start] + blk + s[end:]
open(p, 'w', encoding='utf-8').write(s)
print(f'  replaced cudaEventCreate x{n1}, cudaEventElapsedTime x{n2}')
PY

echo "### sync + build"
cp "$F" "$W/ggml/src/ggml-cuda/ggml-cuda.cu"
cd "$W"
cmd.exe /c "cd /d C:\AI\build\strix-llama-win && cmake --build build-therock --target llama-server -j 16 > C:\Projects\REV-N-ornith-eval-20260911\kernel-work\results\agg-build2.log 2>&1 && echo BUILD_OK" 2>/dev/null | tr -d '\0' | tail -2
ERRS=$(grep -ac 'error:' "$KW/results/agg-build2.log" 2>/dev/null); ERRS=${ERRS:-0}
echo "    compile errors: $ERRS"
if [ "$ERRS" != "0" ]; then grep -a 'error:' "$KW/results/agg-build2.log" | head -5; fi

echo "### verify artifact"
if grep -a -q 'OP_TIMING aggregate' "$DLL" 2>/dev/null; then
  echo "    => DLL CONTAINS the aggregate timer **READY TO MEASURE**"
else
  echo "    => DLL does NOT contain the timer"
fi
