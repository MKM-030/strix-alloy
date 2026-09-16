#!/usr/bin/env python3
"""Port ggml-org/llama.cpp PR #28118 to the strix-halo fork:
keep SPECULATIVE recurrent-state checkpoints on-device (target+draft, update+load).
The prompt-history checkpoint (cur.update_*) stays host-backed, per the PR.
Idempotent."""
import re, sys

F = "tools/server/server-context.cpp"
src = open(F).read()
if "LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY | LLAMA_STATE_SEQ_FLAGS_ON_DEVICE" in src:
    print("already patched"); sys.exit(0)

# The 6 speculative sites: receivers are slot.spec_ckpt / ckpt (bound to slot.spec_ckpt)
#   slot.spec_ckpt.update_dft, ckpt.load_dft, ckpt.update_tgt, ckpt.update_dft,
#   ckpt.load_tgt, ckpt.load_dft
# NOTE: lines 2363/2364 (cur.update_tgt/update_dft = prompt-history checkpoint) must NOT change.
targets = [
    ("slot.spec_ckpt.update_dft(ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY);",
     "slot.spec_ckpt.update_dft(ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY | LLAMA_STATE_SEQ_FLAGS_ON_DEVICE);"),
    ("ckpt.load_dft(ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY);",
     "ckpt.load_dft(ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY | LLAMA_STATE_SEQ_FLAGS_ON_DEVICE);"),
    ("ckpt.update_tgt(ctx_tgt, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY);",
     "ckpt.update_tgt(ctx_tgt, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY | LLAMA_STATE_SEQ_FLAGS_ON_DEVICE);"),
    ("ckpt.update_dft(ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY);",
     "ckpt.update_dft(ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY | LLAMA_STATE_SEQ_FLAGS_ON_DEVICE);"),
    ("ckpt.load_tgt(slot.ctx_tgt, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY);",
     "ckpt.load_tgt(slot.ctx_tgt, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY | LLAMA_STATE_SEQ_FLAGS_ON_DEVICE);"),
    ("ckpt.load_dft(slot.ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY);",
     "ckpt.load_dft(slot.ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY | LLAMA_STATE_SEQ_FLAGS_ON_DEVICE);"),
]
n_applied = 0
for old, new in targets:
    c = src.count(old)
    if c == 0:
        print(f"  MISS: {old[:60]}")
        continue
    src = src.replace(old, new)
    n_applied += c
    print(f"  patched x{c}: {old[:60]}")

# safety: prompt-history sites must be untouched
assert "cur.update_tgt(ctx_tgt, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY);" in src, "prompt ckpt tgt altered!"
assert "cur.update_dft(ctx_dft, slot.id, LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY);" in src, "prompt ckpt dft altered!"

open(F, "w").write(src)
print(f"applied {n_applied} replacements; prompt-history sites preserved")
