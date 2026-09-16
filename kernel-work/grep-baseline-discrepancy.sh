#!/usr/bin/env bash
cd /mnt/c/Projects/REV-N-ornith-eval-20260911/docs/benchmarks
echo "=== docs mentioning 32.9 / 33.0 / 33 t/s ==="
grep -rn '32\.9\|33\.0\|33 t/s\|~33' *.md 2>/dev/null | head -20
echo
echo "=== docs mentioning 30.2 / 30.3 at 16k ==="
grep -rn '30\.2\|30\.3' *.md 2>/dev/null | head -20
echo
echo "=== all decode @16k figures ==="
grep -rn '16k' *.md 2>/dev/null | grep -iE 'decode|t/s' | head -25
