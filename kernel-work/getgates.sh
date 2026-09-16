#!/usr/bin/env bash
# getgates.sh — download pwilkin's installer and list every env gate it sets.
cd /tmp || exit 1
curl -fsSL -o inst.sh https://raw.githubusercontent.com/pwilkin/strix-halo/main/install.sh
echo "size: $(wc -c < inst.sh)"
echo "=== LLAMA_ / export lines ==="
grep -nE 'LLAMA_|^ *export |STRIX_.*GATE' inst.sh | head -80
