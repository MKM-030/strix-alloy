#!/usr/bin/env bash
# kernelmarkers.sh — list which fork kernels fired, per log.
for f in "$@"; do
  echo "=== $(basename "$f")"
  if [ ! -f "$f" ]; then echo "  (missing)"; continue; fi
  grep -oE 'FORK_[A-Z0-9_]+|MMB[A-Z0-9_]*|QSA_[A-Z0-9_]+|mmb_[a-z0-9_]+' "$f" 2>/dev/null | sort | uniq -c | sort -rn | head -15
  echo "  -- WMMA/gemm hints --"
  grep -icE 'wmma|bf16.*gemm|dequant.*gemm' "$f" 2>/dev/null
done
