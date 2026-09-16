#!/usr/bin/env python3
"""Instrument llm_graph_input_ple::set_input() to measure the HOST-SIDE PLE cost.

WHY: Codex flagged (correctly, verified in source) that set_input() runs host-side inside
llama_decode and performs:
  * mctx->get_prev_tokens()      KV lookup
  * a host-side n-gram hash      (the comment: "ggml has no int64 and no xor")
  * ple_reader->gather()         257k-393k scattered reads ("~300 ms with the GPU idle")
  * ggml_backend_tensor_set()    host->device upload
So our "target verify" wall-clock includes host work, not only GPU execution.
This measures how much, split into: prev_tokens / hash / gather+upload.

MEASUREMENT ONLY: no behaviour change. Prints a summary every 32 calls.
"""
P = '/home/revn/strix-llama/src/models/qwen4exp.cpp'
src = open(P, encoding='utf-8').read()

# 1. file-scope accumulators, placed just before the class
anchor = "// PLE n-gram hash embedding: each token gathers ple_n_heads rows of a shared table."
assert src.count(anchor) == 1, f'class anchor count={src.count(anchor)}'
counters = """// [PLE_TIMING] measurement-only: host-side PLE staging cost inside llama_decode.
// set_input() does KV lookup + a host hash + a scattered gather + a host->device upload,
// all on the host thread, so this is NOT GPU time.
namespace ple_timing {
static int64_t t_prev = 0, t_hash = 0, t_gather = 0, t_upload = 0;
static int64_t n_calls = 0, n_tokens_total = 0;
static void report() {
    static int64_t last = 0;
    if (++n_calls - last < 32) { return; }
    last = n_calls;
    const double tot = (t_prev + t_hash + t_gather + t_upload) / 1000.0;
    fprintf(stderr,
        "[PLE_TIMING] calls=%lld tokens=%lld  prev=%.1f ms  hash=%.1f ms  gather=%.1f ms  "
        "upload=%.1f ms  | host-total=%.1f ms\\n",
        (long long) n_calls, (long long) n_tokens_total,
        t_prev/1000.0, t_hash/1000.0, t_gather/1000.0, t_upload/1000.0, tot);
    fflush(stderr);
}
} // namespace ple_timing

"""
src = src.replace(anchor, counters + anchor, 1)

# 2. time each phase inside set_input
old = """    // predecessors come from the KV cells (ext.tok); apply_ubatch() already stored this ubatch, so its own tokens count too
    mctx->get_prev_tokens(*ubatch, n_prev, prev);

    for (int64_t i = 0; i < n_tokens; ++i) {"""
new = """    // predecessors come from the KV cells (ext.tok); apply_ubatch() already stored this ubatch, so its own tokens count too
    const int64_t t0 = ggml_time_us();
    mctx->get_prev_tokens(*ubatch, n_prev, prev);
    const int64_t t1 = ggml_time_us();

    for (int64_t i = 0; i < n_tokens; ++i) {"""
assert src.count(old) == 1, f'prev anchor={src.count(old)}'
src = src.replace(old, new, 1)

old = """    if (pmodel.ple_reader) {
        staging.resize(idx.size() * pmodel.ple_reader->head_dim * sizeof(float));
        pmodel.ple_reader->gather(idx.data(), (int64_t) idx.size(), (float *) staging.data());
        ggml_backend_tensor_set(data, staging.data(), 0, staging.size());
    } else {
        ggml_backend_tensor_set(rows, idx.data(), 0, idx.size()*ggml_element_size(rows));
    }
}"""
new = """    const int64_t t2 = ggml_time_us();

    if (pmodel.ple_reader) {
        staging.resize(idx.size() * pmodel.ple_reader->head_dim * sizeof(float));
        pmodel.ple_reader->gather(idx.data(), (int64_t) idx.size(), (float *) staging.data());
        const int64_t t3 = ggml_time_us();
        ggml_backend_tensor_set(data, staging.data(), 0, staging.size());
        const int64_t t4 = ggml_time_us();
        ple_timing::t_gather += t3 - t2;
        ple_timing::t_upload += t4 - t3;
    } else {
        ggml_backend_tensor_set(rows, idx.data(), 0, idx.size()*ggml_element_size(rows));
        ple_timing::t_upload += ggml_time_us() - t2;
    }

    ple_timing::t_prev += t1 - t0;
    ple_timing::t_hash += t2 - t1;
    ple_timing::n_tokens_total += n_tokens;
    ple_timing::report();
}"""
assert src.count(old) == 1, f'tail anchor={src.count(old)}'
src = src.replace(old, new, 1)

open(P, 'w', encoding='utf-8').write(src)
print('patched OK')
print('  ple_timing refs:', src.count('ple_timing::'))
print('  ggml_time_us in set_input:', src.count('const int64_t t0 = ggml_time_us();'))
