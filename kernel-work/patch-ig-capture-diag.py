#!/usr/bin/env python3
"""Decisive diagnostic for the in-graph timer.

record_calls is still 0 after the case-insensitivity fix, so the failing condition is NOT
op_selected alone. Add counters that distinguish:
  * how many times the node loop ran with (use_cuda_graph && update_required)
  * how many nodes were seen there, and how many op_selected matched
  * what the first few op-name strings actually look like
Printed once, a few evals in.
"""
P = '/home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu'
src = open(P, encoding='utf-8').read()

# counters next to the existing diagnostics
old = """static long long rec_calls = 0;          // diagnostics: how many record() calls happened
static long long collect_calls = 0;      // diagnostics: how many collect() calls happened"""
new = """static long long rec_calls = 0;          // diagnostics: how many record() calls happened
static long long collect_calls = 0;      // diagnostics: how many collect() calls happened
static long long cap_loop_calls = 0;     // diagnostics: node loop ran with update_required
static long long cap_nodes_seen = 0;     // diagnostics: nodes examined during capture
static long long cap_matches = 0;        // diagnostics: op_selected() returned true
static std::string cap_sample;           // diagnostics: first few op names seen"""
assert src.count(old) == 1
src = src.replace(old, new)

# instrument the node loop: count and sample
old = """                if (use_cuda_graph && cuda_graph_update_required && op_timing_ig::enabled()
                        && op_timing_ig::op_selected(node)) {
                    op_timing_ig::record(cuda_ctx->stream(), node);
                }"""
new = """                if (use_cuda_graph && cuda_graph_update_required) {
                    ++op_timing_ig::cap_nodes_seen;
                    if (op_timing_ig::cap_sample.size() < 200) {
                        op_timing_ig::cap_sample += std::string(ggml_op_name(node->op)) + ",";
                    }
                    if (op_timing_ig::enabled() && op_timing_ig::op_selected(node)) {
                        ++op_timing_ig::cap_matches;
                        op_timing_ig::record(cuda_ctx->stream(), node);
                    }
                }"""
assert src.count(old) == 1
src = src.replace(old, new)

# count how often the capture branch is entered
old = """        op_timing_ig::begin_capture_hook();
        CUDA_CHECK(cudaStreamBeginCapture(cuda_ctx->stream(), cudaStreamCaptureModeRelaxed));"""
new = """        op_timing_ig::begin_capture_hook();
        ++op_timing_ig::cap_loop_calls;
        CUDA_CHECK(cudaStreamBeginCapture(cuda_ctx->stream(), cudaStreamCaptureModeRelaxed));"""
assert src.count(old) == 1
src = src.replace(old, new)

# extend the one-time diagnostic
old = """        fprintf(stderr,
            "OP_TIMING_IG DIAG: record_calls=%lld collect_calls=%lld segs=%zu\\n",
            (long long) rec_calls, (long long) collect_calls, segs.size());"""
new = """        fprintf(stderr,
            "OP_TIMING_IG DIAG: record_calls=%lld collect_calls=%lld segs=%zu cap_branch=%lld "
            "cap_nodes=%lld matches=%lld\\n",
            (long long) rec_calls, (long long) collect_calls, segs.size(),
            (long long) cap_loop_calls, (long long) cap_nodes_seen, (long long) cap_matches);
        fprintf(stderr, "OP_TIMING_IG DIAG sample ops: %s\\n", cap_sample.c_str());
        fprintf(stderr, "OP_TIMING_IG DIAG filter env: %s\\n",
            getenv("LLAMA_OP_TIMING_OPS") ? getenv("LLAMA_OP_TIMING_OPS") : "(unset)");"""
assert src.count(old) == 1
src = src.replace(old, new)

open(P, 'w', encoding='utf-8').write(src)
print('patched OK')
print('  cap_nodes_seen refs:', src.count('cap_nodes_seen'))
print('  cap_sample refs    :', src.count('cap_sample'))
