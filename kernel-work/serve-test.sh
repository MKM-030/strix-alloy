#!/usr/bin/env bash
# serve-test.sh — load, self-test, and bench a config; run as the BACKGROUND COMMAND ITSELF
# (so it owns the process lifetime and nothing kills it when a wrapper returns).
# usage: serve-test.sh <tag> <bin> <model> <ctx> <b> <ub> <envs> <mtp|none> <sizes> <gen> <repeats>
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
TAG="$1"; BIN="$2"; MODEL="$3"; CTX="$4"; B="$5"; UB="$6"; ENVS="$7"; MTP="$8"; SIZES="$9"; GEN="${10}"; REPS="${11:-2}"
PORT=8140
LOG="$OUT/st-$TAG.log"

for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
sleep 4
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1
unset LLAMA_MMB 2>/dev/null || true
[ -n "$ENVS" ] && [ "$ENVS" != "-" ] && export $ENVS

ARGS=(-m "$MODEL" -ngl 99 -fa on -fit off --load-mode none -ctk f16 -ctv f16
      -c "$CTX" -b "$B" -ub "$UB" --parallel 1 -t 8 --host 127.0.0.1 --port $PORT --no-webui)
[ "${MODEL##*/}" != "${MODEL}" ] && case "$MODEL" in *PROJFIX*) ARGS+=(--lazy-mode on-direct);; esac
[ "$MTP" != "none" ] && ARGS+=(-md "$MTP" --spec-type draft-mtp --spec-draft-n-max 3)

echo "[$TAG] launching $(date +%T)" | tee "$LOG"
"$BIN" "${ARGS[@]}" >> "$LOG" 2>&1 &
SRV=$!
echo "[$TAG] pid=$SRV"

UP=0
for i in $(seq 1 480); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { UP=1; break; }
  kill -0 $SRV 2>/dev/null || { echo "[$TAG] server died $(date +%T)"; break; }
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "[$TAG] LOAD-FAILED"; grep -aiE 'd2t|t2d|vocab|wrong shape|out of memory|failed|ABORT|assert|error' "$LOG" | tail -8
  exit 1
fi
echo "[$TAG] UP $(date +%T) | d2t: $(grep -ac 'd2t\|t2d' "$LOG") | MMB markers: $(grep -acE 'MMB_TALL|MMB_GLU|MMB_BLK16|MMB_DOWN16|HC_GATEMIX|MMB_SHADOW' "$LOG")"
grep -aE 'd2t|t2d|vocab_out|listening' "$LOG" | tail -3

python3 "$BASE/fnbench.py" --port $PORT --label "$TAG" --sizes "$SIZES" --gen "$GEN" \
  --repeats "$REPS" --out "$OUT/st-$TAG.json" 2>&1 | grep -E 'n= |CHAT|wrote'

echo "[$TAG] markers-final: $(grep -acE 'MMB_TALL|MMB_GLU|MMB_BLK16|MMB_DOWN16|HC_GATEMIX|MMB_SHADOW' "$LOG")"
kill -9 $SRV 2>/dev/null
echo "[$TAG] done $(date +%T)"
