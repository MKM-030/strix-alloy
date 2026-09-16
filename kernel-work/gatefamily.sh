#!/usr/bin/env bash
# gatefamily.sh — empirical gate-family A/B (my invented all-35 set hit GGML_ASSERT obj_new,
# so bisect by family exactly as olliehm did: MMB / HC / QSA / NORMCONV+GDN / PLE / MOE).
# usage: gatefamily.sh <tag> <family> <model> <ctx> <b> <ub> <sizes> <gen>
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
TAG="$1"; FAMILY="$2"; MODEL="$3"; CTX="$4"; B="$5"; UB="$6"; SIZES="$7"; GEN="$8"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
PORT=8155
LOG="$OUT/gf-$TAG.log"

for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done
sleep 4
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1

set_family() {
  case "$1" in
    mmb)   export LLAMA_MMB=1 LLAMA_MMB_GLU=1 LLAMA_MMB_TALL=1 LLAMA_MMB_DOWN16=1 LLAMA_MMB_MIN_T=512 ;;
    hc)    export LLAMA_HC_BLK16=1 LLAMA_HC_GATEMIX=1 LLAMA_HC_MIX_FUSE=1 LLAMA_HC_RES16=1 ;;
    qsa)   export LLAMA_QSA_SPARSE=1 LLAMA_QSA_FUSE_EXPAND=1 LLAMA_QSA_DIRECT_INDICES=1 ;;
    norm)  export LLAMA_NORM_GATED=1 LLAMA_NORM_ROWS=1 ;;
    gdn)   export LLAMA_GDN_CONV=1 ;;
    ple)   export LLAMA_PLE_CONV=1 ;;
    moe)   export LLAMA_MOE_RED_SCALAR=1 ;;
    none)  : ;;
    all-clean) export LLAMA_MMB=1 LLAMA_MMB_GLU=1 LLAMA_MMB_TALL=1 LLAMA_MMB_DOWN16=1 LLAMA_MMB_MIN_T=512
               export LLAMA_HC_BLK16=1 LLAMA_HC_GATEMIX=1 LLAMA_HC_RES16=1
               export LLAMA_QSA_SPARSE=1 LLAMA_QSA_FUSE_EXPAND=1
               export LLAMA_NORM_GATED=1 LLAMA_NORM_ROWS=1 LLAMA_GDN_CONV=1 LLAMA_PLE_CONV=1
               export LLAMA_MOE_RED_SCALAR=1
               export LLAMA_MMB_HC16=0 ;;  # proven-bad gate kept OFF; string-valued QSA/HC opts omitted (guessed "1" broke graph build)
    bool-only) export LLAMA_MMB=1 LLAMA_MMB_MIN_T=512 LLAMA_NORM_GATED=1 LLAMA_NORM_ROWS=1
               export LLAMA_GDN_CONV=1 LLAMA_PLE_CONV=1
               export LLAMA_MMB_HC16=0 ;;
  esac
}
set_family "$FAMILY"

ARGS=(-m "$MODEL" -ngl 99 -fa on -fit off --load-mode none -ctk f16 -ctv f16
      -c "$CTX" -b "$B" -ub "$UB" --parallel 1 -t 8 --host 127.0.0.1 --port $PORT --no-webui)
case "$MODEL" in *PROJFIX*) ARGS+=(--lazy-mode on-direct);; esac

echo "[$TAG] family=$FAMILY launch $(date +%T)" | tee "$LOG"
"$BIN" "${ARGS[@]}" >> "$LOG" 2>&1 &
SRV=$!
UP=0
for i in $(seq 1 420); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { UP=1; break; }
  kill -0 $SRV 2>/dev/null || break
  sleep 5
done
if [ "$UP" != 1 ]; then
  echo "[$TAG] LOAD-FAILED: $(grep -aE 'GGML_ASSERT|error|failed|ABORT' "$LOG" | tail -1)"
  exit 1
fi
python3 "$BASE/fnbench.py" --port $PORT --label "$TAG" --sizes "$SIZES" --gen "$GEN" \
  --repeats 3 --out "$OUT/gf-$TAG.json" 2>&1 | grep -E 'n= |wrote'
echo "[$TAG] done $(date +%T)"
kill -9 $SRV 2>/dev/null
