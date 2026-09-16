#!/usr/bin/env bash
# gates-test.sh — replicate olliehm's 964-1045 t/s recipe: ALL 35 fork gates ON,
# with the single known-bad gate LLAMA_MMB_HC16=0. Stock UD-IQ4_XS, ub 8192.
# Run as the background command itself so it owns process lifetime.
# usage: gates-test.sh <tag> <model> <ctx> <b> <ub> <sizes> <gen> [mtp-head|none]
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
TAG="$1"; MODEL="$2"; CTX="$3"; B="$4"; UB="$5"; SIZES="$6"; GEN="$7"; MTP="${8:-none}"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
PORT=8150
LOG="$OUT/gt-$TAG.log"

for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
sleep 4
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 HSA_OVERRIDE_GFX_VERSION=11.5.1

# ---- the 35 launcher gates: all ON except the one proven-bad (MMB_HC16) ----
export LLAMA_GDN_CHUNKED=1
export LLAMA_GDN_CONV=1
export LLAMA_HC_BLK16=1
export LLAMA_HC_CN_SHAPE=1
export LLAMA_HC_GATEMIX=1
export LLAMA_HC_MIX_FUSE=1
export LLAMA_HC_PACK_DI=1
export LLAMA_HC_RES16=1
export LLAMA_IDX_RELU_SUM=1
export LLAMA_MMB=1
export LLAMA_MMB_BF16W=1
export LLAMA_MMB_CACHE=1
export LLAMA_MMB_DOWN16=1
export LLAMA_MMB_F32SPLIT=1
export LLAMA_MMB_GLU=1
export LLAMA_MMB_HC16=0          # <-- the single fix from issue #24
export LLAMA_MMB_MIN_T=512
export LLAMA_MMB_SHADOW=1
export LLAMA_MMB_TALL=1
export LLAMA_MOE_RED_SCALAR=1
export LLAMA_MTP_EH_FLATTEN=1
export LLAMA_MTP_QSA=1
export LLAMA_NORM_GATED=1
export LLAMA_NORM_ROWS=1
export LLAMA_PLE_CONV=1
export LLAMA_PLE_PREFETCH=1
export LLAMA_QSA_BLOCK_SELECTION=1
export LLAMA_QSA_DENSE_SHORTCUT=1
export LLAMA_QSA_DIRECT_INDICES=1
export LLAMA_QSA_FUSE_EXPAND=1
export LLAMA_QSA_PACK_KEYS=1
export LLAMA_QSA_PACK_VALUES=1
export LLAMA_QSA_QUERY_STRIP=1
export LLAMA_QSA_SCORE_WMMA=1
export LLAMA_QSA_SPARSE=1
export LLAMA_QSA_TOKEN_EMBD=1
export LLAMA_QSA_WHOLE_ATTN=1

ARGS=(-m "$MODEL" -ngl 99 -fa on -fit off --load-mode none -ctk f16 -ctv f16
      -c "$CTX" -b "$B" -ub "$UB" --parallel 1 -t 8 --host 127.0.0.1 --port $PORT --no-webui)
case "$MODEL" in *PROJFIX*) ARGS+=(--lazy-mode on-direct);; esac
[ "$MTP" != "none" ] && ARGS+=(-md "$MTP" --spec-type draft-mtp --spec-draft-n-max 4 --spec-draft-p-min 0.75)

echo "[$TAG] launch $(date +%T) gates=35 (HC16=0)" | tee "$LOG"
"$BIN" "${ARGS[@]}" >> "$LOG" 2>&1 &
SRV=$!
UP=0
for i in $(seq 1 480); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { UP=1; break; }
  kill -0 $SRV 2>/dev/null || { echo "[$TAG] died $(date +%T)"; break; }
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "[$TAG] LOAD-FAILED"; grep -aiE 'error|failed|ABORT|assert|out of memory|d2t|wrong' "$LOG" | tail -6
  exit 1
fi
echo "[$TAG] UP $(date +%T)"
python3 "$BASE/fnbench.py" --port $PORT --label "$TAG" --sizes "$SIZES" --gen "$GEN" \
  --repeats 3 --out "$OUT/gt-$TAG.json" 2>&1 | grep -E 'n= |CHAT|wrote'
echo "[$TAG] done $(date +%T)"
kill -9 $SRV 2>/dev/null
