#!/usr/bin/env bash
D=/mnt/c/AI/build/strix-llama-win/build-therock/bin/ggml-hip.dll
S=/mnt/c/AI/build/strix-llama-win/ggml/src/ggml-cuda/ggml-cuda.cu
O=$(find /mnt/c/AI/build/strix-llama-win/build-therock -name 'ggml-cuda.cu.obj' 2>/dev/null | head -1)

echo "=== does the built DLL contain the AGGREGATE timer string? ==="
if grep -a -q 'OP_TIMING aggregate' "$D" 2>/dev/null; then echo "  YES - aggregate timer compiled in"; else echo "  NO  - aggregate timer NOT in the binary"; fi
echo "=== and the in-graph string (should be absent) ==="
if grep -a -q 'OP_TIMING_IG' "$D" 2>/dev/null; then echo "  present (unexpected)"; else echo "  absent (expected)"; fi

echo
echo "=== source vs object timestamps ==="
stat -c '%y  %n' "$S" 2>/dev/null
[ -n "$O" ] && stat -c '%y  %n' "$O" 2>/dev/null
stat -c '%y  %n' "$D" 2>/dev/null

echo
echo "=== aggregate code currently in the source ==="
grep -n 'OP_TIMING aggregate\|op_timing::record\|op_timing::flush' "$S"
