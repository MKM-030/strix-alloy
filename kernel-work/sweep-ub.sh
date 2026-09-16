#!/usr/bin/env bash
# sweep-ub.sh — ubatch/batch sweep for the pwilkin HIP fork, one server at a time.
# Detach with: setsid nohup bash sweep-ub.sh > /tmp/sweep.log 2>&1 &
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
PORT=8114
SWEEP_LOG="$OUT/sweep-ub.log"

echo "==== sweep start $(date +%T) ====" >> "$SWEEP_LOG"

# (batch, ubatch, ctx, extra env)
run_cfg() {
  local b="$1" ub="$2" ctx="$3" mmenv="$4"
  local tag="pf-b${b}-ub${ub}"
  echo "---- $tag (ctx=$ctx env='$mmenv') $(date +%T) ----" >> "$SWEEP_LOG"
  pkill -x llama-server 2>/dev/null
  sleep 4
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
  sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_DETECTION=1   # shellcheck disable=SC2086
  if [ -n "$mmenv" ]; then
    env $mmenv "$BIN" -m "$PF" -ngl 99 -fa on -fit off --load-mode none --lazy-mode on-direct \
      -ctk f16 -ctv f16 -c "$ctx" -b "$b" -ub "$ub" --parallel 1 -t 8 \
      --host 127.0.0.1 --port $PORT --no-webui >> "$OUT/server-$tag.log" 2>&1 &
  else
    "$BIN" -m "$PF" -ngl 99 -fa on -fit off --load-mode none --lazy-mode on-direct \
      -ctk f16 -ctv f16 -c "$ctx" -b "$b" -ub "$ub" --parallel 1 -t 8 \
      --host 127.0.0.1 --port $PORT --no-webui >> "$OUT/server-$tag.log" 2>&1 &
  fi
  local srv=$!
  local up=0
  for i in $(seq 1 300); do
    curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { up=1; break; }
    kill -0 $srv 2>/dev/null || break
    sleep 5
  done
  if [ "$up" != 1 ]; then
    echo "  LOAD-FAILED $tag" >> "$SWEEP_LOG"
    grep -E 'out of memory|failed to allocate|error' "$OUT/server-$tag.log" | tail -2 >> "$SWEEP_LOG"
    kill -9 $srv 2>/dev/null
    return
  fi
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes 8192,32768 64 2 \
    --repeats 2 --out "$OUT/$tag.json" 2>&1 | grep -E 'n= |wrote' >> "$SWEEP_LOG"
  kill $srv 2>/dev/null; sleep 3; kill -9 $srv 2>/dev/null
}

# ctx chosen so that ctx + ub fits: KV f16 ~ 24 KiB/token for 12 attn layers + recurrent state
run_cfg 8192  8192  49152 ""
run_cfg 16384 16384 65536 ""
run_cfg 8192  8192  65536 ""
run_cfg 4096  4096  65536 ""

echo "==== sweep done $(date +%T) ====" >> "$SWEEP_LOG"
