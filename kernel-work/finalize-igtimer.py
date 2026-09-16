#!/usr/bin/env python3
"""Replace the whole diagnostic preamble in collect() with a loud, one-time failure notice.
Operates on the exact text currently in the file."""
P = '/home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu'
src = open(P, encoding='utf-8').read()

start = src.index('static void collect() {')
end   = src.index('    for (auto & s : segs) {', start)
preamble = src[start:end]

new_preamble = """static void collect() {
    // Proven on this build (2026-09-15): capture + recording work (record_calls=96,
    // cap_nodes=3490, matches=96), but hipEventElapsedTime() returns 400
    // (hipErrorInvalidResourceHandle) for captured events EVEN when the events are created
    // outside the capture region. So event records that become graph nodes have no queryable
    // timing state after replay on ROCm/DXG, and in-graph event timing cannot work here.
    // Say that once, loudly, instead of silently printing "tracked total 0.0 ms/replay".
    static bool warned = false;
    ++collect_calls;
    long long failed = 0;
"""
src = src[:start] + new_preamble + src[end:]

# count failures in the loop
old = """    for (auto & s : segs) {
        float ms = 0;
        if (hipEventElapsedTime(&ms, s.a, s.b) != hipSuccess) {
            continue;
        }"""
new = """    for (auto & s : segs) {
        float ms = 0;
        if (hipEventElapsedTime(&ms, s.a, s.b) != hipSuccess) {
            ++failed;
            continue;
        }"""
assert src.count(old) == 1, f'loop anchor={src.count(old)}'
src = src.replace(old, new)

# gate the periodic summary on "not warned"
old = """    static int64_t evals = 0;
    if (++evals % 8 == 0) {"""
new = """    if (!warned && !segs.empty() && failed == (long long) segs.size()) {
        warned = true;
        fprintf(stderr,
            "OP_TIMING_IG: hipEventElapsedTime() failed for all %lld captured events "
            "(hipErrorInvalidResourceHandle). In-graph event timing is NOT supported on this "
            "ROCm/DXG build. For per-op shares use LLAMA_OP_TIMING=1 with "
            "GGML_CUDA_DISABLE_GRAPHS=1.\\n",
            failed);
        fflush(stderr);
    }

    static int64_t evals = 0;
    if (++evals % 8 == 0 && !warned) {"""
assert src.count(old) == 1, f'summary anchor={src.count(old)}'
src = src.replace(old, new)

open(P, 'w', encoding='utf-8').write(src)
print('finalized OK')
print('  preamble replaced  :', 'one-time diagnostics' not in src)
print('  loud notice present:', src.count('NOT supported on this'))
print('  failed counter     :', src.count('++failed'))
