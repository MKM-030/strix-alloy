#!/usr/bin/env bash
# decisive.sh — (1) MMB on/off clean A/B with marker capture at pp16k; (2) MTP depth sweep inputs.
# Detached: setsid nohup bash decisive.sh > /tmp/dec.log 2>&1 &
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
PW=/home/revn/strix-llama/build-hip/bin/llama-server
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
PORT=8122
L="$OUT/decisive.log"
say(){ echo "[$(date +%T)] $*" | tee -a "$L"; }
stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 5; }

run(){
  local tag="$1" ctx="$2" b="$3" ub="$4" envs="$5" sizes="$6" gen="$7"
  say "==== $tag ctx=$ctx b=$b ub=$ub env='$envs' sizes=$sizes"
  stop_srv
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1
  unset LLAMA_MMB LLAMA_MMB_MIN_T LLAMA_MMB_GLU LLAMA_MMB_SHADOW LLAMA_MMB_BF16W 2>/dev/null || true
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
    say "  LOAD-FAILED $tag :: $(grep -aE 'out of memory|failed to allocate' "$OUT/server-$tag.log" | tail -1)"
    stop_srv; return 1
  fi
  # marker census BEFORE benching
  local markers
  markers=$(grep -acE 'MMB_TALL|MMB_GLU|MMB_BLK16|MMB_DOWN16|HC_GATEMIX|MMB_SHADOW|MMB_CVT' "$OUT/server-$tag.log" || true)
  say "  loaded; MMB markers in log = $markers"
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes "$sizes" --gen "$gen" \
    --repeats 3 --out "$OUT/$tag.json" 2>&1 | grep -E 'n= |wrote' >> "$L"
  markers=$(grep -acE 'MMB_TALL|MMB_GLU|MMB_BLK16|MMB_DOWN16|HC_GATEMIX|MMB_SHADOW|MMB_CVT' "$OUT/server-$tag.log" || true)
  say "  post-bench MMB markers = $markers"
  stop_srv
}

# 16k prefill (pp16384 = the author's exact workload), MMB ON vs OFF, ub 8192 (fits)
run D1-pp16k-mmb    98304 8192 8192 "LLAMA_MMB=1" "8192,16384,32768" 64
run D2-pp16k-nommb  98304 8192 8192 ""            "8192,16384,32768" 64
# also capture CLOSE-UP: does MMB fire at all? run with CVT_LOG
run D3-mmb-cvtlog   98304 8192 8192 "LLAMA_MMB=1 LLAMA_MMB_CVT_LOG=1" "16384" 32
say "######## decisive done ########"
stop_srv
