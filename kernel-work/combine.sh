#!/usr/bin/env bash
# combine.sh — the combined config: pwilkin HIP + PROJFIX + MMB=1 + FR-Spec MTP (patched fork).
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
PW=/home/revn/strix-llama/build-hip/bin/llama-server
PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
FR=/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf
PORT=8126
L="$OUT/combine.log"
say(){ echo "[$(date +%T)] $*" | tee -a "$L"; }
stop_srv(){ for p in $(pgrep -x llama-server); do kill -9 "$p" 2>/dev/null; done; sleep 5; }

stop_srv
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1 LLAMA_MMB=1
say "==== combined: PROJFIX + MMB + FR-Spec MTP (d2t patched) ===="
"$PW" -m "$PF" -ngl 99 -fa on -fit off --load-mode none --lazy-mode on-direct \
  -ctk f16 -ctv f16 -c 49152 -b 8192 -ub 8192 --parallel 1 -t 8 \
  -md "$FR" --spec-type draft-mtp --spec-draft-n-max 3 \
  --host 127.0.0.1 --port $PORT --no-webui > "$OUT/server-combine.log" 2>&1 &
SRV=$!
UP=0
for i in $(seq 1 420); do
  curl -s http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { UP=1; break; }
  kill -0 $SRV 2>/dev/null || break
  sleep 5
done
if [ "$UP" != 1 ]; then
  say "LOAD-FAILED. key lines:"
  grep -aE 'd2t|t2d|wrong shape|out of memory|failed|error|n_vocab_out' "$OUT/server-combine.log" | tail -8 | tee -a "$L"
  exit 1
fi
say "LOADED OK — FR-Spec accepted by the HIP fork!"
grep -aE 'd2t|t2d|n_vocab_out|MTP using' "$OUT/server-combine.log" | tail -4 | tee -a "$L"
python3 "$BASE/fnbench.py" --port $PORT --label combine-frspec-mmb --sizes 1024,8192,32768 --gen 128 \
  --repeats 3 --out "$OUT/combine-frspec-mmb.json" 2>&1 | grep -E 'n= |wrote' | tee -a "$L"
say "MMB markers: $(grep -acE 'MMB_TALL|MMB_GLU|MMB_BLK16|MMB_DOWN16|HC_GATEMIX|MMB_SHADOW' "$OUT/server-combine.log")"
stop_srv
say "######## combine done ########"
