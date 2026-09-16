#!/usr/bin/env bash
for k in 10 5 3; do
  p="/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/ea-k$k.err"
  echo "=== expert_used_count=$k ==="
  if [ -f "$p" ]; then
    grep -a 'rounds:\|target_ms\|draft acceptance\|expert_used' "$p" | tail -5
  else
    echo "  (missing)"
  fi
done
