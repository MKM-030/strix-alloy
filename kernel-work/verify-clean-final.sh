#!/usr/bin/env bash
L=/mnt/c/AI/build/strix-llama-win/build-therock/bin/llama.dll
echo "llama.dll mtime: $(stat -c '%y' "$L" | cut -d. -f1)"
echo "PLE_TIMING in llama.dll: $(grep -ac 'PLE_TIMING' "$L" 2>/dev/null || echo 0)"
echo "OP_TIMING in llama.dll : $(grep -ac 'OP_TIMING' "$L" 2>/dev/null || echo 0)"
echo
echo "WSL fork clean?"
grep -c 'ple_timing' /home/revn/strix-llama/src/models/qwen4exp.cpp 2>/dev/null || echo 0
cd /home/revn/strix-llama
git status --short | head -5
echo "(empty above = clean)"
