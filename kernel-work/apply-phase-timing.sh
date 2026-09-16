#!/usr/bin/env bash
# apply-phase-timing.sh — copy the instrumented server-context.cpp into the Windows tree and rebuild.
set -euo pipefail
SRC=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/src-server-context.cpp
DST=/mnt/c/AI/build/strix-llama-win/tools/server/server-context.cpp
echo "=== sanity: our edits present in the source ==="
grep -c 'g_t_tgt_decode_us' "$SRC"
grep -c 'phase: tgt_decode' "$SRC"
echo "=== back up the destination, then install ==="
cp "$DST" "$DST.bak-$(date +%s)" 2>/dev/null || true
cp "$SRC" "$DST"
echo "=== verify installed ==="
grep -c 'g_t_tgt_decode_us' "$DST"
grep -c 'phase: tgt_decode' "$DST"
echo "=== keep the WSL fork in sync too (so both trees match) ==="
cp "$SRC" /home/revn/strix-llama/tools/server/server-context.cpp
grep -c 'g_t_tgt_decode_us' /home/revn/strix-llama/tools/server/server-context.cpp
echo done
