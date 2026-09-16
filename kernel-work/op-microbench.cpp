// op-microbench.cpp — per-op decode-shape micro-benchmark for Flash-Next on gfx1151.
// Links the strix-halo fork's ggml libs; builds one compute graph per weight-carrying op family
// at Flash-Next decode shapes (batch-1, k=10), fills weights with random bytes (timing-valid,
// numerics-invalid by design), and wall-clocks synchronous iterations. No CUDA graphs, no model
// file, ~610 MB of weights total.
//
// Written 2026-09-13 without WSL access: UNVERIFIED. Smoke-test before trusting (runbook §8 step 4).
// Known risk: mul_mat_id src1/ids orientation mirrors build_moe_ffn's batch-1 case; if ggml asserts
// on shapes, read the assert, fix the orientation, re-run — timings are unaffected by which of the
// two orientations is used as long as ggml accepts it.
//
// Build:
//   hipcc -O2 -o op-microbench op-microbench.cpp \
//     -I/home/revn/strix-llama/ggml/include \
//     -L/home/revn/strix-llama/build-hip/bin -lggml -lggml-base -lggml-cpu -lggml-hip \
//     -Wl,-rpath,/home/revn/strix-llama/build-hip/bin
// Run:
//   ./op-microbench

#include "ggml.h"
#include "ggml-backend.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>

namespace {

std::mt19937 rng(1234);

void fill_random_bytes(ggml_backend_t backend, struct ggml_tensor * t) {
    const size_t nbytes = ggml_nbytes(t);
    std::vector<uint8_t> host(nbytes);
    for (size_t i = 0; i < nbytes; ++i) {
        host[i] = (uint8_t) (rng() & 0xFF);
    }
    ggml_backend_tensor_set(t, host.data(), 0, nbytes);
}

void fill_f32_const(ggml_backend_t backend, struct ggml_tensor * t, float v) {
    std::vector<float> host(ggml_nelements(t), v);
    ggml_backend_tensor_set(t, host.data(), 0, ggml_nbytes(t));
}

struct Result {
    const char * name;
    double us_per_iter;
    double mb_per_iter;
    double gb_per_s;
};

Result bench(const char * name, ggml_backend_t backend, struct ggml_context * cctx,
             struct ggml_tensor * op, double bytes_per_iter, int iters) {
    struct ggml_graph * gf = ggml_new_graph(cctx);
    ggml_build_forward_expand(gf, op);
    ggml_backend_graph_compute(backend, gf); // warmup + dispatch sanity

    const auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < iters; ++i) {
        ggml_backend_graph_compute(backend, gf);
    }
    const auto t1 = std::chrono::steady_clock::now();
    const double us = std::chrono::duration<double, std::micro>(t1 - t0).count() / iters;
    Result r{name, us, bytes_per_iter / 1e6, bytes_per_iter / (us * 1e-6) / 1e9};
    printf("%-20s %9.1f us/iter  %8.2f MB/iter  %7.1f GB/s effective\n", r.name, r.us_per_iter,
           r.mb_per_iter, r.gb_per_s);
    return r;
}

} // namespace

int main() {
    struct ggml_init_params ip = {
        /*.mem_size   =*/ 512ull * 1024 * 1024,
        /*.mem_buffer =*/ nullptr,
        /*.no_alloc   =*/ true,
    };
    struct ggml_context * wctx = ggml_init(ip); // weights
    struct ggml_context * cctx = ggml_init(ip); // activations + graphs
    if (!wctx || !cctx) {
        fprintf(stderr, "ggml_init failed\n");
        return 1;
    }
    ggml_backend_t backend = ggml_backend_cuda_init(0);
    if (!backend) {
        fprintf(stderr, "ggml_backend_cuda_init failed (check env: HSA_ENABLE_DXG_DETECTION=1 etc.)\n");
        return 1;
    }
    printf("op-microbench: backend=%s\n", ggml_backend_name(backend));

    const int K = 10; // expert_used_count

    // ---- weight tensors, Flash-Next decode shapes ----
    struct ggml_tensor * w_gate_up = ggml_new_tensor_3d(wctx, GGML_TYPE_IQ3_S, 2560, 640, 512);
    struct ggml_tensor * w_down_iq = ggml_new_tensor_3d(wctx, GGML_TYPE_IQ4_NL, 640, 2560, 512);
    struct ggml_tensor * w_down_q8 = ggml_new_tensor_3d(wctx, GGML_TYPE_Q8_0, 640, 2560, 512);
    struct ggml_tensor * w_qkv     = ggml_new_tensor_2d(wctx, GGML_TYPE_Q8_0, 2560, 10240);
    struct ggml_tensor * w_gate    = ggml_new_tensor_2d(wctx, GGML_TYPE_Q8_0, 2560, 6144);
    struct ggml_tensor * w_ssmout  = ggml_new_tensor_2d(wctx, GGML_TYPE_Q8_0, 6144, 2560);
    struct ggml_tensor * w_hc_up   = ggml_new_tensor_2d(wctx, GGML_TYPE_Q8_0, 320, 10240);
    struct ggml_tensor * w_hc_dn   = ggml_new_tensor_2d(wctx, GGML_TYPE_Q8_0, 10240, 320);
    struct ggml_tensor * w_router  = ggml_new_tensor_2d(wctx, GGML_TYPE_F32, 2560, 512);
    struct ggml_tensor * w_out     = ggml_new_tensor_2d(wctx, GGML_TYPE_Q6_K, 2560, 248320);

    // ---- activations (created before alloc; filled after) ----
    struct ggml_tensor * cur = ggml_new_tensor_2d(cctx, GGML_TYPE_F32, 2560, 1);   // hidden [2560,1]
    struct ggml_tensor * ids = ggml_new_tensor_2d(cctx, GGML_TYPE_I32, K, 1);      // [k,1] expert ids
    struct ggml_tensor * h   = ggml_new_tensor_2d(cctx, GGML_TYPE_F32, 640, K);    // per-expert interm.

    // allocate everything on the backend BEFORE any host->device copy
    if (ggml_backend_alloc_ctx_tensors(wctx, backend) == nullptr) {
        fprintf(stderr, "weight allocation failed\n");
        return 1;
    }
    if (ggml_backend_alloc_ctx_tensors(cctx, backend) == nullptr) {
        fprintf(stderr, "activation allocation failed\n");
        return 1;
    }

    struct ggml_tensor * weights[] = {w_gate_up, w_down_iq, w_down_q8, w_qkv, w_gate,
                                      w_ssmout, w_hc_up,   w_hc_dn,   w_router, w_out};
    double weight_total = 0;
    for (struct ggml_tensor * t : weights) {
        fill_random_bytes(backend, t);
        weight_total += ggml_nbytes(t);
        printf("filled %-10s %9.1f MB (%s)\n", "", ggml_nbytes(t) / 1e6, ggml_type_name(t->type));
    }
    printf("weights total: %.0f MB\n\n", weight_total / 1e6);

    fill_f32_const(backend, cur, 0.01f);
    fill_f32_const(backend, h, 0.01f);
    {
        std::vector<int32_t> ids_host(K);
        for (int i = 0; i < K; ++i) {
            ids_host[i] = i * 47 % 512;
        }
        ggml_backend_tensor_set(ids, ids_host.data(), 0, ggml_nbytes(ids));
    }

    std::vector<Result> results;
    const int iters = 100;

    // MoE gate+up: the model's mmvq fusion reads BOTH gate and up tensors in one launch.
    // This bench uses a single [2560,640,512] tensor per launch; count 2x (gate+up) per-expert bytes.
    {
        struct ggml_tensor * o = ggml_mul_mat_id(cctx, w_gate_up, cur, ids);
        results.push_back(bench("moe_gate_up", backend, cctx, o,
                                2.0 * ggml_nbytes(w_gate_up) * K / 512.0, iters));
    }
    {
        struct ggml_tensor * o = ggml_mul_mat_id(cctx, w_down_iq, h, ids);
        results.push_back(bench("moe_down_IQ4NL", backend, cctx, o,
                                ggml_nbytes(w_down_iq) * K / 512.0, iters));
    }
    {
        struct ggml_tensor * o = ggml_mul_mat_id(cctx, w_down_q8, h, ids);
        results.push_back(bench("moe_down_Q8", backend, cctx, o,
                                ggml_nbytes(w_down_q8) * K / 512.0, iters));
    }
    {
        struct ggml_tensor * o = ggml_mul_mat(cctx, w_qkv, cur);
        results.push_back(bench("attn_qkv", backend, cctx, o, ggml_nbytes(w_qkv), iters));
    }
    {
        struct ggml_tensor * o = ggml_mul_mat(cctx, w_gate, cur);
        results.push_back(bench("attn_gate", backend, cctx, o, ggml_nbytes(w_gate), iters));
    }
    {
        struct ggml_tensor * o = ggml_mul_mat(cctx, w_ssmout, cur);
        results.push_back(bench("ssm_out", backend, cctx, o, ggml_nbytes(w_ssmout), iters));
    }
    {
        struct ggml_tensor * a = ggml_mul_mat(cctx, w_hc_up, cur);
        struct ggml_tensor * b = ggml_mul_mat(cctx, w_hc_dn, a);
        results.push_back(bench("hc_up+down", backend, cctx, b,
                                ggml_nbytes(w_hc_up) + ggml_nbytes(w_hc_dn), iters));
    }
    {
        struct ggml_tensor * o = ggml_mul_mat(cctx, w_router, cur);
        results.push_back(bench("router_F32", backend, cctx, o, ggml_nbytes(w_router), iters));
    }
    {
        struct ggml_tensor * o = ggml_mul_mat(cctx, w_out, cur);
        results.push_back(bench("output_head", backend, cctx, o, ggml_nbytes(w_out), iters));
    }
    {
        // activation-side proxy for the expert intermediate (silu-mul, [640,k])
        struct ggml_tensor * s = ggml_silu(cctx, h);
        struct ggml_tensor * o = ggml_mul(cctx, s, h);
        results.push_back(bench("glu_f32", backend, cctx, o, 3.0 * ggml_nbytes(h), iters));
    }

    // ---- summary: predicted in-model weight time per token ----
    auto find = [&](const char * n) -> double {
        for (const Result & r : results) {
            if (strcmp(r.name, n) == 0) {
                return r.us_per_iter;
            }
        }
        return 0.0;
    };
    const double per_layer_dense = find("attn_qkv") + find("attn_gate") + find("ssm_out") +
                                   find("hc_up+down") + find("router_F32");
    const double per_layer_moe   = find("moe_gate_up") + find("moe_down_IQ4NL") + find("glu_f32");
    const double out_us          = find("output_head");
    // approximation: 36 GDN + 12 full-attn layers share the dense GEMV set; MoE on all 48; head once.
    const double dense_ms = per_layer_dense * 48 / 1000.0;
    const double moe_ms   = per_layer_moe * 48 / 1000.0;
    printf("\nsummary (batch=1, %d iters/op; sync overhead ~5-15us/op included):\n", iters);
    printf("  dense GEMVs  (x48 layers): %6.1f ms/token\n", dense_ms);
    printf("  MoE chain    (x48 layers): %6.1f ms/token\n", moe_ms);
    printf("  output head  (x1):         %6.1f ms/token\n", out_us / 1000.0);
    printf("  predicted weight-time total: %.1f ms/token (in-model measured ~49 ms median)\n",
           dense_ms + moe_ms + out_us / 1000.0);
    printf("  per-op effective GB/s shows which op is furthest from the ~200-240 GB/s ceiling\n");
    return 0;
}
