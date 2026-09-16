#!/usr/bin/env bash
# final-two.sh — (a) stock UD + author gates (olliehm parity), (b) PROJFIX + author gates @ ub16384.
# Detached run as the background command itself.
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
UD=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
PORT=8166
L="$OUT/final2.log"
say(){ echo "[$(date +%T)] $*" | tee -a "$L"; }
stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 5; }

gates_all(){
  export LLAMA_MMB=1 LLAMA_MMB_MIN_T=512 LLAMA_MMB_BF16W=1 LLAMA_MMB_GLU=1 LLAMA_MMB_TALL=2 \
    LLAMA_MMB_CACHE=4 LLAMA_MMB_F32SPLIT=2 LLAMA_MMB_HC16=2 LLAMA_MMB_SHADOW=2 LLAMA_MMB_DOWN16=1 \
    LLAMA_HC_CN_SHAPE=1 LLAMA_HC_GATEMIX=1 LLAMA_HC_MIX_FUSE=1 LLAMA_HC_BLK16=1 LLAMA_HC_RES16=1 \
    LLAMA_HC_PACK_DI=1 LLAMA_NORM_GATED=1 LLAMA_NORM_ROWS=1 LLAMA_IDX_RELU_SUM=1 LLAMA_PLE_CONV=1 \
    LLAMA_GDN_CONV=1 LLAMA_QSA_SPARSE=1 LLAMA_QSA_WHOLE_ATTN=1 LLAMA_QSA_BLOCK_SELECTION=1 \
    LLAMA_QSA_COMPACT_METADATA=1 LLAMA_QSA_DENSE_SHORTCUT=1 LLAMA_QSA_DIRECT_INDICES=1 \
    LLAMA_QSA_PACK_KEYS=1 LLAMA_QSA_PACK_VALUES=1 LLAMA_QSA_QUERY_STRIP=512 \
    LLAMA_QSA_SCORE_BOUNDS=1 LLAMA_QSA_NO_DENSE_MASK=1 LLAMA_QSA_FA_V3=1 LLAMA_QSA_FUSE_EXPAND=1
}

# run <tag> <model> <ctx> <b> <ub> <sizes> <gen>
run(){
  local tag="$1" model="$2" ctx="$3" b="$4" ub="$5" sizes="$6" gen="$7"
  say "==== $tag ctx=$ctx b=$b ub=$ub model=$(basename $model)"
  stop_srv
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; sleep 2
  source "$BASE/env.sh"
  export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1 HSA_OVERRIDE_GFX_VERSION=11.5.1
  gates_all
  local -a a=(-m "$model" -ngl 999 -fa on -fit off --load-mode none -ctk f16 -ctv f16
    -c "$ctx" -b "$b" -ub "$ub" --parallel 1 --jinja --host 127.0.0.1 --port $PORT --no-webui)
  case "$model" in *PROJFIX*) a+=(--lazy-mode on-direct);; esac
  "$BIN" "${a[@]}" >> "$OUT/f2-$tag.log" 2>&1 &
  local srv=$! up=0
  for i in $(seq 1 480); do
    curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { up=1; break; }
    kill -0 $srv 2>/dev/null || break
    sleep 5
  done
  if [ "$up" != 1 ]; then
    say "  LOAD-FAILED $tag: $(grep -aE 'GGML_ASSERT|error|failed|out of memory' "$OUT/f2-$tag.log" | tail -1)"
    stop_srv; return 1
  fi
  say "  loaded $(date +%T)"
  python3 "$BASE/fnbench.py" --port $PORT --label "$tag" --sizes "$sizes" --gen "$gen" \
    --repeats 3 --out "$OUT/f2-$tag.json" 2>&1 | grep -E 'n= |wrote' | tee -a "$L"
  stop_srv
}

run ud-author "$UD" 49152 8192 8192 "1024,8192,16384,32768" 128
run pf-ub16k "$PF" 49152 16384 16384 "8192,16384,32768" 128
say "######## final2 done ########"
stop_srv
