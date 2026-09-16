#!/usr/bin/env bash
cd /home/revn/strix-llama
echo "=== MMB env reading in mmb.cu ==="
grep -n 'getenv' ggml/src/ggml-cuda/mmb.cu | head -20
echo "=== total LLAMA_ getenv in ggml-cuda ==="
grep -rn 'getenv("LLAMA_' ggml/src/ggml-cuda/ | wc -l
echo "=== ac1ebb4e0 stat ==="
git show ac1ebb4e0 --stat | head -25
echo "=== ac1ebb4e0 removes how many getenv? ==="
git show ac1ebb4e0 | grep -c '^-.*getenv'
git show ac1ebb4e0 | grep -c '^+.*getenv'
