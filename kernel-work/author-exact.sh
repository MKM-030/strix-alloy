#!/usr/bin/env bash
# author-exact.sh — the author's EXACT gate set + flags (from /home/revn/pwilkin/install.sh lines 493-540),
# adapted to WSL/DXG (no retained PM4, ub lowered to fit the 32 GB carve).
# usage: author-exact.sh <tag> <model> <ctx> <b> <ub> <sizes> <gen> [mtp-head|none] [extra llama args]
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
TAG="$1"; MODEL="$2"; CTX="$3"; B="$4"; UB="$5"; SIZES="$6"; GEN="$7"; MTP="${8:-none}"
shift 8 2>/dev/null || shift $# 2>/dev/null || true
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
PORT=8160
LOG="$OUT/ax-$TAG.log"

for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
sleep 4
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 HSA_OVERRIDE_GFX_VERSION=11.5.1

# ---- the author's exact gate block (verbatim values from install.sh) ----
export LLAMA_MMB=1 LLAMA_MMB_MIN_T=512 \
  LLAMA_MMB_BF16W=1 LLAMA_MMB_GLU=1 \
  LLAMA_MMB_TALL=2 LLAMA_MMB_CACHE=4 \
  LLAMA_MMB_F32SPLIT=2 LLAMA_MMB_HC16=2 \
  LLAMA_MMB_SHADOW=2 LLAMA_MMB_DOWN16=1 \
  LLAMA_HC_CN_SHAPE=1 LLAMA_HC_GATEMIX=1 \
  LLAMA_HC_MIX_FUSE=1 LLAMA_HC_BLK16=1 \
  LLAMA_HC_RES16=1 LLAMA_HC_PACK_DI=1 \
  LLAMA_NORM_GATED=1 LLAMA_NORM_ROWS=1 \
  LLAMA_IDX_RELU_SUM=1 LLAMA_PLE_CONV=1 \
  LLAMA_GDN_CONV=1 \
  LLAMA_QSA_SPARSE=1 LLAMA_QSA_WHOLE_ATTN=1 \
  LLAMA_QSA_BLOCK_SELECTION=1 \
  LLAMA_QSA_COMPACT_METADATA=1 \
  LLAMA_QSA_DENSE_SHORTCUT=1 \
  LLAMA_QSA_DIRECT_INDICES=1 \
  LLAMA_QSA_PACK_KEYS=1 LLAMA_QSA_PACK_VALUES=1 \
  LLAMA_QSA_QUERY_STRIP=512 \
  LLAMA_QSA_SCORE_BOUNDS=1 \
  LLAMA_QSA_NO_DENSE_MASK=1 \
  LLAMA_QSA_FA_V3=1 LLAMA_QSA_FUSE_EXPAND=1 \
  LLAMA_MTP_QSA=1 LLAMA_MTP_QSA_MIN_T=128

# MTP_QSA requires the MTP layer's indexer tensors; the plain head lacks them, so an MTP run
# with full gates spins in the draft-load path. Disable the MTP-specific QSA gates for MTP runs.
if [ "$MTP" != "none" ]; then
  export LLAMA_MTP_QSA=0
fi

ARGS=(-m "$MODEL" -dev ROCm0 -ngl 999 -fa on -fit off --load-mode none -ctk f16 -ctv f16
      -c "$CTX" -b "$B" -ub "$UB" --parallel 1 --jinja
      --host 127.0.0.1 --port $PORT --no-webui)
case "$MODEL" in *PROJFIX*) ARGS+=(--lazy-mode on-direct);; esac
if [ "$MTP" != "none" ]; then
  ARGS+=(-md "$MTP" --spec-type draft-mtp --spec-draft-model "$MTP" --spec-draft-device ROCm0 --spec-draft-ngl 99 --spec-draft-n-max 2)
fi
[ "$#" -gt 0 ] && ARGS+=("$@")

echo "[$TAG] author-exact launch $(date +%T) gates=37 ub=$UB" | tee "$LOG"
"$BIN" "${ARGS[@]}" >> "$LOG" 2>&1 &
SRV=$!
UP=0
for i in $(seq 1 480); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { UP=1; break; }
  kill -0 $SRV 2>/dev/null || { echo "[$TAG] died $(date +%T)"; break; }
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "[$TAG] LOAD-FAILED: $(grep -aE 'GGML_ASSERT|error|failed|ABORT|out of memory' "$LOG" | tail -1)"
  exit 1
fi
echo "[$TAG] UP $(date +%T); QSA markers: $(grep -ac 'QSA_SCORE_BOUNDS active' "$LOG")"
python3 "$BASE/fnbench.py" --port $PORT --label "$TAG" --sizes "$SIZES" --gen "$GEN" \
  --repeats 3 --out "$OUT/ax-$TAG.json" 2>&1 | grep -E 'n= |wrote'
echo "[$TAG] done $(date +%T)"
kill -9 $SRV 2>/dev/null
