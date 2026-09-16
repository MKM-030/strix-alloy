// shapebench.hip — Codex Step 3: is the decode bandwidth loss the ACCESS PATTERN or the KERNEL?
//
// A decode step does not stream 4.2 GB contiguously. It reads ~150 separate weight tensors, each
// 1 MB..520 MB, each via its own kernel launch. So measure the same total bytes two ways:
//
//   A) contiguous : one big buffer, one grid-stride read            (models "memory can do 235 GB/s")
//   B) fragmented : N separate buffers with realistic tensor sizes  (models the real access pattern)
//
// If A ~= B, the access pattern is fine and the loss lives in the matvec kernels (dequant, dependencies,
// register pressure). If A >> B, the small-tensor/many-buffer pattern itself is the limitation.
//
// The reduction is consumed (written to a 1-element output) so nothing is optimised away. The
// reduction is done with float accumulation of the loaded values, which also keeps the load live.
//
// Build (same toolchain as the server):
//   <sdk>\bin\hipcc.exe -O3 --offload-arch=gfx1151 shapebench.hip -o shapebench.exe
//
// Usage: shapebench.exe <totalGB> <nBuffers>

#include <hip/hip_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <cmath>
#include <vector>
#include <algorithm>
#include <random>

#define HIP_CHECK(x) do { hipError_t e = (x); if (e != hipSuccess) { \
    printf("HIP error %s at %s:%d\n", hipGetErrorString(e), __FILE__, __LINE__); exit(1); } } while (0)

// Grid-stride read of one buffer; each thread accumulates its own loads and writes one partial.
__global__ void read_kernel(const uint4 * __restrict__ buf, size_t n_uint4, float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    float acc = 0.0f;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        // fold the four words into the accumulator so the load cannot be eliminated
        acc += (float) __popc(v.x) + (float) __popc(v.y) + (float) __popc(v.z) + (float) __popc(v.w);
    }
    // one atomic per thread block is too much; reduce via shared then one atomic
    __shared__ float s[256];
    s[threadIdx.x] = acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Same read as read_kernel but with NO contending epilogue: each block writes its partial to its own
// slot instead of atomicAdd-ing into one global scalar. Codex's confound check for variant B:
// B launches up to 4096 blocks/buffer vs D's 256, so B pays 16x the shared-reduction + atomic epilogue.
// If B-nocontend is much faster than B-contend, B's slowness is epilogue contention, not memory.
__global__ void read_kernel_nc(const uint4 * __restrict__ buf, size_t n_uint4, float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    float acc = 0.0f;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        acc += (float) __popc(v.x) + (float) __popc(v.y) + (float) __popc(v.z) + (float) __popc(v.w);
    }
    __shared__ float s[256];
    s[threadIdx.x] = acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) out[blockIdx.x] = s[0];   // no contention
}

// B-like read with a selectable epilogue: contending (atomicAdd to one slot) vs non-contending.
static float run_read_epi(void ** ptrs, const size_t * bytes, int n, int iters, int blocks_cap, bool contending) {
    float * dout; HIP_CHECK(hipMalloc(&dout, sizeof(float) * 8192)); HIP_CHECK(hipMemset(dout, 0, sizeof(float) * 8192));
    auto go = [&] {
        for (int i = 0; i < n; ++i) {
            size_t nu = bytes[i] / sizeof(uint4);
            int blocks = (int) std::min<size_t>((nu + 255) / 256, blocks_cap);
            if (blocks < 1) blocks = 1;
            if (contending) read_kernel          <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dout);
            else            read_kernel_nc       <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dout);
        }
    };
    go(); HIP_CHECK(hipDeviceSynchronize());
    hipEvent_t t0, t1; HIP_CHECK(hipEventCreate(&t0)); HIP_CHECK(hipEventCreate(&t1));
    HIP_CHECK(hipEventRecord(t0));
    for (int it = 0; it < iters; ++it) go();
    HIP_CHECK(hipEventRecord(t1)); HIP_CHECK(hipEventSynchronize(t1));
    float ms = 0.0f; HIP_CHECK(hipEventElapsedTime(&ms, t0, t1));
    HIP_CHECK(hipFree(dout)); hipEventDestroy(t0); hipEventDestroy(t1);
    return ms / iters;
}

static float run_read(void ** ptrs, const size_t * bytes, int n, int iters, int blocks_cap = 4096) {
    hipEvent_t t0, t1; HIP_CHECK(hipEventCreate(&t0)); HIP_CHECK(hipEventCreate(&t1));
    float * dout; HIP_CHECK(hipMalloc(&dout, sizeof(float))); HIP_CHECK(hipMemset(dout, 0, sizeof(float)));
    // warm
    for (int i = 0; i < n; ++i) {
        size_t nu = bytes[i] / sizeof(uint4);
        int blocks = (int) std::min<size_t>((nu + 255) / 256, blocks_cap);
        if (blocks < 1) blocks = 1;
        read_kernel<<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dout);
    }
    HIP_CHECK(hipDeviceSynchronize());
    HIP_CHECK(hipEventRecord(t0));
    for (int it = 0; it < iters; ++it) {
        for (int i = 0; i < n; ++i) {
            size_t nu = bytes[i] / sizeof(uint4);
            int blocks = (int) std::min<size_t>((nu + 255) / 256, blocks_cap);
            if (blocks < 1) blocks = 1;
            read_kernel<<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dout);
        }
    }
    HIP_CHECK(hipEventRecord(t1));
    HIP_CHECK(hipEventSynchronize(t1));
    float ms = 0.0f; HIP_CHECK(hipEventElapsedTime(&ms, t0, t1));
    HIP_CHECK(hipFree(dout)); hipEventDestroy(t0); hipEventDestroy(t1);
    return ms / iters;
}

// Variant of read_kernel: a 1-D grid of (nBufs * BLOCKS_PER_BUF) blocks. Block (b, k) reads buffer b,
// with blocks cooperating via a within-buffer grid-stride. One launch covers ALL buffers, so any
// difference vs the "N separate launches" path is per-launch behaviour (ramp / wave quantisation),
// not the memory system's ability to handle scattered addresses.
#define BLOCKS_PER_BUF 256
__global__ void read_multi_kernel(const uint4 * const * __restrict__ bufs,
                                 const size_t * __restrict__ counts,
                                 float * __restrict__ out) {
    const int buf = blockIdx.x / BLOCKS_PER_BUF;
    const int sub = blockIdx.x % BLOCKS_PER_BUF;
    const uint4 * __restrict__ buf_p = bufs[buf];
    const size_t n = counts[buf];
    const size_t stride = (size_t) BLOCKS_PER_BUF * blockDim.x;
    size_t i = (size_t) sub * blockDim.x + threadIdx.x;
    float acc = 0.0f;
    for (; i < n; i += stride) {
        const uint4 v = buf_p[i];
        acc += (float) __popc(v.x) + (float) __popc(v.y) + (float) __popc(v.z) + (float) __popc(v.w);
    }
    __shared__ float s[256];
    s[threadIdx.x] = acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Codex Step-3 variant C: the ACTUAL production operator shape — a quantized GEMV. Pure reads
// (A..D) only prove the memory pattern; this adds the dequant + dot that the real mmvq kernel does,
// which is what distinguishes "memory-bound" from "kernel-internal cost".
//
// IQ4_NL: 32 weights per 18-byte block (2-byte scale + 16 bytes = 32 nibbles). One uint4 (16 B) is
// exactly one block's nibble payload, so we dequant 32 weights and FMA them against x per uint4 —
// the same work-per-byte ratio as the real vec_dot_iq4_nl_q8_1, minus the q8_x quantization side.
__constant__ float c_iq4nl[16] = {
    -127.f, -104.f, -83.f, -65.f, -49.f, -35.f, -22.f, -10.f,
       1.f,   13.f,  25.f,  38.f,  53.f,  69.f,  89.f, 113.f };

__global__ void gemv_like_kernel(const uint4 * __restrict__ buf, size_t n_uint4,
                                 const float * __restrict__ x, int xmask,
                                 float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    float acc = 0.0f;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        const size_t base = i * 32;
        const uint32_t w[4] = { v.x, v.y, v.z, v.w };
#pragma unroll
        for (int q = 0; q < 4; ++q) {
#pragma unroll
            for (int n = 0; n < 8; ++n) {
                const int nib = (int) ((w[q] >> (4 * n)) & 0xF);
                const float wv = c_iq4nl[nib] * 0.0078740f;   // ~1/127
                acc = fmaf(wv, x[(base + q * 8 + n) & xmask], acc);
            }
        }
    }
    __shared__ float s[256];
    s[threadIdx.x] = acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Variant F: identical to gemv_like_kernel EXCEPT the 16-entry value lookup is replaced by plain
// arithmetic that produces the same *shape* of work (a multiply-add per weight) without a dynamic
// table index. On AMD, a dynamically-indexed __constant__ array is serialized across a wave (constant
// memory only broadcasts), so if the LUT is the bottleneck, F should be much faster than E. If F is
// the same as E, the cost is raw ALU/issue and not the lookup.
__global__ void gemv_arith_kernel(const uint4 * __restrict__ buf, size_t n_uint4,
                                  const float * __restrict__ x, int xmask,
                                  float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    float acc = 0.0f;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        const size_t base = i * 32;
        const uint32_t w[4] = { v.x, v.y, v.z, v.w };
#pragma unroll
        for (int q = 0; q < 4; ++q) {
#pragma unroll
            for (int n = 0; n < 8; ++n) {
                const int nib = (int) ((w[q] >> (4 * n)) & 0xF);
                // same per-element arithmetic count as E, no table index
                const float wv = ((float) nib - 7.5f) * 0.0078740f * 127.0f;
                acc = fmaf(wv, x[(base + q * 8 + n) & xmask], acc);
            }
        }
    }
    __shared__ float s[256];
    s[threadIdx.x] = acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Variant G: like E but the nibble is consumed with NO per-element work beyond a single FMA whose
// weight is derived once per uint4 (8x less ALU than E/F). Isolates "loads alone with minimal ALU".
__global__ void gemv_minimal_kernel(const uint4 * __restrict__ buf, size_t n_uint4,
                                    const float * __restrict__ x, int xmask,
                                    float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    float acc = 0.0f;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        const float wv = (float) (__popc(v.x) + __popc(v.y) + __popc(v.z) + __popc(v.w)) * 0.0078740f;
        acc = fmaf(wv, x[(i * 32) & xmask], acc);
    }
    __shared__ float s[256];
    s[threadIdx.x] = acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Variant H: same ALU count as F, but the 32 FMAs per uint4 are split across INDEPENDENT accumulators
// (round-robin). If E/F's 46% is a serial dependency chain on `acc`, H recovers most of it -> an ILP
// problem with a cheap fix. If H is still ~46%, it is raw ALU/issue throughput -> needs dp4a/int-dot.
template <int NACC>
__global__ void gemv_ilp_kernel(const uint4 * __restrict__ buf, size_t n_uint4,
                                const float * __restrict__ x, int xmask,
                                float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    float acc[NACC];
#pragma unroll
    for (int a = 0; a < NACC; ++a) acc[a] = 0.0f;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        const size_t base = i * 32;
        const uint32_t w[4] = { v.x, v.y, v.z, v.w };
#pragma unroll
        for (int q = 0; q < 4; ++q) {
#pragma unroll
            for (int n = 0; n < 8; ++n) {
                const int nib = (int) ((w[q] >> (4 * n)) & 0xF);
                const float wv = ((float) nib - 7.5f) * 0.0078740f * 127.0f;
                acc[(q * 8 + n) % NACC] = fmaf(wv, x[(base + q * 8 + n) & xmask], acc[(q * 8 + n) % NACC]);
            }
        }
    }
    float tot = 0.0f;
#pragma unroll
    for (int a = 0; a < NACC; ++a) tot += acc[a];
    __shared__ float s[256];
    s[threadIdx.x] = tot;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Variant I: the INTENDED algorithm — 4 int8 MACs per instruction via dp4a, which is what the real
// IQ4_NL/Q8_1 vec_dot uses. Same loads, same 32 weights per uint4, but 8 dot instructions instead of
// 32 float FMAs. If I lands near A, production should be near A too and the float kernels were simply
// a bad model; if I also lands ~50%, the ALU floor is real regardless of encoding.
__global__ void gemv_dp4a_kernel(const uint4 * __restrict__ buf, size_t n_uint4,
                                 const int8_t * __restrict__ xq, int xmask,
                                 float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    int acc = 0;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        const size_t base = i * 32;
        const uint32_t w[4] = { v.x, v.y, v.z, v.w };
#pragma unroll
        for (int q = 0; q < 4; ++q) {
#pragma unroll
            for (int p = 0; p < 2; ++p) {                 // two groups of 4 nibbles per word
                const uint32_t ww = w[q];
                // extract 4 nibbles -> 4 signed int8 lane values (linear dequant proxy: 16*n - 127)
                int lanes = 0;
#pragma unroll
                for (int n = 0; n < 4; ++n) {
                    const int nib = (int) ((ww >> (4 * (p * 4 + n))) & 0xF);
                    const int8_t val = (int8_t) (nib * 16 - 127);
                    lanes |= ((int) (uint8_t) val) << (8 * n);
                }
                const int off = (int) ((base + q * 8 + p * 4) & xmask);
                const int x4 = *(const int *) (xq + off);   // 4 int8 activations
                // RDNA3/3.5 path from the fork's own ggml_cuda_dp4a
                acc = __builtin_amdgcn_sudot4(true, lanes, true, x4, acc, false);
            }
        }
    }
    __shared__ float s[256];
    s[threadIdx.x] = (float) acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Variant J: the IQ4_NL ALIGNMENT test. The real block is 18 bytes (2-byte scale d + 16 bytes qs),
// so a 4-byte read of qs sits at offset 2 mod 18 — never 4-byte aligned. My variant I reads clean
// 16-byte-aligned uint4. J does the same arithmetic as I but walks the buffer in 18-byte blocks,
// reading the 16 nibble bytes at offset 2 (2-byte aligned only). If J collapses toward production's
// ~52%, the 18-byte stride / misalignment is the missing cost, and a repacked (aligned) block format
// is the fix.
__global__ void gemv_iq4nl_18b_kernel(const uint8_t * __restrict__ raw, size_t n_blocks,
                                      const int8_t * __restrict__ xq, int xmask,
                                      float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    int acc = 0;
    for (; i < n_blocks; i += stride) {
        const uint8_t * blk = raw + i * 18 + 2;      // skip the 2-byte scale; qs is 2-byte aligned
#pragma unroll
        for (int q = 0; q < 4; ++q) {
            uint32_t ww;
            __builtin_memcpy(&ww, blk + q * 4, 4);   // deliberately unaligned 4-byte load
#pragma unroll
            for (int p = 0; p < 2; ++p) {
                int lanes = 0;
#pragma unroll
                for (int n = 0; n < 4; ++n) {
                    const int nib = (int) ((ww >> (4 * (p * 4 + n))) & 0xF);
                    lanes |= ((int) (uint8_t) (int8_t) (nib * 16 - 127)) << (8 * n);
                }
                const int off = (int) (((size_t) i * 32 + q * 8 + p * 4) & xmask);
                const int x4 = *(const int *) (xq + off);
                acc = __builtin_amdgcn_sudot4(true, lanes, true, x4, acc, false);
            }
        }
    }
    __shared__ float s[256];
    s[threadIdx.x] = (float) acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Variant K: dp4a PLUS the real AMD dequant — the register-based byte-permute table lookup the fork
// actually uses (get_int_from_table_16: 6 v_perm per lookup, 4 lookups per 32 weights). My variant I
// skipped this with cheap arithmetic. If K collapses toward production's ~52%, the LUT cost is the
// missing piece; if K stays ~80%, production's gap is elsewhere (multi-warp reduction, spin locks).
__global__ void gemv_dp4a_lut_kernel(const uint4 * __restrict__ buf, size_t n_uint4,
                                     const int8_t * __restrict__ xq, int xmask,
                                     float * __restrict__ out) {
    // kvalues for IQ4_NL as int8 (the fork's table), loaded once per thread from constant memory.
    const uint32_t t0 = 0xEFDDCDBDu, t1 = 0x1263A7C9u, t2 = 0x246E0F1Fu, t3 = 0xE9F6957Fu;
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    int acc = 0;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        const size_t base = i * 32;
        const uint32_t w[4] = { v.x, v.y, v.z, v.w };
#pragma unroll
        for (int q = 0; q < 4; ++q) {
            const uint32_t q4 = w[q];
            const uint32_t q_even = q4;
            const uint32_t q_odd  = (q4 >> 4);
            // real AMD path: 6 v_perm to build the 4 int8 results
            const uint32_t v_even_low  = __builtin_amdgcn_perm(t1, t0, q_even & 0x07070707);
            const uint32_t v_odd_low   = __builtin_amdgcn_perm(t1, t0, q_odd  & 0x07070707);
            const uint32_t v_even_high = __builtin_amdgcn_perm(t3, t2, q_even & 0x07070707);
            const uint32_t v_odd_high  = __builtin_amdgcn_perm(t3, t2, q_odd  & 0x07070707);
            const uint32_t res_x = __builtin_amdgcn_perm(v_even_high, v_even_low, 0x03020100u | ((q_even & 0x08080808u) >> 1));
            const uint32_t res_y = __builtin_amdgcn_perm(v_odd_high,  v_odd_low,  0x03020100u | ((q_odd  & 0x08080808u) >> 1));
            const int off = (int) ((base + q * 8) & xmask);
            acc = __builtin_amdgcn_sudot4(true, (int) res_x, true, *(const int *) (xq + off),     acc, false);
            acc = __builtin_amdgcn_sudot4(true, (int) res_y, true, *(const int *) (xq + off + 4), acc, false);
        }
    }
    __shared__ float s[256];
    s[threadIdx.x] = (float) acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) atomicAdd(out, s[0]);
}

// Non-contending twin of gemv_dp4a_kernel: writes its partial to a per-block slot instead of
// atomicAdd-ing one scalar. Real mmvq writes per-row results (no atomic), so this is the FAIR epilogue
// and tells us whether the contending epilogue was depressing the I/K ceiling.
__global__ void gemv_dp4a_nc_kernel(const uint4 * __restrict__ buf, size_t n_uint4,
                                    const int8_t * __restrict__ xq, int xmask,
                                    float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    int acc = 0;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        const size_t base = i * 32;
        const uint32_t w[4] = { v.x, v.y, v.z, v.w };
#pragma unroll
        for (int q = 0; q < 4; ++q) {
#pragma unroll
            for (int p = 0; p < 2; ++p) {
                const uint32_t ww = w[q];
                int lanes = 0;
#pragma unroll
                for (int n = 0; n < 4; ++n) {
                    const int nib = (int) ((ww >> (4 * (p * 4 + n))) & 0xF);
                    const int8_t val = (int8_t) (nib * 16 - 127);
                    lanes |= ((int) (uint8_t) val) << (8 * n);
                }
                const int off = (int) ((base + q * 8 + p * 4) & xmask);
                acc = __builtin_amdgcn_sudot4(true, lanes, true, *(const int *) (xq + off), acc, false);
            }
        }
    }
    __shared__ float s[256];
    s[threadIdx.x] = (float) acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) out[blockIdx.x] = s[0];   // no contention
}

// Non-contending twin of gemv_arith_kernel (32 float FMAs) so the ALU cost can be measured with the
// same fair epilogue as gemv_dp4a_nc_kernel. If arith-nc is still ~50%, the ALU cost is real and
// independent of the epilogue; if it jumps to ~100%, the earlier "ALU-bound" reading was the epilogue.
__global__ void gemv_arith_nc_kernel(const uint4 * __restrict__ buf, size_t n_uint4,
                                     const float * __restrict__ x, int xmask,
                                     float * __restrict__ out) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    float acc = 0.0f;
    for (; i < n_uint4; i += stride) {
        const uint4 v = buf[i];
        const size_t base = i * 32;
        const uint32_t w[4] = { v.x, v.y, v.z, v.w };
#pragma unroll
        for (int q = 0; q < 4; ++q) {
#pragma unroll
            for (int n = 0; n < 8; ++n) {
                const int nib = (int) ((w[q] >> (4 * n)) & 0xF);
                const float wv = ((float) nib - 7.5f) * 0.0078740f * 127.0f;
                acc = fmaf(wv, x[(base + q * 8 + n) & xmask], acc);
            }
        }
    }
    __shared__ float s[256];
    s[threadIdx.x] = acc;
    __syncthreads();
    for (int off = blockDim.x / 2; off > 0; off >>= 1) {
        if ((int) threadIdx.x < off) s[threadIdx.x] += s[threadIdx.x + off];
        __syncthreads();
    }
    if (threadIdx.x == 0) out[blockIdx.x] = s[0];
}

// Same as run_read (N launches, one per weight tensor) but running a dequant+dot kernel. This is the
// fair in-vitro model of production decode: many launches at real tensor sizes. `kind` selects which
// inner loop: 0 = E (LUT), 1 = F (arith, no LUT), 2 = G (minimal ALU), 4/8 = ILP accumulators,
// 3 = I (dp4a int8).
static float run_gemv(void ** ptrs, const size_t * bytes, int n, int iters, int blocks_cap, int kind) {
    float * dx = nullptr; HIP_CHECK(hipMalloc(&dx, sizeof(float) * 4096));
    HIP_CHECK(hipMemset(dx, 0, sizeof(float) * 4096));
    int8_t * dxq = nullptr; HIP_CHECK(hipMalloc(&dxq, 4096)); HIP_CHECK(hipMemset(dxq, 1, 4096));
    float * dout; HIP_CHECK(hipMalloc(&dout, sizeof(float))); HIP_CHECK(hipMemset(dout, 0, sizeof(float)));
    auto go = [&] {
        for (int i = 0; i < n; ++i) {
            size_t nu = bytes[i] / sizeof(uint4);
            int blocks = (int) std::min<size_t>((nu + 255) / 256, blocks_cap);
            if (blocks < 1) blocks = 1;
            if      (kind == 0) gemv_like_kernel   <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dx, 4095, dout);
            else if (kind == 1) gemv_arith_kernel  <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dx, 4095, dout);
            else if (kind == 2) gemv_minimal_kernel<<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dx, 4095, dout);
            else if (kind == 3) gemv_dp4a_kernel   <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dxq, 4095, dout);
            else if (kind == 5) gemv_iq4nl_18b_kernel<<<blocks, 256>>>((const uint8_t *) ptrs[i], nu * 16 / 18, dxq, 4095, dout);
            else if (kind == 6) gemv_dp4a_lut_kernel <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dxq, 4095, dout);
            else if (kind == 4) gemv_ilp_kernel<4> <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dx, 4095, dout);
            else if (kind == 7) gemv_dp4a_nc_kernel <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dxq, 4095, dout);
            else if (kind == 8) gemv_arith_nc_kernel<<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dx, 4095, dout);
            else                gemv_ilp_kernel<8> <<<blocks, 256>>>((const uint4 *) ptrs[i], nu, dx, 4095, dout);
        }
    };
    go(); HIP_CHECK(hipDeviceSynchronize());
    hipEvent_t t0, t1; HIP_CHECK(hipEventCreate(&t0)); HIP_CHECK(hipEventCreate(&t1));
    HIP_CHECK(hipEventRecord(t0));
    for (int it = 0; it < iters; ++it) go();
    HIP_CHECK(hipEventRecord(t1)); HIP_CHECK(hipEventSynchronize(t1));
    float ms = 0.0f; HIP_CHECK(hipEventElapsedTime(&ms, t0, t1));
    HIP_CHECK(hipFree(dx)); HIP_CHECK(hipFree(dxq)); HIP_CHECK(hipFree(dout)); hipEventDestroy(t0); hipEventDestroy(t1);
    return ms / iters;
}

static float run_read_multi(void ** ptrs, const size_t * bytes, int n, int iters) {
    std::vector<const uint4 *> hp(n);
    std::vector<size_t>        hc(n);
    for (int i = 0; i < n; ++i) { hp[i] = (const uint4 *) ptrs[i]; hc[i] = bytes[i] / sizeof(uint4); }
    const uint4 ** dp = nullptr; size_t * dc = nullptr;
    HIP_CHECK(hipMalloc(&dp, sizeof(const uint4 *) * n));
    HIP_CHECK(hipMalloc(&dc, sizeof(size_t) * n));
    HIP_CHECK(hipMemcpy(dp, hp.data(), sizeof(const uint4 *) * n, hipMemcpyHostToDevice));
    HIP_CHECK(hipMemcpy(dc, hc.data(), sizeof(size_t) * n, hipMemcpyHostToDevice));
    float * dout; HIP_CHECK(hipMalloc(&dout, sizeof(float))); HIP_CHECK(hipMemset(dout, 0, sizeof(float)));
    const dim3 grid(n * BLOCKS_PER_BUF);
    auto go = [&] { read_multi_kernel<<<grid, 256>>>(dp, dc, dout); };
    go(); HIP_CHECK(hipDeviceSynchronize());
    hipEvent_t t0, t1; HIP_CHECK(hipEventCreate(&t0)); HIP_CHECK(hipEventCreate(&t1));
    HIP_CHECK(hipEventRecord(t0));
    for (int it = 0; it < iters; ++it) go();
    HIP_CHECK(hipEventRecord(t1)); HIP_CHECK(hipEventSynchronize(t1));
    float ms = 0.0f; HIP_CHECK(hipEventElapsedTime(&ms, t0, t1));
    HIP_CHECK(hipFree(dp)); HIP_CHECK(hipFree(dc)); HIP_CHECK(hipFree(dout));
    hipEventDestroy(t0); hipEventDestroy(t1);
    return ms / iters;
}

int main(int argc, char ** argv) {
    double totalGB = argc > 1 ? atof(argv[1]) : 4.219;
    int    nBufs   = argc > 2 ? atoi(argv[2])  : 150;
    const char * mode = argc > 3 ? argv[3] : "realistic";
    const int iters = 20;

    int dev = 0; HIP_CHECK(hipSetDevice(dev));
    hipDeviceProp_t prop; HIP_CHECK(hipGetDeviceProperties(&prop, dev));
    printf("device: %s  (%s), %zu MB pool\n", prop.name, prop.gcnArchName, prop.totalGlobalMem >> 20);

    const size_t total_bytes = (size_t)(totalGB * 1e9);

    // ---- per-buffer sizes -----------------------------------------------------------------------
    // "uniform"   : nBufs equal buffers          -> isolates COUNT from size variance
    // "realistic" : log-uniform 0.1..520 MB      -> models the actual decode read set
    std::vector<size_t> sizes(nBufs);
    size_t assigned = 0;
    if (std::string(mode) == "uniform") {
        for (int i = 0; i < nBufs; ++i) { sizes[i] = (total_bytes / nBufs) & ~(size_t)0xF; assigned += sizes[i]; }
    } else {
        std::vector<double> weights;
        std::mt19937 rng(1234);
        std::uniform_real_distribution<double> u(0.0, 1.0);
        for (int i = 0; i < nBufs; ++i) weights.push_back(0.1 * pow(5200.0, u(rng)) * 1e6);
        double wsum = 0; for (double w : weights) wsum += w;
        for (int i = 0; i < nBufs; ++i) {
            size_t b = (size_t)(total_bytes * weights[i] / wsum);
            b &= ~(size_t)0xF;
            sizes[i] = b; assigned += b;
        }
    }
    if (assigned < total_bytes) sizes[0] += (total_bytes - assigned);

    // ---- allocate A: one contiguous buffer -------------------------------------------------------
    void * A = nullptr;
    HIP_CHECK(hipMalloc(&A, total_bytes));
    HIP_CHECK(hipMemset(A, 0xA5, total_bytes));   // non-zero so values are real

    // ---- allocate B: nBufs separate buffers ------------------------------------------------------
    std::vector<void *> B(nBufs, nullptr);
    for (int i = 0; i < nBufs; ++i) { HIP_CHECK(hipMalloc(&B[i], sizes[i])); HIP_CHECK(hipMemset(B[i], 0xA5, sizes[i])); }

    // ---- run -------------------------------------------------------------------------------------
    float msA = run_read(&A, &total_bytes, 1, iters);
    float msB = run_read(B.data(), sizes.data(), nBufs, iters);
    // D: many launches, but each with the SAME per-buffer grid as variant C (256 blocks).
    // If D is fast -> the cost was grid shape / short loops.  If D is slow -> it is launch count.
    float msD = run_read(B.data(), sizes.data(), nBufs, iters, BLOCKS_PER_BUF);
    float msC = run_read_multi(B.data(), sizes.data(), nBufs, iters);

    double gb = totalGB;
    printf("\ntotal bytes: %.3f GB   mode=%s  buffers=%d\n", gb, mode, nBufs);
    printf("  A  contiguous            : %8.3f ms  -> %7.1f GB/s\n", msA, gb / (msA / 1000.0));
    printf("  B  frag, N launch, big g : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msB, gb / (msB / 1000.0), 100.0 * msA / msB);
    printf("  D  frag, N launch, small : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msD, gb / (msD / 1000.0), 100.0 * msA / msD);
    printf("  C  frag, 1 launch        : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msC, gb / (msC / 1000.0), 100.0 * msA / msC);

    // E: the production operator shape (dequant + dot), many launches, real tensor sizes.
    //   kind 0 = IQ4_NL-style LUT dequant; 1 = same ALU count without the LUT; 2 = minimal ALU.
    float msEbig   = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 0);
    float msEsmall = run_gemv(B.data(), sizes.data(), nBufs, iters, BLOCKS_PER_BUF, 0);
    printf("  E  GEMV(dequant+dot), big grid : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msEbig, gb / (msEbig / 1000.0), 100.0 * msA / msEbig);
    printf("  E  GEMV(dequant+dot), small gr : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msEsmall, gb / (msEsmall / 1000.0), 100.0 * msA / msEsmall);
    float msF = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 1);
    float msG = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 2);
    printf("  F  GEMV(arith, no LUT)         : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msF, gb / (msF / 1000.0), 100.0 * msA / msF);
    printf("  G  GEMV(minimal ALU)           : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msG, gb / (msG / 1000.0), 100.0 * msA / msG);
    float msH4 = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 4);
    float msH8 = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 8);
    printf("  H  GEMV(arith) 4 accumulators  : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msH4, gb / (msH4 / 1000.0), 100.0 * msA / msH4);
    printf("  H  GEMV(arith) 8 accumulators  : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msH8, gb / (msH8 / 1000.0), 100.0 * msA / msH8);
    float msI = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 3);
    printf("  I  GEMV(dp4a int8, 8 dots/16B) : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msI, gb / (msI / 1000.0), 100.0 * msA / msI);
    // ---- Codex confound check: is B's slowness the contending epilogue? ----
    float msBnc = run_read_epi(B.data(), sizes.data(), nBufs, iters, 4096, false);
    float msDnc = run_read_epi(B.data(), sizes.data(), nBufs, iters, BLOCKS_PER_BUF, false);
    printf("  B  frag, big grid, NO contending epilogue : %8.3f ms -> %7.1f GB/s (%.1f%% of A)\n",
           msBnc, gb / (msBnc / 1000.0), 100.0 * msA / msBnc);
    printf("  D  frag, small grid, NO contending epilogue: %8.3f ms -> %7.1f GB/s (%.1f%% of A)\n",
           msDnc, gb / (msDnc / 1000.0), 100.0 * msA / msDnc);
    printf("  -> B contend %.3f ms vs B no-contend %.3f ms (epilogue cost = %.3f ms)\n",
           msB, msBnc, msB - msBnc);
    float msInc = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 7);
    printf("  I  GEMV(dp4a) NO contending epilogue     : %8.3f ms -> %7.1f GB/s (%.1f%% of A)\n",
           msInc, gb / (msInc / 1000.0), 100.0 * msA / msInc);
    float msFnc = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 8);
    printf("  F  GEMV(32 float FMA) NO contending epi  : %8.3f ms -> %7.1f GB/s (%.1f%% of A)\n",
           msFnc, gb / (msFnc / 1000.0), 100.0 * msA / msFnc);
    float msJ = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 5);
    printf("  J  GEMV(dp4a, 18B IQ4_NL blk)  : %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msJ, gb / (msJ / 1000.0), 100.0 * msA / msJ);
    float msK = run_gemv(B.data(), sizes.data(), nBufs, iters, 4096, 6);
    printf("  K  GEMV(dp4a + real v_perm LUT): %8.3f ms  -> %7.1f GB/s   (%.1f%% of A)\n",
           msK, gb / (msK / 1000.0), 100.0 * msA / msK);
    printf("\n  smallest %zu B, largest %zu B, median %zu B\n",
           *std::min_element(sizes.begin(), sizes.end()),
           *std::max_element(sizes.begin(), sizes.end()),
           sizes[nBufs / 2]);

    HIP_CHECK(hipFree(A));
    for (int i = 0; i < nBufs; ++i) HIP_CHECK(hipFree(B[i]));
    return 0;
}
