#!/usr/bin/env python3
"""Fix declaration order: begin_capture_hook() references ev_used, but the pool declarations
sit later in the file (they replaced the old record() body). Move the pool state up, next to
`segs`, and leave only the functions where record() was.
"""
P = '/home/revn/strix-llama/ggml/src/ggml-cuda/ggml-cuda.cu'
src = open(P, encoding='utf-8').read()

# 1. remove the pool-state block from where it is now (above record())
pool_block = """// Events are allocated ONCE from a pool that is grown OUTSIDE capture. Creating an event
// while a stream capture is active yields a handle that hipEventElapsedTime() later rejects
// with hipErrorInvalidResourceHandle (400).
static std::vector<cudaEvent_t> ev_pool;
static size_t ev_used = 0;

"""
assert src.count(pool_block) == 1, f'pool block count={src.count(pool_block)}'
src = src.replace(pool_block, '', 1)

# 2. put the state next to segs (before begin_capture_hook)
old = """static std::vector<Seg> segs;
static long long rec_calls = 0;"""
new = """static std::vector<Seg> segs;

// Events are allocated ONCE from a pool grown OUTSIDE capture. Creating an event while a stream
// capture is active yields a handle that hipEventElapsedTime() later rejects with
// hipErrorInvalidResourceHandle (400). Reused across replays.
static std::vector<cudaEvent_t> ev_pool;
static size_t ev_used = 0;

static long long rec_calls = 0;"""
assert src.count(old) == 1, f'segs anchor count={src.count(old)}'
src = src.replace(old, new, 1)

open(P, 'w', encoding='utf-8').write(src)
print('reordered OK')
# show the ordering we now have
i_pool = src.index('static std::vector<cudaEvent_t> ev_pool')
i_hook = src.index('static void begin_capture_hook()')
print('  ev_pool declared before begin_capture_hook:', i_pool < i_hook)
# only ONE ev_used = 0 assignment should remain (in the hook)
print('  "ev_used = 0" count:', src.count('ev_used = 0'))
