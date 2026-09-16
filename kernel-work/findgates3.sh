#!/usr/bin/env bash
# findgates3.sh — find any file in the fork that exports many LLAMA_ gates.
cd /home/revn/strix-llama || exit 1
echo "=== files with LLAMA_ exports (count of lines) ==="
grep -rlE 'LLAMA_[A-Z0-9_]+=' --include='*.sh' --include='*.md' --include='*.txt' --include='*.json' \
  --include='*.yaml' --include='*.yml' --include='*.env' . 2>/dev/null | grep -v '/\.git/' | head -20
echo
echo "=== scripts dir listing ==="
ls scripts/ 2>/dev/null | head -20
echo
echo "=== any *.sh mentioning LLAMA_MMB ==="
grep -rl 'LLAMA_MMB' --include='*.sh' . 2>/dev/null | grep -v '/\.git/' | head
echo
echo "=== CMake: gates as compile options? ==="
grep -rnE 'LLAMA_(MMB|QSA|HC|GDN|NORM|PLE|IDX|MOE)' ggml/CMakeLists.txt ggml/src/ggml-hip/CMakeLists.txt CMakeLists.txt 2>/dev/null | head -20
