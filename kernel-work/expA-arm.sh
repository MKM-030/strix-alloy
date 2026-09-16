#!/usr/bin/env bash
# One experiment-A arm per invocation, from the Windows driver.
# usage: expA-arm.sh <tag> <envs-string> [llama-bench flags...]
# Pre-flight: drop page caches (previous arm + download cache), abort if RAM too low.
source /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/env.sh
export HSA_ENABLE_DXG_DETECTION=1 
TAG="$1"; ENVS="$2"; shift 2
BIN=/home/revn/strix-llama/build-hip/bin/llama-bench
M="${BENCH_MODEL:-/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf}"
OUT=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/expA
mkdir -p "$OUT"
cd "$OUT"

sync
sudo /sbin/sysctl -q -w vm.drop_caches=3 >/dev/null 2>&1 || sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
sleep 2
AVAIL=$(free -g | awk '/^Mem:/{print $7}')
echo "=== [$TAG] start $(date +%T) avail=${AVAIL}G ===" | tee -a expA.log
if [ "$AVAIL" -lt 55 ]; then
  echo "=== [$TAG] ABORT: only ${AVAIL}G available (need >=55G) ===" | tee -a expA.log
  exit 2
fi

env $ENVS "$BIN" -m "$M" -ngl 99 -fa 1 -t 8 "$@" > "expA-$TAG.log" 2>&1
RC=$?
echo "=== [$TAG] exit=$RC $(date +%T) ===" | tee -a expA.log
tail -3 "expA-$TAG.log" | sed "s/^/[$TAG] /"
exit $RC
