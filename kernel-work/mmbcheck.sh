#!/usr/bin/env bash
# mmbcheck.sh — did the MMB (bf16-WMMA dequant GEMM) kernels actually fire?
D=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results
for f in server-pf-mmb1.log server-pf-pw-ub8k.log server-W2-pf-ub8k-mmb.log server-ud-mmb-full.log server-W2-ud-ub8k-mmb.log; do
  p="$D/$f"
  printf '=== %s : ' "$f"
  if [ ! -f "$p" ]; then echo "MISSING"; continue; fi
  echo "$(wc -l < "$p") lines"
  grep -aE 'MMB_TALL|MMB_GLU|MMB_BLK16|MMB_DOWN16|HC_GATEMIX|MMB_SHADOW|MMB_CVT|FORK_COMPACT|FORK_GDN' "$p" | head -8
done
