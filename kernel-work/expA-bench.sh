#!/usr/bin/env bash
# Experiment A: graph on/off A/B on Flash-Next UD-IQ4_XS with the strix-halo fork.
# Sequential configs, fresh process (fresh load) each. One heavy job at a time.
source /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/env.sh
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1

BIN=/home/revn/strix-llama/build-hip/bin/llama-bench
M=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
OUT=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/expA
mkdir -p "$OUT"
cd "$OUT"

run() {
  local tag="$1"; local envs="$2"; shift 2
  echo "=== [$tag] start $(date +%T) ===" >> expA.log
  env $envs "$BIN" -m "$M" -ngl 99 -fa 1 -t 8 "$@" >> "expA-$tag.log" 2>&1
  echo "=== [$tag] exit=$? $(date +%T) ===" >> expA.log
}

run on-p0   ""                                              -p 0    -n 128 -r 3
run off-p0  "GGML_CUDA_DISABLE_GRAPHS=1"                    -p 0    -n 128 -r 3
run on-t    "LLAMA_GRAPH_TIMING=1 LLAMA_GRAPH_DIAG=1"       -p 0    -n 64  -r 1
run off-t   "LLAMA_GRAPH_TIMING=1 GGML_CUDA_DISABLE_GRAPHS=1" -p 0  -n 64  -r 1
run on-p2k  ""                                              -p 2048 -n 128 -r 3
run off-p2k "GGML_CUDA_DISABLE_GRAPHS=1"                    -p 2048 -n 128 -r 3

echo "ALL DONE $(date +%T)" >> expA.log
