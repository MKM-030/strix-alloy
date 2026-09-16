#!/usr/bin/env bash
cd /home/revn/strix-llama || exit 1
echo "=== ggml_set_rows contract (ggml.c) ==="
grep -n "ggml_set_rows" -A 30 ggml/src/ggml.c | sed -n '1,45p'
