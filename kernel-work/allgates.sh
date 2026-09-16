#!/usr/bin/env bash
# allgates.sh — list every LLAMA_* env gate the fork reads.
cd /home/revn/strix-llama || exit 1
grep -rhoE 'getenv\("LLAMA_[A-Z0-9_]+"\)' ggml/src/ggml-cuda/ src/ common/ tools/ 2>/dev/null \
  | sed 's/getenv("//; s/")//' | sort -u
echo "--- count ---"
grep -rhoE 'getenv\("LLAMA_[A-Z0-9_]+"\)' ggml/src/ggml-cuda/ src/ common/ tools/ 2>/dev/null \
  | sed 's/getenv("//; s/")//' | sort -u | wc -l
