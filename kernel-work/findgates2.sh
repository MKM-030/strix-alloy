#!/usr/bin/env bash
# findgates2.sh — locate the gate exports in pwilkin's installer (any launcher body).
cd /tmp || exit 1
[ -f inst.sh ] || curl -fsSL -o inst.sh https://raw.githubusercontent.com/pwilkin/strix-halo/main/install.sh
echo "=== all lines mentioning LLAMA_ (any form) ==="
grep -n 'LLAMA_' inst.sh | head -60
echo
echo "=== grep for a gates block (export or =1 lists) ==="
grep -nE 'LLAMA_[A-Z0-9_]+=' inst.sh | head -60
