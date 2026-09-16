#!/usr/bin/env bash
# wsl-hip-check.sh — does HIP work from WSL (a different runtime path over /dev/dxg)?
# If WSL HIP works but native-Windows HIP does not, the fault is in the native ROCm runtime.
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1 HSA_OVERRIDE_GFX_VERSION=11.5.1

BIN=/home/revn/strix-llama/build-hip/bin/llama-hidden-dump
MODEL=/home/revn/models/Ornith-1.5-35B-MTP-23G-ICE.gguf

echo "=== WSL HIP path test ($(date -Iseconds)) ==="
echo "bin:   $BIN"
echo "model: $MODEL  exists=$([ -f "$MODEL" ] && echo yes || echo no)"
echo "--- running (512 tokens) ---"
rm -f "$OUT/hd-wslcheck".tokens "$OUT/hd-wslcheck".h "$OUT/hd-wslcheck".json
timeout 900 "$BIN" -m "$MODEL" -f "$BASE/bench-corpus.txt" --out "$OUT/hd-wslcheck" \
  --ntokens 512 --window 256 -c 256 -b 256 -ngl 99 2>&1 | grep -iE \
  'ROCm devices|AMD Radeon|device|threadpool|context|graph|hidden-dump|error|fail|abort|assert' | head -25
echo "exit=${PIPESTATUS[0]}"
echo "--- artifacts ---"
ls -la "$OUT"/hd-wslcheck.* 2>/dev/null || echo "NONE"
