#!/usr/bin/env bash
# way3.sh — drluoto HIP + UD-IQ4_XS from EXT4 (9p was the blocker), plain MTP head.
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
DR=/home/revn/drluoto-llama/build-hip/bin/llama-server
UD=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
PLAIN=/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0.gguf
PORT=8121
L="$OUT/way3.log"
say(){ echo "[$(date +%T)] $*" | tee -a "$L"; }
stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 5; }

# ensure plain head on ext4
if [ ! -f "$PLAIN" ]; then
  say "copying plain MTP head to ext4..."
  cp /mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0.gguf "$PLAIN" 2>/dev/null \
    || cp /mnt/c/AI/models/qwen38-flash/mtp-Qwen3.8-Flash-Next-Q8_0.gguf "$PLAIN"
fi
ls -la "$PLAIN" >> "$L"

run(){
  local tag="$1" ctx="$2" b="$3" ub="$4" mtp="$5" sizes="$6" gen="$7"
  say "==== $tag ctx=$ctx b=$b ub=$ub mtp=$(basename $mtp) ===="
  stop_srv
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_DETECTION=1
  local -a a=(-m "$UD" -ngl 99 -fa on -fit off --load-mode none -ctk f16 -ctv f16
    -c "$ctx" -b "$b" -ub "$ub" --parallel 1 -t 8 --host 127.0.0.1 --port $PORT --no-webui)
  [ "$mtp" != "none" ] && a+=(-md "$mtp" --spec-type draft-mtp --spec-draft-n-max 3)
  "$DR" "${a[@]}" >> "$OUT/server-$tag.log" 2>&1 &
  local srv=$! up=0
  for i in $(seq 1 360); do
    curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { up=1; break; }
    kill -0 $srv 2>/dev/null || break
    sleep 5
  done
  if [ "$up" != 1 ]; then
    say "LOAD-FAILED $tag :: $(grep -E 'out of memory|failed|error|wrong shape' "$OUT/server-$tag.log" | tail -1)"
    stop_srv; return 1
  fi
  say "loaded; benching"
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes "$sizes" --gen "$gen" \
    --repeats 2 --repeats-big 1 --big-threshold 32768 --out "$OUT/$tag.json" 2>&1 \
    | grep -E 'n= |wrote|error' | tee -a "$L"
  stop_srv
}

run W3-ud-mtp   32768 8192 8192 "$PLAIN" "1024,8192,32768" 128
run W3-ud-nospec 32768 8192 8192 none    "1024,8192,32768" 64
say "######## way3 done ########"
stop_srv
