#!/usr/bin/env bash
# mtp-bisect.sh — which gate FAMILY breaks the MTP draft-load path?
# Baseline: MTP works with no gates (18-19 t/s, 48-58% accept). Full gates: draft load HANGS.
# Each config gets a hard timeout; "HANG" means the draft-load spin.
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
UD=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
HEAD=/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0.gguf
PORT=8170
L="$OUT/bisect.log"
say(){ echo "[$(date +%T)] $*" | tee -a "$L"; }
stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 4; }

set_family(){
  case "$1" in
    mmb)  export LLAMA_MMB=1 LLAMA_MMB_MIN_T=512 LLAMA_MMB_BF16W=1 LLAMA_MMB_GLU=1 LLAMA_MMB_TALL=2 \
                 LLAMA_MMB_CACHE=4 LLAMA_MMB_F32SPLIT=2 LLAMA_MMB_HC16=2 LLAMA_MMB_SHADOW=2 LLAMA_MMB_DOWN16=1 ;;
    hc)   export LLAMA_HC_CN_SHAPE=1 LLAMA_HC_GATEMIX=1 LLAMA_HC_MIX_FUSE=1 LLAMA_HC_BLK16=1 \
                 LLAMA_HC_RES16=1 LLAMA_HC_PACK_DI=1 ;;
    qsa)  export LLAMA_QSA_SPARSE=1 LLAMA_QSA_WHOLE_ATTN=1 LLAMA_QSA_BLOCK_SELECTION=1 \
                 LLAMA_QSA_COMPACT_METADATA=1 LLAMA_QSA_DENSE_SHORTCUT=1 LLAMA_QSA_DIRECT_INDICES=1 \
                 LLAMA_QSA_PACK_KEYS=1 LLAMA_QSA_PACK_VALUES=1 LLAMA_QSA_QUERY_STRIP=512 \
                 LLAMA_QSA_SCORE_BOUNDS=1 LLAMA_QSA_NO_DENSE_MASK=1 LLAMA_QSA_FA_V3=1 LLAMA_QSA_FUSE_EXPAND=1 ;;
    norm) export LLAMA_NORM_GATED=1 LLAMA_NORM_ROWS=1 LLAMA_IDX_RELU_SUM=1 LLAMA_PLE_CONV=1 LLAMA_GDN_CONV=1 ;;
  esac
}

# test <family> — one family + MTP; HANG detection via hard timeout
test_family(){
  local fam="$1"
  say "==== MTP + family=$fam ===="
  stop_srv
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  local log="$OUT/bis-$fam.log"
  : > "$log"
  # subshell: env vars scoped per family
  (
    source "$BASE/env.sh"
    export HSA_ENABLE_DXG_DETECTION=1 HSA_OVERRIDE_GFX_VERSION=11.5.1
    set_family "$fam"
    exec timeout -k 5 900 "$BIN" -m "$UD" -ngl 999 -fa on -fit off --load-mode none \
      -ctk f16 -ctv f16 -c 8192 -b 2048 -ub 2048 --parallel 1 --jinja \
      -md "$HEAD" --spec-type draft-mtp --spec-draft-n-max 2 \
      --host 127.0.0.1 --port $PORT --no-webui
  ) >> "$log" 2>&1 &
  local srv=$!
  local up=0
  for i in $(seq 1 150); do   # 150*4s = 600s
    curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { up=1; break; }
    kill -0 $srv 2>/dev/null || break
    sleep 4
  done
  if [ "$up" != 1 ]; then
    local last
    last=$(grep -aE 'loading draft model|listening|error' "$log" | tail -1)
    if echo "$last" | grep -q 'loading draft model'; then
      say "  $fam -> HANG (stuck at draft load)"
    else
      say "  $fam -> FAIL/other: $last"
    fi
    for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
    sleep 3
    return 1
  fi
  say "  $fam -> LOADED"
  python3 "$BASE/fnbench.py" --port $PORT --label "bis-$fam" --sizes 1024 --gen 96 \
    --repeats 2 --out "$OUT/bis-$fam.json" 2>&1 | grep -E 'n= ' | tee -a "$L"
  say "  $fam accept: $(grep -a 'draft acceptance' "$log" | tail -1 | sed 's/.*draft acceptance/draft acceptance/')"
  stop_srv
}

for fam in mmb hc qsa norm; do test_family "$fam"; done
say "######## bisect done ########"
stop_srv
