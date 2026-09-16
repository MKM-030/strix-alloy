#!/usr/bin/env bash
# make-frspec-head.sh — convert the FR-Spec 65k head into the fork's naming, on the Windows side.
SRC=/mnt/c/AI/models/qwen38-flash/drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf
OUT=/mnt/c/AI/models/qwen38-flash/projfix/mtp-frspec-65k-pwhead.gguf
python3 /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/convert-frspec-head.py "$SRC" "$OUT"
echo "--- verify the result parses and has the expected tensors ---"
cd /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
python3 - "$OUT" <<'PY'
import sys
sys.path.insert(0, '.')
from gguf_inventory import parse_shard, NAME2TYPE
s = parse_shard(sys.argv[1])
for t in s['tensors']:
    if 'nextn' in t['name'] or t['name'] in ('d2t','output.weight'):
        print(f"  {t['name']:42s} {NAME2TYPE.get(t['type'],t['type']):6s} ne={t['ne']}")
PY
