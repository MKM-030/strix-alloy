#!/usr/bin/env bash
# hip-bench2.sh — parameterized WSL/HIP llama-server bench (pwilkin & drluoto builds).
# usage: hip-bench2.sh <tag> <bin> <model> <sizes> <gen> <repeats> [--server-args...]
# Everything after repeats is passed verbatim to llama-server.
set -u
TAG="$1"; BIN="$2"; MODEL="$3"; SIZES="$4"; GEN="$5"; REPS="$6"; shift 6
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
PORT=8114
LOG="$OUT/server-$TAG.log"

pkill -x llama-server 2>/dev/null; sleep 3
sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
AVAIL=$(free -g | awk '/^Mem:/{print $7}')
echo "=== $TAG start $(date +%T) avail=${AVAIL}G bin=$BIN ===" | tee "$LOG"
[ "$AVAIL" -ge 55 ] || { echo "ABORT: <55G available"; exit 2; }

source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1

"$BIN" -m "$MODEL" -ngl 99 -fa on --parallel 1 -t 8 \
  --host 127.0.0.1 --port $PORT --no-webui "$@" >> "$LOG" 2>&1 &
SRV=$!
echo "pid=$SRV args: $*" | tee -a "$LOG"

for i in $(seq 1 400); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && break
  kill -0 $SRV 2>/dev/null || { echo "SERVER DIED"; tail -25 "$LOG"; exit 1; }
  sleep 5
done
echo "serving at $(date +%T); benching" | tee -a "$LOG"

python3 "$BASE/fnbench.py" --port $PORT --label "$TAG" --sizes "$SIZES" --gen "$GEN" \
  --repeats "$REPS" --repeats-big 1 --big-threshold 32768 --out "$OUT/$TAG.json" 2>&1 | tee -a "$LOG"

kill $SRV 2>/dev/null; sleep 3; kill -9 $SRV 2>/dev/null
echo "=== $TAG done $(date +%T) -> $OUT/$TAG.json ===" | tee -a "$LOG"
