#!/usr/bin/env bash
F=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/src-server-context.cpp
echo "target file: $F"
ls -la "$F"
echo "ON_DEVICE sites: $(grep -c ON_DEVICE "$F")"
echo "timing anchors:  $(grep -c 'g_t_tgt_decode_us' "$F")"
echo "phase print:     $(grep -c 'phase: tgt_decode' "$F")"
echo
echo "=== semantic diff vs current WSL fork (ignore the timing lines) ==="
strip() { grep -v -e 'g_t_' -e 'g_n_' -e 'g_p_' -e 'phase: tgt_decode' -e 't_ph' -e 'phase timing (measurement'; }
diff <(strip < /home/revn/strix-llama/tools/server/server-context.cpp) <(strip < "$F") && echo "IDENTICAL apart from the timing edit"
echo
echo "=== running flash/llama processes on the box? ==="
pgrep -a llama-server 2>/dev/null || echo "  none in WSL"
