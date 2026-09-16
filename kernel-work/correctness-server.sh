#!/usr/bin/env bash
# Numerical-correctness A/B: same prompt, temp 0, graphs ON vs OFF via llama-server.
# usage: correctness-server.sh <on|off> <model.gguf> [extra server args...]
set -u
source /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/env.sh
export HSA_ENABLE_DXG_DETECTION=1 MODE="$1"; MODEL="$2"; shift 2
TAG="corr-$MODE-$(basename "$MODEL" | cut -c1-24)"
BIN=/home/revn/strix-llama/build-hip/bin/llama-server
OUT=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/expA
mkdir -p "$OUT"
cd "$OUT"
[ "$MODE" = "off" ] && export GGML_CUDA_DISABLE_GRAPHS=1

sync
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null
sleep 2

"$BIN" -m "$MODEL" -ngl 99 -fa on -c 2048 -b 512 -ub 512 -t 8 \
  --host 127.0.0.1 --port 8098 --no-webui \
  > "$TAG-server.log" 2>&1 &
SRV=$!
echo "[$TAG] server pid $SRV start $(date +%T)"

UP=0
for i in $(seq 1 240); do
  if curl -s http://127.0.0.1:8098/health 2>/dev/null | grep -q '"ok"'; then UP=1; break; fi
  if ! kill -0 $SRV 2>/dev/null; then echo "[$TAG] SERVER DIED"; tail -5 "$TAG-server.log"; exit 1; fi
  sleep 2
done
if [ "$UP" != "1" ]; then echo "[$TAG] TIMEOUT waiting for health"; kill $SRV 2>/dev/null; exit 1; fi
echo "[$TAG] server up $(date +%T)"

curl -s http://127.0.0.1:8098/v1/chat/completions -H 'Content-Type: application/json' \
  -d @/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/correctness-prompt.json > "$TAG.json"
echo "[$TAG] generation done $(date +%T)"

kill $SRV 2>/dev/null
sleep 3
kill -9 $SRV 2>/dev/null
python3 - "$TAG" <<'PYEOF'
import json, sys
tag = sys.argv[1]
try:
    d = json.load(open(f"{tag}.json"))
    txt = d["choices"][0]["message"]["content"]
    print(f"[{tag}] OUTPUT-BEGIN")
    print(txt)
    print(f"[{tag}] OUTPUT-END")
except Exception as e:
    print(f"[{tag}] PARSE-FAIL {e}")
PYEOF
