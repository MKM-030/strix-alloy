#!/usr/bin/env bash
# projfix-opt.sh — best-effort PROJFIX optimization within the 32 GB carve.
# Detached: setsid nohup bash projfix-opt.sh > /tmp/pfopt.log 2>&1 &
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
FRSPEC=/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf
PORT=8114
L="$OUT/opt.log"
say(){ echo "$@" >> "$L"; }
say "######## opt run start $(date +%T) ########"

stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 4; }

# run_cfg <tag> <ctx> <batch> <ub> <mmb:0|1> <mtp:off|frspec> <sizes> <gen>
run_cfg(){
  local tag="$1" ctx="$2" b="$3" ub="$4" mmb="$5" mtp="$6" sizes="$7" gen="$8"
  say "---- $tag ctx=$ctx b=$b ub=$ub mmb=$mmb mtp=$mtp $(date +%T) ----"
  stop_srv
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1
  [ "$mmb" = "1" ] && export LLAMA_MMB=1 || unset LLAMA_MMB
  local -a args=(-m "$PF" -ngl 99 -fa on -fit off --load-mode none --lazy-mode on-direct
    -ctk f16 -ctv f16 -c "$ctx" -b "$b" -ub "$ub" --parallel 1 -t 8
    --host 127.0.0.1 --port $PORT --no-webui)
  if [ "$mtp" = "frspec" ]; then
    args+=(-md "$FRSPEC" --spec-type draft-mtp --spec-draft-n-max 3)
  fi
  "$BIN" "${args[@]}" >> "$OUT/server-$tag.log" 2>&1 &
  local srv=$!
  local up=0
  for i in $(seq 1 240); do
    curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { up=1; break; }
    kill -0 $srv 2>/dev/null || break
    sleep 5
  done
  if [ "$up" != 1 ]; then
    say "  LOAD-FAILED $tag"
    grep -E 'out of memory|failed to allocate|error|d2t|wrong shape|vocab' "$OUT/server-$tag.log" | tail -3 >> "$L"
    kill -9 $srv 2>/dev/null; return 1
  fi
  say "  loaded; benching"
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes "$sizes" --gen "$gen" \
    --repeats 2 --repeats-big 1 --big-threshold 32768 --out "$OUT/$tag.json" 2>&1 \
    | grep -E 'n= |wrote|error' >> "$L"
  stop_srv
}

# 1) max ubatch that fits (12288) with MMB, no MTP -> prefill ceiling at this carve
run_cfg pf-ub12288-mmb 49152 12288 12288 1 off 8192,32768,49152 64
# 2) same + FR-Spec MTP -> does the pwilkin fork accept d2t, and what decode?
run_cfg pf-ub12288-mmb-mtp 49152 12288 12288 1 frspec 8192,32768,49152 128
# 3) ub 8192 with MTP (safety margin, more KV)
run_cfg pf-ub8192-mtp 65536 8192 8192 1 frspec 8192,32768,65536 128
# 4) no MMB control at ub12288 (isolate MMB effect at this ubatch)
run_cfg pf-ub12288-nommb 49152 12288 12288 0 off 8192,32768 64

say "######## opt run done $(date +%T) ########"
stop_srv
