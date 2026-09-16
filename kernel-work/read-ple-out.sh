#!/usr/bin/env bash
for f in ir-il-prefill-ub16k.err ir-il-mtp-n2.err ir-il-prefill-ub16k.out ir-il-mtp-n2.out; do
  p="/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/$f"
  echo "=== $f ==="
  if [ -f "$p" ]; then
    n=$(grep -ac 'PLE_TIMING' "$p" 2>/dev/null || true)
    echo "  PLE_TIMING lines: ${n:-0}   (bytes: $(wc -c < "$p"))"
    grep -a 'PLE_TIMING' "$p" 2>/dev/null | tail -6 || true
  else
    echo "  missing"
  fi
done
echo
echo "=== any PLE_TIMING anywhere in results? ==="
grep -ral 'PLE_TIMING' /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/results/ 2>/dev/null | head
