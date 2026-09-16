#!/usr/bin/env bash
# iommu-ab.sh — measure whether disabling the guest IOMMU changes prefill/decode in WSL.
#
# Context: baldlawyer's Strix Halo result (amd_iommu=off -> +1.8..31.6% prefill) is a BARE-METAL
# Linux finding. This WSL guest boots paravirtualized on Hyper-V, so the "IOMMU" here is virtual;
# the test can only show whether the effect SURVIVES virtualisation, not reproduce the host effect.
#
# usage: iommu-ab.sh <tag>   (tag is recorded with the result)
set -u
BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
OUT="$BASE/results"; mkdir -p "$OUT"
TAG="${1:-run}"
source "$BASE/env.sh"
export HSA_ENABLE_DXG_DETECTION=1 HSA_OVERRIDE_GFX_VERSION=11.5.1

BIN=/home/revn/strix-llama/build-hip/bin/llama-bench
# smaller of the Flash-Next quantizations so each arm loads fast enough to repeat
MODEL=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
[ -f "$MODEL" ] || MODEL=/mnt/c/AI/models/qwen38-flash/unsloth-UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf

LOG="$OUT/iommu-$TAG.log"
{
  echo "==== iommu test: $TAG  $(date -Iseconds) ===="
  echo "cmdline: $(cat /proc/cmdline)"
  echo "grep iommu dmesg:"
  dmesg 2>/dev/null | grep -i iommu | head -4
  echo "model: $MODEL"
  echo "--- llama-bench -p 2048,8192 -n 128 -r 3 ---"
  "$BIN" -m "$MODEL" -ngl 99 -fa 1 -p 2048,8192 -n 128 -r 3 2>&1 | tail -25
} 2>&1 | tee "$LOG"
echo "saved $LOG"
