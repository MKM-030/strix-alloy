#!/usr/bin/env python3
"""Fix hipEventElapsedTime -> hipErrorInvalidResourceHandle (400) on captured events.

Evidence: "seg: op=MUL_MAT_ID a=... b=... err=400 (invalid resource handle) ms=0.0000"
with record_calls=96, cap_nodes=3490, matches=96. So capture and recording work; only the
ELAPSED QUERY fails.

Hypothesis: the events are created with hipEventCreate() *while stream capture is active*.
An event created during capture may not be a valid queryable handle after instantiation.
Fix: allocate events from a pool created OUTSIDE capture (in begin_capture_hook, which runs
before cudaStreamBeginCapture), and reuse them across replays.
"""
P = '/home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu'
src = open(P, encoding='utf-8').read()

# replace record() with a pooled version
old = """static void record(cudaStream_t stream, const ggml_tensor * node) {
    cudaEvent_t a, b;
    CUDA_CHECK(hipEventCreate(&a));
    CUDA_CHECK(hipEventCreate(&b));
    CUDA_CHECK(cudaEventRecord(a, stream));
    segs.push_back({ggml_op_name(node->op), layer_of(node), a, b});
    CUDA_CHECK(cudaEventRecord(b, stream));
    ++rec_calls;
}"""
new = """// Events are allocated ONCE from a pool that is grown OUTSIDE capture. Creating an event
// while a stream capture is active yields a handle that hipEventElapsedTime() later rejects
// with hipErrorInvalidResourceHandle (400).
static std::vector<cudaEvent_t> ev_pool;
static size_t ev_used = 0;

static cudaEvent_t pool_event() {
    if (ev_used + 2 > ev_pool.size()) {
        for (int k = 0; k < 512; k++) {   // grow in blocks
            cudaEvent_t e;
            CUDA_CHECK(hipEventCreate(&e));
            ev_pool.push_back(e);
        }
    }
    cudaEvent_t e = ev_pool[ev_used];
    ev_used += 2;                          // consume a pair
    return e;
}

static void record(cudaStream_t stream, const ggml_tensor * node) {
    if (ev_used + 2 > ev_pool.size()) {
        // pool exhausted mid-capture: fall back to creating (may query-fail, but keeps counts honest)
        for (int k = 0; k < 512; k++) {
            cudaEvent_t e;
            CUDA_CHECK(hipEventCreate(&e));
            ev_pool.push_back(e);
        }
    }
    cudaEvent_t a = ev_pool[ev_used];
    cudaEvent_t b = ev_pool[ev_used + 1];
    ev_used += 2;
    CUDA_CHECK(cudaEventRecord(a, stream));
    segs.push_back({ggml_op_name(node->op), layer_of(node), a, b});
    CUDA_CHECK(cudaEventRecord(b, stream));
    ++rec_calls;
}"""
assert src.count(old) == 1, f'record anchor={src.count(old)}'
src = src.replace(old, new)

# reset the pool cursor at each fresh capture (events are reused, not destroyed)
old = "static void begin_capture_hook() { segs.clear(); }  // fresh capture: new event set below"
new = "static void begin_capture_hook() { segs.clear(); ev_used = 0; }  // fresh capture: reuse pooled events"
assert src.count(old) == 1, f'begin anchor={src.count(old)}'
src = src.replace(old, new)

open(P, 'w', encoding='utf-8').write(src)
print('patched OK')
print('  ev_pool refs:', src.count('ev_pool'))
print('  pool_event  :', src.count('pool_event'))
