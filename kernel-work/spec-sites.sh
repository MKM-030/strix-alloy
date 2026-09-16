#!/usr/bin/env bash
# spec-sites.sh — show receiver + line for every checkpoint call, to identify the SPEC ones.
F=/home/revn/strix-llama/tools/server/server-context.cpp
echo "=== all update_tgt/update_dft/load_tgt/load_dft calls ==="
grep -nE '\.(update_tgt|update_dft|load_tgt|load_dft)\(' "$F"
echo
echo "=== spec_ckpt mentions ==="
grep -n 'spec_ckpt' "$F" | head -30
