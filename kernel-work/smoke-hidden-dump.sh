#!/usr/bin/env bash
# smoke-hidden-dump.sh — verify llama-hidden-dump loads a model and emits h_nextn rows.
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1 HSA_OVERRIDE_GFX_VERSION=11.5.1

BIN=/home/revn/strix-llama/build-hip/bin/llama-hidden-dump
# small, fast, and known to have an MTP/nextn block
MODEL=/home/revn/models/Ornith-1.5-35B-MTP-23G-ICE.gguf
CORPUS="$BASE/bench-corpus.txt"

PREFIX="$OUT/hd-smoke"
rm -f "$PREFIX".tokens "$PREFIX".h "$PREFIX".json

echo "=== llama-hidden-dump smoke ==="
"$BIN" -m "$MODEL" -f "$CORPUS" --out "$PREFIX" --ntokens 512 --window 256 \
  -c 256 -b 256 -ngl 99 2>&1 | tail -30
echo "exit=$?"
echo "--- artifacts ---"
ls -la "$PREFIX"* 2>/dev/null || echo "NONE"
echo "--- manifest ---"
cat "$PREFIX.json" 2>/dev/null || echo "no manifest"
