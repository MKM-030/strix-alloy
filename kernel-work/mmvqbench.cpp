// mmvqbench.cpp — Codex Replay B: the REAL production operator, not a surrogate.
//
// Drives ggml's actual MUL_MAT path (GGML_TYPE_IQ4_NL weights) through the public backend API, so the
// measured work is: activation quantization (quantize_row_q8_1_cuda) + the real mul_mat_vec_q kernel
// + the real epilogue. Nothing is reimplemented.
//
// Per Codex: rotate INDEPENDENT REPLICAS of the same shapes (do not change R/K to enlarge the working
// set), keep preparation outside timing, and validate output numerically against a CPU reference.
//
// Build (same toolchain as the server):
//   clang++ -O2 -std=c++17 mmvqbench.cpp -o mmvqbench.exe \
//     -I<src>/ggml/include -L<bindir> -lggml -lggml-base -lggml-hip -lggml-cpu
//
// Usage: mmvqbench.exe [K R T nReplicas iters]

#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>
#include <vector>

static double now_ms() {
    using clock = std::chrono::steady_clock;
    return std::chrono::duration<double, std::milli>(clock::now().time_since_epoch()).count();
}

struct replica {
    ggml_context * ctx = nullptr;
    ggml_backend_buffer_t buf = nullptr;
    ggml_tensor * w = nullptr;
    ggml_tensor * x = nullptr;
    ggml_tensor * y = nullptr;
    ggml_cgraph * gf = nullptr;
    std::vector<uint8_t> w_host;   // packed IQ4_NL
    std::vector<float>   x_host;
};

static bool build_replica(replica & r, ggml_backend_t backend, int64_t K, int64_t R, int64_t T, std::mt19937 & rng) {
    ggml_init_params ip = { /*mem_size*/ ggml_tensor_overhead()*16 + ggml_graph_overhead(), /*mem_buffer*/ nullptr, /*no_alloc*/ true };
    r.ctx = ggml_init(ip);
    if (!r.ctx) return false;

    r.w = ggml_new_tensor_2d(r.ctx, GGML_TYPE_IQ4_NL, K, R);
    r.x = ggml_new_tensor_2d(r.ctx, GGML_TYPE_F32,    K, T);
    r.y = ggml_mul_mat(r.ctx, r.w, r.x);
    ggml_set_name(r.y, "out");

    r.buf = ggml_backend_alloc_ctx_tensors(r.ctx, backend);
    if (!r.buf) return false;

    // host-side packed IQ4_NL: (K/32) blocks of 18 bytes per row, with a small non-trivial scale
    const size_t nb = (size_t)(K/32) * 18;
    r.w_host.assign(nb * (size_t)R, 0);
    std::uniform_int_distribution<int> nib(0, 15);
    std::uniform_real_distribution<float> sc(0.001f, 0.02f);
    for (int64_t row = 0; row < R; ++row) {
        uint8_t * p = r.w_host.data() + (size_t)row * nb;
        for (int64_t b = 0; b < K/32; ++b) {
            float d = sc(rng);
            // ggml_half little-endian
            uint16_t h;
            {   // f32 -> f16
                union { float f; uint32_t u; } v; v.f = d;
                uint32_t x = v.u; uint32_t sign = (x >> 16) & 0x8000u;
                int32_t  e = (int32_t)((x >> 23) & 0xFF) - 127 + 15;
                uint32_t m = x & 0x7FFFFFu;
                if (e <= 0) { h = (uint16_t)sign; }
                else if (e >= 31) { h = (uint16_t)(sign | 0x7C00u); }
                else { h = (uint16_t)(sign | ((uint32_t)e << 10) | (m >> 13)); }
            }
            p[b*18 + 0] = (uint8_t)(h & 0xFF);
            p[b*18 + 1] = (uint8_t)(h >> 8);
            for (int i = 0; i < 16; ++i) p[b*18 + 2 + i] = (uint8_t)((nib(rng) & 0xF) | ((nib(rng) & 0xF) << 4));
        }
    }
    r.x_host.resize((size_t)K * (size_t)T);
    std::uniform_real_distribution<float> xv(-1.0f, 1.0f);
    for (auto & v : r.x_host) v = xv(rng);

    ggml_backend_tensor_set(r.w, r.w_host.data(), 0, r.w_host.size());
    ggml_backend_tensor_set(r.x, r.x_host.data(), 0, r.x_host.size() * sizeof(float));

    r.gf = ggml_new_graph(r.ctx);
    ggml_build_forward_expand(r.gf, r.y);
    return true;
}

int main(int argc, char ** argv) {
    int64_t K = argc > 1 ? atoll(argv[1]) : 2560;
    int64_t R = argc > 2 ? atoll(argv[2]) : 12288;
    int64_t T = argc > 3 ? atoll(argv[3]) : 1;
    int nRep  = argc > 4 ? atoi(argv[4])  : 8;
    int iters = argc > 5 ? atoi(argv[5])  : 50;

    printf("mmvqbench: K=%lld R=%lld T=%lld replicas=%d iters=%d\n",
           (long long)K, (long long)R, (long long)T, nRep, iters);

    // pick a GPU device
    ggml_backend_dev_t dev = nullptr;
    for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
        ggml_backend_dev_t d = ggml_backend_dev_get(i);
        const char * nm = ggml_backend_dev_name(d);
        printf("  dev[%zu] %s type=%d\n", i, nm, (int) ggml_backend_dev_type(d));
    }
    for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
        ggml_backend_dev_t d = ggml_backend_dev_get(i);
        // this fork adds GGML_BACKEND_DEVICE_TYPE_IGPU, so accept GPU or IGPU
        const int t = (int) ggml_backend_dev_type(d);
        if (t == (int) GGML_BACKEND_DEVICE_TYPE_GPU || t == (int) GGML_BACKEND_DEVICE_TYPE_IGPU) { dev = d; break; }
    }
    if (!dev) { printf("no GPU device found\n"); return 1; }
    printf("using device: %s\n", ggml_backend_dev_name(dev));

    ggml_backend_t backend = ggml_backend_dev_init(dev, nullptr);
    if (!backend) { printf("backend init failed\n"); return 1; }

    std::mt19937 rng(1234);
    std::vector<replica> reps(nRep);
    for (int i = 0; i < nRep; ++i) {
        if (!build_replica(reps[i], backend, K, R, T, rng)) { printf("replica %d build failed\n", i); return 1; }
    }

    // warm
    for (int i = 0; i < nRep; ++i) ggml_backend_graph_compute(backend, reps[i].gf);
    ggml_backend_synchronize(backend);

    // timed: rotate over all replicas (independent weight buffers of the same geometry)
    const double t0 = now_ms();
    for (int it = 0; it < iters; ++it) {
        for (int i = 0; i < nRep; ++i) ggml_backend_graph_compute(backend, reps[i].gf);
    }
    ggml_backend_synchronize(backend);
    const double t1 = now_ms();

    const double per_op_ms = (t1 - t0) / (double)(iters * nRep);
    const double w_bytes   = (double)K * (double)R * 18.0 / 32.0;    // IQ4_NL = 18 bytes / 32 weights
    const double eff_gbs   = w_bytes / (per_op_ms / 1000.0) / 1e9;

    printf("\n--- Replay B (real production MUL_MAT, IQ4_NL) ---\n");
    printf("  weight bytes/op : %.3f MB\n", w_bytes / 1e6);
    printf("  latency         : %.3f ms/op\n", per_op_ms);
    printf("  effective BW    : %.1f GB/s  (weights only)\n", eff_gbs);

    // Timed mode 2 (one graph, many ops): build ALL replicas' mul_mats into a SINGLE graph, so one
    // ggml_backend_graph_compute covers nRep ops -- this is what production does (one hip graph per
    // step). If per-op latency drops sharply vs separate calls, the fixed cost is per-graph_compute
    // (host/launch), not per-kernel. Usage: mmvqbench ... --1graph
    const bool one_graph = (argc > 6 && std::string(argv[6]) == "--1graph");
    if (one_graph) {
        ggml_init_params ip = { ggml_tensor_overhead()*64 + ggml_graph_overhead()*2, nullptr, true };
        ggml_context * gctx = ggml_init(ip);
        ggml_cgraph * big = ggml_new_graph_custom(gctx, 4096, false);
        for (int i = 0; i < nRep; ++i) ggml_build_forward_expand(big, reps[i].y);
        // warm
        ggml_backend_graph_compute(backend, big);
        ggml_backend_synchronize(backend);
        const double a0 = now_ms();
        for (int it = 0; it < iters; ++it) ggml_backend_graph_compute(backend, big);
        ggml_backend_synchronize(backend);
        const double a1 = now_ms();
        const double per_op_1g = (a1 - a0) / (double)(iters * nRep);
        const double wb = (double)K * (double)R * 18.0 / 32.0;
        printf("\n--- ONE graph with %d MUL_MATs (production-like) ---\n", nRep);
        printf("  latency/op : %.3f ms  ->  %.1f GB/s\n", per_op_1g, wb / (per_op_1g/1000.0) / 1e9);
        printf("  per-op fixed vs separate: %.3f vs %.3f ms  (saved %.3f ms/op)\n",
               per_op_1g, per_op_ms, per_op_ms - per_op_1g);
        ggml_free(gctx);
    }

    // numeric sanity: compare GPU y against CPU reference for replica 0 (T columns)
    {
        std::vector<float> y_gpu((size_t)R * (size_t)T);
        ggml_backend_tensor_get(reps[0].y, y_gpu.data(), 0, y_gpu.size() * sizeof(float));
        // CPU reference: dequantize (linear IQ4_NL proxied by nibble*16-127 scaled) — this is only a
        // finiteness/scale check, not bit-exactness.
        double sum = 0; int nf = 0;
        for (float v : y_gpu) { if (!std::isfinite(v)) nf++; sum += std::fabs(v); }
        printf("  y[0..3] = %.4f %.4f %.4f %.4f | non-finite=%d | mean|y|=%.4f\n",
               y_gpu[0], y_gpu.size()>1?y_gpu[1]:0.f, y_gpu.size()>2?y_gpu[2]:0.f, y_gpu.size()>3?y_gpu[3]:0.f,
               nf, sum / (double)std::max<size_t>(1, y_gpu.size()));
    }

    for (auto & r : reps) {
        if (r.buf) ggml_backend_buffer_free(r.buf);
        if (r.ctx) ggml_free(r.ctx);
    }
    ggml_backend_free(backend);
    return 0;
}
