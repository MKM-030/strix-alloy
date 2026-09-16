#!/usr/bin/env bash
# ub16-suite.sh — does ub 16384 unlock high prefill? Focused, robust, one config at a time.
# Detached: setsid nohup bash ub16-suite.sh > /tmp/ub16.log 2>&1 &
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
PW=/home/revn/strix-llama/build-hip/bin/llama-server
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
UD=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
PORT=8115
L="$OUT/ub16.log"
say(){ echo "$@" | tee -a "$L"; }
stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 5; }

# run <tag> <model> <ctx> <b> <ub> <envs> <sizes> <gen>
run(){
  local tag="$1" model="$2" ctx="$3" b="$4" ub="$5" envs="$6" sizes="$7" gen="$8"
  say "---- $tag ctx=$ctx b=$b ub=$ub env='$envs' $(date +%T) ----"
  stop_srv
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_DETECTION=1   unset LLAMA_MMB 2>/dev/null || true
  [ -n "$envs" ] && export $envs
  local -a a=(-m "$model" -ngl 99 -fa on -fit off --load-mode none -ctk f16 -ctv f16
    -c "$ctx" -b "$b" -ub "$ub" --parallel 1 -t 8 --host 127.0.0.1 --port $PORT --no-webui)
  [ "$model" = "$PF" ] && a+=(--lazy-mode on-direct)
  "$PW" "${a[@]}" >> "$OUT/server-$tag.log" 2>&1 &
  local srv=$!
  local up=0
  for i in $(seq 1 420); do
    curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { up=1; break; }
    kill -0 $srv 2>/dev/null || break
    sleep 5
  done
  if [ "$up" != 1 ]; then
    say "  LOAD-FAILED $tag :: $(grep -E 'out of memory|failed to allocate' "$OUT/server-$tag.log" | tail -1)"
    kill -9 $srv 2>/dev/null; return 1
  fi
  say "  loaded $(date +%T)"
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes "$sizes" --gen "$gen" \
    --repeats 2 --repeats-big 1 --big-threshold 32768 --out "$OUT/$tag.json" 2>&1 \
    | grep -E 'n= |wrote|error' >> "$L"
  stop_srv
}

# UD-IQ4_XS is 60.4 GiB resident -> ub 16384 should fit; test prefill at multiple ctx
run U1-ud-ub16k-nommb  "$UD" 32768 16384 16384 ""            "8192,32768" 64
run U2-ud-ub16k-mmb    "$UD" 32768 16384 16384 "LLAMA_MMB=1" "8192,32768" 64
run U3-ud-ub8k-mmb     "$UD" 32768 8192  8192  "LLAMA_MMB=1" "8192,32768" 64
# PROJFIX best-known working prefill config for reference in the same session
run P1-pf-ub8k-mmb     "$PF" 49152 8192  8192  "LLAMA_MMB=1" "8192,32768" 64

say "######## ub16 suite done $(date +%T) ########"
stop_srv
