#!/usr/bin/env bash
# lever-test.sh — isolate ubatch vs MMB on PROJFIX (they cannot coexist on the 32GB carve).
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
PW=/home/revn/strix-llama/build-hip/bin/llama-server
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
PORT=8116
L="$OUT/lever.log"
say(){ echo "$@" | tee -a "$L"; }
stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 5; }

run(){
  local tag="$1" ctx="$2" b="$3" ub="$4" envs="$5"
  say "---- $tag ctx=$ctx b=$b ub=$ub env='$envs' $(date +%T) ----"
  stop_srv
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_ETECTION=1 2>/dev/null || true
  export HSA_ENABLE_DXG_DETECTION=1   unset LLAMA_MMB 2>/dev/null || true
  [ -n "$envs" ] && export $envs
  "$PW" -m "$PF" -ngl 99 -fa on -fit off --load-mode none --lazy-mode on-direct \
    -ctk f16 -ctv f16 -c "$ctx" -b "$b" -ub "$ub" --parallel 1 -t 8 \
    --host 127.0.0.1 --port $PORT --no-webui >> "$OUT/server-$tag.log" 2>&1 &
  local srv=$! up=0
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
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes 8192,32768 --gen 64 \
    --repeats 3 --out "$OUT/$tag.json" 2>&1 | grep -E 'n= |wrote' >> "$L"
  stop_srv
}

# ubatch ladder WITHOUT mmb (mmb's 6 GiB shadow blocks the big ubatch)
run L1-ub8192-nommb  "$PF" 49152 8192  8192  ""
run L2-ub12288-nommb "$PF" 49152 12288 12288 ""
# mmb with the safe ubatch (known good; repeat for variance)
run L3-ub8192-mmb    "$PF" 49152 8192  8192  "LLAMA_MMB=1"
run L4-ub4096-mmb    "$PF" 49152 4096  4096  "LLAMA_MMB=1"

say "######## lever test done $(date +%T) ########"
stop_srv
