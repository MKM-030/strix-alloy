#!/usr/bin/env bash
cd /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
for f in results/*.log results/*.err; do
  [ -f "$f" ] || continue
  if grep -q 'd2t\|frspec\|nextn\|65536' "$f" 2>/dev/null; then
    echo "### $f"
    grep -n 'd2t\|frspec\|nextn\|65536\|wrong shape\|ABORT\|GGML_ASSERT\|invalid' "$f" | head -10
    echo
  fi
done
