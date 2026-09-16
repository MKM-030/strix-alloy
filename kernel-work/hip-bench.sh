#!/usr/bin/env bash
# hip-bench.sh — start a WSL/HIP llama-server (Way 2 = pwilkin, Way 3 = drluoto), benchmark, stop.
# usage: hip-bench.sh <way2|way3> <tag> <sizes> <gen> <repeats> [extra server args...]
# Models load from /mnt/c (ext4 ballooning starves Windows; founder guardrail).
set -u
WAY="$1"; TAG="$2"; SIZES="$3"; GEN="$4"; REPS="$5"; shift 5
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"

if [ "$WAY" = "way2" ]; then
  BIN=/home/revn/strix-llama/build-hip/bin/llama-server
else
  BIN=/home/revn/drluoto-llama/build-hip/bin/llama-server
fi
MODEL=/mnt/c/AI/models/qwen38-flash/unsloth-UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
PORT=8114
LOG="$OUT/server-$TAG.log"

# one heavy job at a time
pkill -f llama-server 2>/dev/null; sleep 2
sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
AVAIL=$(free -g | awk '/^Mem:/{print $7}')
echo "=== $TAG start $(date +%T) avail=${AVAIL}G ===" | tee "$LOG"
[ "$AVAIL" -ge 55 ] || { echo "ABORT: <55G available"; exit 2; }

source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1

"$BIN" -m "$MODEL" -ngl 99 -fa on -c 196608 --parallel 1 -t 8 \
  --host 127.0.0.1 --port $PORT --no-webui "$@" >> "$LOG" 2>&1 &
SRV=$!
echo "pid=$SRV bin=$BIN args: $*" | tee -a "$LOG"

for i in $(seq 1 360); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && break
  kill -0 $SRV 2>/dev/null || { echo "SERVER DIED"; tail -20 "$LOG"; exit 1; }
  sleep 5
done
echo "serving; benching" | tee -a "$LOG"

python3 "$BASE/fnbench.py" --port $PORT --label "$TAG" --sizes "$SIZES" --gen "$GEN" \
  --repeats "$REPS" --repeats-big 1 --big-threshold 32768 --out "$OUT/$TAG.json" \
  --context-limit 196608 --cache-dir "$BASE" 2>&1 | tee -a "$LOG"

kill $SRV 2>/dev/null; sleep 3; kill -9 $SRV 2>/dev/null
echo "=== $TAG done $(date +%T) -> $OUT/$TAG.json ===" | tee -a "$LOG"
