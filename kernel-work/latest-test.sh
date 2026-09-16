#!/usr/bin/env bash
# latest-test.sh — the new strix-halo branch (d67d5883): tuned defaults compiled in, no env gates.
# Tests prefill AND decode (with plain MTP head, which previously hung under the gate set).
# usage: latest-test.sh <tag> <model> <ctx> <b> <ub> <sizes> <gen> [mtp-head|none]
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
TAG="$1"; MODEL="$2"; CTX="$3"; B="$4"; UB="$5"; SIZES="$6"; GEN="$7"; MTP="${8:-none}"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
PORT=8175
LOG="$OUT/lt-$TAG.log"

for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
sleep 4
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1 HSA_OVERRIDE_GFX_VERSION=11.5.1
# NOTE: d67d588 compiled the tuned values in and DELETED the gates; do not set LLAMA_* gates.
env | grep -c '^LLAMA_' | sed 's/^/[gates inherited: /;s/$/]/'

ARGS=(-m "$MODEL" -dev ROCm0 -ngl 999 -fa on -fit off --load-mode none -ctk f16 -ctv f16
      -c "$CTX" -b "$B" -ub "$UB" --parallel 1 --jinja --host 127.0.0.1 --port $PORT --no-webui)
case "$MODEL" in *PROJFIX*) ARGS+=(--lazy-mode on-direct);; esac
if [ "$MTP" != "none" ]; then
  ARGS+=(-md "$MTP" --spec-type draft-mtp --spec-draft-n-max 2)
fi

echo "[$TAG] latest-branch launch $(date +%T) ctx=$CTX b=$B ub=$UB mtp=$(basename $MTP)" | tee "$LOG"
"$BIN" "${ARGS[@]}" >> "$LOG" 2>&1 &
SRV=$!
UP=0
for i in $(seq 1 420); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { UP=1; break; }
  kill -0 $SRV 2>/dev/null || { echo "[$TAG] died $(date +%T)"; break; }
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "[$TAG] LOAD-FAILED: $(grep -aE 'GGML_ASSERT|error|failed|out of memory' "$LOG" | tail -1)"
  kill -9 $SRV 2>/dev/null; exit 1
fi
echo "[$TAG] UP $(date +%T)"
python3 "$BASE/fnbench.py" --port $PORT --label "$TAG" --sizes "$SIZES" --gen "$GEN" \
  --repeats 3 --out "$OUT/lt-$TAG.json" 2>&1 | grep -E 'n= |wrote'
echo "[$TAG] draft: $(grep -a 'draft acceptance' "$LOG" | tail -1 | sed 's/.*draft acceptance/draft acceptance/')"
kill -9 $SRV 2>/dev/null
echo "[$TAG] done $(date +%T)"
