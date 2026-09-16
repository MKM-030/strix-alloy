#!/usr/bin/env bash
# mtp-isolate.sh — does MTP decode work on the pwilkin fork if we DISABLE the extra gates?
# (The full gate set spins in the draft-load path; this isolates gates vs draft.)
# usage: mtp-isolate.sh <tag> <gate-mode: none|mmb-only|all> <mtp-head|none>
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
TAG="$1"; MODE="$2"; MTP="${3:-none}"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
UD=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
PORT=8164
LOG="$OUT/mi-$TAG.log"

for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
sleep 4
source "$BASE/env.sh"
export HSA_ENABLE_DXG_ETECTION=1 2>/dev/null || true
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1 HSA_OVERRIDE_GFX_VERSION=11.5.1

case "$MODE" in
  none) : ;;
  mmb-only) export LLAMA_MMB=1 LLAMA_MMB_MIN_T=512 ;;
  all)
    export LLAMA_MMB=1 LLAMA_MMB_MIN_T=512 LLAMA_MMB_BF16W=1 LLAMA_MMB_GLU=1 LLAMA_MMB_TALL=2 \
           LLAMA_MMB_CACHE=4 LLAMA_MMB_F32SPLIT=2 LLAMA_MMB_HC16=2 LLAMA_MMB_SHADOW=2 LLAMA_MMB_DOWN16=1 \
           LLAMA_HC_CN_SHAPE=1 LLAMA_HC_GATEMIX=1 LLAMA_HC_MIX_FUSE=1 LLAMA_HC_BLK16=1 LLAMA_HC_RES16=1 \
           LLAMA_HC_PACK_DI=1 LLAMA_NORM_GATED=1 LLAMA_NORM_ROWS=1 LLAMA_IDX_RELU_SUM=1 LLAMA_PLE_CONV=1 \
           LLAMA_GDN_CONV=1 LLAMA_QSA_SPARSE=1 LLAMA_QSA_WHOLE_ATTN=1 LLAMA_QSA_BLOCK_SELECTION=1 \
           LLAMA_QSA_COMPACT_METADATA=1 LLAMA_QSA_DENSE_SHORTCUT=1 LLAMA_QSA_DIRECT_INDICES=1 \
           LLAMA_QSA_PACK_KEYS=1 LLAMA_QSA_PACK_VALUES=1 LLAMA_QSA_QUERY_STRIP=512 \
           LLAMA_QSA_SCORE_BOUNDS=1 LLAMA_QSA_NO_DENSE_MASK=1 LLAMA_QSA_FA_V3=1 LLAMA_QSA_FUSE_EXPAND=1
    ;;
esac

ARGS=(-m "$UD" -ngl 999 -fa on -fit off --load-mode none -ctk f16 -ctv f16
      -c 8192 -b 2048 -ub 2048 --parallel 1 --jinja --host 127.0.0.1 --port $PORT --no-webui)
[ "$MTP" != "none" ] && ARGS+=(-md "$MTP" --spec-type draft-mtp --spec-draft-n-max 2)

echo "[$TAG] mode=$MODE mtp=$(basename $MTP) launch $(date +%T)" | tee "$LOG"
"$BIN" "${ARGS[@]}" >> "$LOG" 2>&1 &
SRV=$!
UP=0
for i in $(seq 1 180); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { UP=1; break; }
  kill -0 $SRV 2>/dev/null || break
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "[$TAG] LOAD-FAILED/HUNG: $(grep -aE 'error|failed|assert' "$LOG" | tail -1)"
  kill -9 $SRV 2>/dev/null; exit 1
fi
echo "[$TAG] UP $(date +%T)"
python3 "$BASE/fnbench.py" --port $PORT --label "$TAG" --sizes 1024,4096 --gen 128 \
  --repeats 2 --out "$OUT/mi-$TAG.json" 2>&1 | grep -E 'n= |wrote'
echo "[$TAG] draft: $(grep -a 'draft acceptance' "$LOG" | tail -1)"
kill -9 $SRV 2>/dev/null
echo "[$TAG] done $(date +%T)"
