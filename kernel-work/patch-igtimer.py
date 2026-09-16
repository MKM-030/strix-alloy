#!/usr/bin/env python3
"""Patch the in-graph op timer to self-diagnose why it reports 0.0 ms/replay.

Adds (nothing else changed):
  * a counter of record() calls
  * a one-time diagnostic in collect() showing segs.size() and the hipEventElapsedTime
    return code + message for the first few segments
This turns "it reports zero" into "here is exactly why".
"""
import re
import sys

P = '/home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu'
src = open(P, encoding='utf-8').read()

# 1. counter next to segs
old = """struct Agg { double us = 0; long long n = 0; };
static std::unordered_map<std::string, Agg> agg;
static std::vector<Seg> segs;

static void begin_capture_hook() { segs.clear(); }  // fresh capture: new event set below"""
new = """struct Agg { double us = 0; long long n = 0; };
static std::unordered_map<std::string, Agg> agg;
static std::vector<Seg> segs;
static long long rec_calls = 0;          // diagnostics: how many record() calls happened
static long long collect_calls = 0;      // diagnostics: how many collect() calls happened

static void begin_capture_hook() { segs.clear(); }  // fresh capture: new event set below"""
assert src.count(old) == 1, f'begin_capture_hook anchor count={src.count(old)}'
src = src.replace(old, new)

# 2. count record() calls
old = """    CUDA_CHECK(hipEventCreate(&a));
    CUDA_CHECK(hipEventCreate(&b));
    CUDA_CHECK(cudaEventRecord(a, stream));
    segs.push_back({ggml_op_name(node->op), layer_of(node), a, b});
    CUDA_CHECK(cudaEventRecord(b, stream));"""
new = """    CUDA_CHECK(hipEventCreate(&a));
    CUDA_CHECK(hipEventCreate(&b));
    CUDA_CHECK(cudaEventRecord(a, stream));
    segs.push_back({ggml_op_name(node->op), layer_of(node), a, b});
    CUDA_CHECK(cudaEventRecord(b, stream));
    ++rec_calls;"""
assert src.count(old) == 1, f'record anchor count={src.count(old)}'
src = src.replace(old, new)

# 3. diagnostics at the top of collect()
old = """static void collect() {
    for (auto & s : segs) {"""
new = """static void collect() {
    // ---- one-time diagnostics: distinguish "no segments" from "elapsed query failed" ----
    static bool diag_done = false;
    ++collect_calls;
    if (!diag_done && collect_calls >= 3) {
        diag_done = true;
        fprintf(stderr,
            "OP_TIMING_IG DIAG: record_calls=%lld collect_calls=%lld segs=%zu\\n",
            (long long) rec_calls, (long long) collect_calls, segs.size());
        int shown = 0;
        for (auto & s : segs) {
            float ms = 0.0f;
            (void) cudaGetLastError();
            cudaError_t e = hipEventElapsedTime(&ms, s.a, s.b);
            fprintf(stderr,
                "OP_TIMING_IG DIAG seg: op=%-16s a=%p b=%p err=%d (%s) ms=%.4f\\n",
                s.op.c_str(), (void *) s.a, (void *) s.b, (int) e, cudaGetErrorString(e), (double) ms);
            if (++shown >= 5) {
                break;
            }
        }
        fflush(stderr);
    }

    for (auto & s : segs) {"""
assert src.count(old) == 1, f'collect anchor count={src.count(old)}'
src = src.replace(old, new)

open(P, 'w', encoding='utf-8').write(src)
print('patched OK')
print('  rec_calls refs  :', src.count('rec_calls'))
print('  DIAG refs       :', src.count('OP_TIMING_IG DIAG'))
