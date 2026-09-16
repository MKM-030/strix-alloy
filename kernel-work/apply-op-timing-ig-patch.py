#!/usr/bin/env python3
"""In-graph per-op event timing for the strix-halo fork.
Events recorded during graph capture become graph nodes: replay re-emits them at
no host cost, and post-sync queries give a per-op GPU split of gpu_wait.
LLAMA_OP_TIMING=2 activates; LLAMA_OP_TIMING_OPS filters (substring match on
"opname tensorname"). Events are intentionally kept alive for the process
lifetime (they are referenced by the instantiated graph)."""
import sys

path = "ggml/src/ggml-cuda/ggml-cuda.cu"
src = open(path).read()
if "OP_TIMING_IG" in src:
    print("already patched")
    sys.exit(0)

state = r'''
// [OP_TIMING_IG] in-graph per-op event timing (LLAMA_OP_TIMING=2, graphs ON).
// During capture, event pairs are recorded around selected ops; the events become
// graph nodes, so every replay re-emits them and post-sync queries yield the
// per-op GPU time of that replay. Events are kept alive for the process lifetime:
// the instantiated graph references them.
namespace op_timing_ig {
struct Seg { std::string op; int64_t layer; cudaEvent_t a, b; };
static inline bool enabled() {
    static const bool e = getenv("LLAMA_OP_TIMING") && atoi(getenv("LLAMA_OP_TIMING")) == 2;
    return e;
}
static bool op_selected(const ggml_tensor * node) {
    const char * f = getenv("LLAMA_OP_TIMING_OPS");
    std::string filters = f ? f : "mul_mat_id,ssm,gated_delta,flash_attn,get_rows,top_k,moe,softmax,rope";
    const std::string nm = std::string(ggml_op_name(node->op)) + " " + node->name;
    size_t start = 0;
    while (start <= filters.size()) {
        size_t comma = filters.find(',', start);
        std::string tok = filters.substr(start, comma == std::string::npos ? std::string::npos : comma - start);
        if (!tok.empty() && nm.find(tok) != std::string::npos) {
            return true;
        }
        if (comma == std::string::npos) {
            break;
        }
        start = comma + 1;
    }
    return false;
}
static int64_t layer_of(const ggml_tensor * t) {
    for (const ggml_tensor * x = t; x; x = x->src[0]) {
        const char * c = strstr(x->name, "blk.");
        if (c) {
            return atoll(c + 4);
        }
    }
    return -1;
}
struct Agg { double us = 0; long long n = 0; };
static std::unordered_map<std::string, Agg> agg;
static std::vector<Seg> segs;

static void begin_capture_hook() { segs.clear(); }  // fresh capture: new event set below

static void record(cudaStream_t stream, const ggml_tensor * node) {
    cudaEvent_t a, b;
    CUDA_CHECK(cudaEventCreate(&a));
    CUDA_CHECK(cudaEventCreate(&b));
    CUDA_CHECK(cudaEventRecord(a, stream));
    segs.push_back({ggml_op_name(node->op), layer_of(node), a, b});
    CUDA_CHECK(cudaEventRecord(b, stream));
}

// call after each pure-replay graph launch + stream sync
static void collect() {
    for (auto & s : segs) {
        float ms = 0;
        if (cudaEventElapsedTime(&ms, s.a, s.b) != hipSuccess) {
            continue;
        }
        auto & a = agg[s.op + "|" + (s.layer < 0 ? std::string("none") : std::to_string(s.layer))];
        a.us += ms * 1000.0;
        a.n += 1;
    }
    static int64_t evals = 0;
    if (++evals % 8 == 0) {
        double total = 0;
        for (auto & kv : agg) {
            total += kv.second.us;
        }
        fprintf(stderr, "OP_TIMING_IG after %lld replays: tracked total %.1f ms/replay\n",
                (long long) evals, total / 8.0);
        std::vector<std::pair<std::string, Agg *>> rows;
        for (auto & kv : agg) {
            rows.push_back({kv.first, &kv.second});
        }
        std::sort(rows.begin(), rows.end(), [](auto & x, auto & y) { return x.second->us > y.second->us; });
        for (size_t r = 0; r < rows.size() && r < 36; r++) {
            fprintf(stderr, "  %-28s n=%-7lld total=%10.1fms avg=%8.1fus\n", rows[r].first.c_str(),
                    rows[r].second->n, rows[r].second->us / 1000.0, rows[r].second->us / rows[r].second->n);
        }
        fflush(stderr);
        agg.clear();
    }
}
} // namespace op_timing_ig

'''
anchor1 = "static void ggml_cuda_graph_evaluate_and_capture(ggml_backend_cuda_context * cuda_ctx"
assert anchor1 in src, "anchor1 missing"
src = src.replace(anchor1, state + anchor1, 1)

old_call = """                if (op_timing::enabled() && !use_cuda_graph) {
                    op_timing::record(cuda_ctx->stream(), node);
                }
                bool ok = ggml_cuda_compute_forward(*cuda_ctx, node);"""
new_call = """                if (op_timing::enabled() && !use_cuda_graph) {
                    op_timing::record(cuda_ctx->stream(), node);
                }
                if (use_cuda_graph && cuda_graph_update_required && op_timing_ig::enabled()
                        && op_timing_ig::op_selected(node)) {
                    op_timing_ig::record(cuda_ctx->stream(), node);
                }
                bool ok = ggml_cuda_compute_forward(*cuda_ctx, node);"""
assert old_call in src, "anchor2 missing (needs op-timing branch applied first)"
src = src.replace(old_call, new_call, 1)

old_capture_begin = """        CUDA_CHECK(cudaStreamBeginCapture(cuda_ctx->stream(), cudaStreamCaptureModeRelaxed));
    }"""
new_capture_begin = """        op_timing_ig::begin_capture_hook();
        CUDA_CHECK(cudaStreamBeginCapture(cuda_ctx->stream(), cudaStreamCaptureModeRelaxed));
    }"""
assert old_capture_begin in src, "anchor3 missing"
src = src.replace(old_capture_begin, new_capture_begin, 1)

old_launch = """        // Launch graph
        CUDA_CHECK(cudaGraphLaunch(graph->instance, cuda_ctx->stream()));"""
new_launch = """        // Launch graph
        CUDA_CHECK(cudaGraphLaunch(graph->instance, cuda_ctx->stream()));
        if (op_timing_ig::enabled() && !cuda_graph_update_required) {
            CUDA_CHECK(cudaStreamSynchronize(cuda_ctx->stream()));
            op_timing_ig::collect();
        }"""
assert old_launch in src, "anchor4 missing"
src = src.replace(old_launch, new_launch, 1)

open(path, "w").write(src)
print("patched OK")
