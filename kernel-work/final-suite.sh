#!/usr/bin/env bash
# final-suite.sh — robust configs only (proven to load), long timeouts, full context grids.
# Detached: setsid nohup bash final-suite.sh > /tmp/final.log 2>&1 &
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
PW=/home/revn/strix-llama/build-hip/bin/llama-server
DR=/home/revn/drluoto-llama/build-hip/bin/llama-server
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
UD=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
FRSPEC=/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf
PLAIN=/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0.gguf
PORT=8114
L="$OUT/final.log"
say(){ echo "$@" | tee -a "$L"; }
stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 4; }

# run_cfg <tag> <bin> <model> <ctx> <b> <ub> <env> <mtp-head|none> <sizes> <gen>
run_cfg(){
  local tag="$1" bin="$2" model="$3" ctx="$4" b="$5" ub="$6" envs="$7" mtp="$8" sizes="$9" gen="${10}"
  say "---- $tag ctx=$ctx b=$b ub=$ub env='$envs' mtp=$(basename "$mtp") $(date +%T) ----"
  stop_srv
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1
  if [ -n "$envs" ]; then export $envs; fi
  local -a args=(-m "$model" -ngl 99 -fa on -fit off --load-mode none \
    -ctk f16 -ctv f16 -c "$ctx" -b "$b" -ub "$ub" --parallel 1 -t 8 \
    --host 127.0.0.1 --port $PORT --no-webui)
  [ "$model" = "$PF" ] && args+=(--lazy-mode on-direct)
  if [ "$mtp" != "none" ]; then
    args+=(-md "$mtp" --spec-type draft-mtp --spec-draft-n-max 3)
  fi
  "$bin" "${args[@]}" >> "$OUT/server-$tag.log" 2>&1 &
  local srv=$!
  local up=0
  for i in $(seq 1 480); do    # 40 min load budget
    curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { up=1; break; }
    kill -0 $srv 2>/dev/null || break
    sleep 5
  done
  if [ "$up" != 1 ]; then
    say "  LOAD-FAILED $tag"
    grep -E 'out of memory|failed to allocate|error|wrong shape|vocab|d2t' "$OUT/server-$tag.log" | tail -3 >> "$L"
    kill -9 $srv 2>/dev/null; return 1
  fi
  say "  loaded $(date +%T); benching"
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes "$sizes" --gen "$gen" \
    --repeats 2 --repeats-big 1 --big-threshold 32768 --out "$OUT/$tag.json" 2>&1 \
    | grep -E 'n= |wrote|error' >> "$L"
  stop_srv
  unset LLAMA_MMB 2>/dev/null || true
}

# A) PROJFIX + MMB, ub 8192 — prefill-ceiling config within the carve (multi-ctx grid)
run_cfg A-pf-mmb-ub8k  "$PW" "$PF" 65536 8192 8192 "LLAMA_MMB=1" none "1024,8192,32768,65536" 64
# B) PROJFIX + MMB + FR-Spec MTP — decode config (tests d2t on the pwilkin fork)
run_cfg B-pf-mmb-mtp  "$PW" "$PF" 65536 8192 8192 "LLAMA_MMB=1" "$FRSPEC" "1024,8192,32768,65536" 128
# C) PROJFIX + MMB + plain MTP head (if FR-Spec d2t is unsupported)
run_cfg C-pf-mmb-mtp-plain "$PW" "$PF" 65536 8192 8192 "LLAMA_MMB=1" "$PLAIN" "1024,8192,32768,65536" 128
# D) Way 3: drluoto HIP + plain head (its own kernels; FR-Spec unsupported there per handoff)
run_cfg D-dr-hip-ud-mtp "$DR" "$UD" 65536 8192 8192 "" "$PLAIN" "1024,8192,32768,65536" 128
# E) Way 3 without MTP (isolate its base decode)
run_cfg E-dr-hip-ud-nospec "$DR" "$UD" 65536 8192 8192 "" none "1024,8192,32768,65536" 64

say "######## final suite done $(date +%T) ########"
stop_srv
