#!/usr/bin/env python3
"""Correct fix for the MTP acceptance cliff: in graph_mtp ONLY, disable the sparse-query path so the
draft uses dense attention over the selected KV.

Why this and not use_block_selection: the draft's sparse selection is driven by `sparse_decode`
(n_tokens <= 8), which is true for the draft AND for the target's own decode step, so it cannot be
gated by ubatch there. But the block is inside graph_mtp, so disabling it affects only the draft.
The target's sparse decode lives in graph::build_layer_attn and is untouched.

Measured context: with sparse selection the draft's output disagrees with the target's for
n_kv > indexer_top_k + ratio - 1, collapsing acceptance to exactly 0 (8192 tokens: 0%, 13.2 t/s).
The hparam override that made everything dense fixed it but cost prefill; this keeps the target sparse.
Idempotent."""
import sys

F = "src/models/qwen4exp.cpp"
src = open(F).read()
if "// [DRAFT_DENSE_ATTN]" in src:
    print("already patched"); sys.exit(0)

old = """        ggml_tensor * top_k = nullptr;
        bool sparse_decode = false;
#if defined(GGML_USE_HIP)
        sparse_decode = n_tokens <= 8 && mctx_hyb->get_n_stream() == 1 &&
            cparams.flash_attn && cparams.offload_kqv && hparams.f_max_alibi_bias == 0.0f && !hparams.attn_soft_cap;
#endif"""
new = """        ggml_tensor * top_k = nullptr;
        bool sparse_decode = false;
#if defined(GGML_USE_HIP)
        sparse_decode = n_tokens <= 8 && mctx_hyb->get_n_stream() == 1 &&
            cparams.flash_attn && cparams.offload_kqv && hparams.f_max_alibi_bias == 0.0f && !hparams.attn_soft_cap;
#endif
        // [DRAFT_DENSE_ATTN] This is the MTP draft block. Past indexer_top_k+ratio-1 cached cells the
        // draft's sparse-selected attention no longer agrees with the target's, and acceptance collapses
        // to exactly zero (measured: 0% at 8192 tokens vs 70% dense). Keep the draft on dense attention;
        // the target's sparse decode path is in graph::build_layer_attn and is unaffected by this.
        sparse_decode = false;"""
assert old in src, "anchor not found"
src = src.replace(old, new, 1)
open(F, "w").write(src)
print("patched OK")
