#!/usr/bin/env python3
"""Apply the LLAMA_OP_TIMING instrumentation patch to ggml/src/ggml-cuda/ggml-cuda.cu.
Run from the fork root on the op-timing branch. Idempotent: skips if already applied."""
import sys

path = "ggml/src/ggml-cuda/ggml-cuda.cu"
src = open(path).read()
if "OP_TIMING" in src:
    print("already patched")
    sys.exit(0)

# 1) instrumentation helpers, inserted right before ggml_cuda_graph_evaluate_and_capture
helpers = r'''
// [OP_TIMING] per-op attribution with event pairs. Requires GGML_CUDA_DISABLE_GRAPHS=1
// (event pairs around each op would perturb capture otherwise). Aggregates by
// (op name, layer parsed from the tensor name) over graph evaluations and prints
// a summary every LLAMA_OP_TIMING_EVERY evals (default 16).
namespace op_timing {
struct Agg { double us = 0; long long n = 0; double bytes = 0; };
struct Pending {
    cudaEvent_t a, b;
    std::string op;
    int64_t layer;
    size_t bytes;
};
static inline bool enabled() {
    static const bool e = getenv("LLAMA_OP_TIMING") && atoi(getenv("LLAMA_OP_TIMING"));
    return e;
}
static std::unordered_map<std::string, Agg> agg;
static std::vector<Pending> pending;
static std::vector<cudaEvent_t> ev;
static int64_t ev_i = 0;

static void ev_ensure(int64_t n) {
    while ((int64_t) ev.size() < 2 * n + 2) {
        cudaEvent_t e;
        CUDA_CHECK(cudaEventCreate(&e));
        ev.push_back(e);
    }
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
static void record(cudaStream_t stream, const ggml_tensor * node) {
    ev_ensure(ev_i + 1);
    cudaEvent_t a = ev[ev_i++];
    cudaEvent_t b = ev[ev_i++];
    CUDA_CHECK(cudaEventRecord(a, stream));
    pending.push_back({a, b, ggml_op_name(node->op), layer_of(node), ggml_nbytes(node)});
    CUDA_CHECK(cudaEventRecord(b, stream));
}
static void flush(cudaStream_t stream) {
    if (pending.empty()) {
        return;
    }
    CUDA_CHECK(cudaStreamSynchronize(stream));
    for (auto & p : pending) {
        float ms = 0;
        CUDA_CHECK(cudaEventElapsedTime(&ms, p.a, p.b));
        auto & a = agg[p.op + "|" + (p.layer < 0 ? std::string("none") : std::to_string(p.layer))];
        a.us += ms * 1000.0;
        a.n += 1;
        a.bytes += p.bytes;
    }
    pending.clear();
    ev_i = 0;
    static int64_t ot_evals = 0;
    ++ot_evals;
    const int64_t every = getenv("LLAMA_OP_TIMING_EVERY") ? atoll(getenv("LLAMA_OP_TIMING_EVERY")) : 16;
    if (ot_evals % every == 0) {
        fprintf(stderr, "OP_TIMING aggregate after %lld evals (op|layer count total_ms avg_us):\n",
                (long long) ot_evals);
        std::vector<std::pair<std::string, Agg *>> rows;
        for (auto & kv : agg) {
            rows.push_back({kv.first, &kv.second});
        }
        std::sort(rows.begin(), rows.end(), [](auto & x, auto & y) { return x.second->us > y.second->us; });
        for (size_t r = 0; r < rows.size() && r < 40; r++) {
            fprintf(stderr, "  %-24s n=%-7lld total=%10.1fms avg=%8.1fus\n",
                    rows[r].first.c_str(), rows[r].second->n,
                    rows[r].second->us / 1000.0, rows[r].second->us / rows[r].second->n);
        }
        fflush(stderr);
    }
}
} // namespace op_timing

'''

anchor1 = "static void ggml_cuda_graph_evaluate_and_capture(ggml_backend_cuda_context * cuda_ctx"
assert anchor1 in src, "anchor1 missing"
src = src.replace(anchor1, helpers + anchor1, 1)

# 2) instrument the compute_forward call (only when not capturing)
old_call = """                bool ok = ggml_cuda_compute_forward(*cuda_ctx, node);"""
new_call = """                if (op_timing::enabled() && !use_cuda_graph) {
                    op_timing::record(cuda_ctx->stream(), node);
                }
                bool ok = ggml_cuda_compute_forward(*cuda_ctx, node);"""
assert old_call in src, "anchor2 missing"
src = src.replace(old_call, new_call, 1)

# 3) flush after direct evaluation completes
old_eval = """        } else {
            graph_evaluated_or_captured = true; // ggml graph has been directly evaluated
        }
    }"""
new_eval = """        } else {
            graph_evaluated_or_captured = true; // ggml graph has been directly evaluated
            if (op_timing::enabled()) {
                op_timing::flush(cuda_ctx->stream());
            }
        }
    }"""
assert old_eval in src, "anchor3 missing"
src = src.replace(old_eval, new_eval, 1)

open(path, "w").write(src)
print("patched OK")
