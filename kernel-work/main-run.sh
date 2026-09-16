#!/usr/bin/env bash
# main-run.sh — ONE unattended sequence. Proven-safe configs, long timeouts, port self-heal.
# Detached: setsid nohup bash main-run.sh > /tmp/main.log 2>&1 &
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
PW=/home/revn/strix-llama/build-hip/bin/llama-server
DR=/home/revn/drluoto-llama/build-hip/bin/llama-server
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
UD=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
FRSPEC=/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf
PLAIN=/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0.gguf
L="$OUT/main.log"
PORT=8120
say(){ echo "[$(date +%T)] $*" | tee -a "$L"; }

killall_srv(){
  for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
  sleep 5
  for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
  sleep 2
}
# wait until port free (max 60s)
wait_port(){
  for i in $(seq 1 30); do
    ss -tln 2>/dev/null | grep -q ":$1" || return 0
    sleep 2
  done
  return 1
}

# run <tag> <bin> <model> <ctx> <b> <ub> <envs> <mtp|none> <sizes> <gen> <repeats>
run(){
  local tag="$1" bin="$2" model="$3" ctx="$4" b="$5" ub="$6" envs="$7" mtp="$8" sizes="$9" gen="${10}" reps="${11:-2}"
  say "==== $tag ctx=$ctx b=$b ub=$ub env='$envs' mtp=$(basename ${mtp}) sizes=$sizes"
  killall_srv; wait_port $PORT || { say "PORT BUSY"; return 1; }
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1
  unset LLAMA_MMB 2>/dev/null || true
  [ -n "$envs" ] && export $envs
  local -a a=(-m "$model" -ngl 99 -fa on -fit off --load-mode none -ctk f16 -ctv f16
    -c "$ctx" -b "$b" -ub "$ub" --parallel 1 -t 8 --host 127.0.0.1 --port $PORT --no-webui)
  [ "$model" = "$PF" ] && a+=(--lazy-mode on-direct)
  [ "$mtp" != "none" ] && a+=(-md "$mtp" --spec-type draft-mtp --spec-draft-n-max 3)
  "$bin" "${a[@]}" >> "$OUT/server-$tag.log" 2>&1 &
  local srv=$! up=0
  for i in $(seq 1 480); do
    curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { up=1; break; }
    kill -0 $srv 2>/dev/null || break
    sleep 5
  done
  if [ "$up" != 1 ]; then
    say "LOAD-FAILED $tag :: $(grep -E 'out of memory|failed to allocate|wrong shape|error' "$OUT/server-$tag.log" | tail -1)"
    killall_srv; return 1
  fi
  say "loaded; benching"
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes "$sizes" --gen "$gen" \
    --repeats "$reps" --repeats-big 1 --big-threshold 32768 --out "$OUT/$tag.json" 2>&1 \
    | grep -E 'n= |wrote|error' | tee -a "$L"
  killall_srv
}

# --- Way 2 (pwilkin HIP) + PROJFIX: the MMB/ubatch matrix ---
run W2-pf-ub8k-mmb    "$PW" "$PF" 49152 8192 8192 "LLAMA_MMB=1" none "1024,8192,32768,49152" 64 3
run W2-pf-ub8k        "$PW" "$PF" 49152 8192 8192 ""           none "1024,8192,32768,49152" 64 2
run W2-pf-ub8k-mmb-mtp "$PW" "$PF" 49152 8192 8192 "LLAMA_MMB=1" "$FRSPEC" "1024,8192,32768" 128 2
# --- Way 2 + UD-IQ4_XS: MMB vs not (does the fork help the stock quant?) ---
run W2-ud-ub8k-mmb    "$PW" "$UD" 65536 8192 8192 "LLAMA_MMB=1" none "8192,32768,65536" 64 2
# --- Way 3 (drluoto HIP) + UD-IQ4_XS: with plain MTP and without ---
run W3-ud-mtp         "$DR" "$UD" 65536 8192 8192 "" "$PLAIN" "1024,8192,32768,65536" 128 2
run W3-ud-nospec      "$DR" "$UD" 65536 8192 8192 "" none     "1024,8192,32768,65536" 64 2

say "######## main run done ########"
killall_srv
