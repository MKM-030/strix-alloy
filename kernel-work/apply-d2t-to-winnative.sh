#!/usr/bin/env bash
# apply-d2t-to-winnative.sh — port ONLY the d2t vocab-trim change onto win-native.
cd /home/revn/strix-llama || exit 1
git show 7c0b59f8 -- src/models/qwen4exp.cpp > /tmp/d2t-only.diff
echo "diff lines: $(wc -l < /tmp/d2t-only.diff)"
if git apply --check /tmp/d2t-only.diff 2>/tmp/d2t-apply.err; then
  git apply /tmp/d2t-only.diff
  echo "APPLIED"
  echo "d2t references now: $(grep -c 'd2t' src/models/qwen4exp.cpp)"
else
  echo "NEEDS MERGE; first errors:"
  head -8 /tmp/d2t-apply.err
fi
