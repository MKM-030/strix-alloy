// bwtest.hip — what read bandwidth does this GPU ACTUALLY achieve?
//
// Why this matters: every "we are only at 55% of the ceiling" conclusion rests on the assumption
// that 200-240 GB/s (LPDDR5X theoretical ~256) is achievable in practice on this box with this
// driver. That number has never been measured here. If achievable bandwidth is ~130 GB/s, then our
// serial decode at ~122 GB/s effective is at ~95% and there is no 45% to find.
//
// Three patterns, because our real access is a MIX:
//   1. pure sequential read (best case, what a streaming kernel could hit)
//   2. strided read by a large stride (worst case, resembles scattered expert rows)
//   3. read + write (copy), to show the read/write split cost
//
// Build: clang++ -x hip --offload-arch=gfx1151 -O3
// Run:   bwtest [size_GB]

#include <hip/hip_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <vector>

#define HIP_CHECK(x) do { hipError_t e = (x); if (e != hipSuccess) { \
    printf("HIP error %s at %s:%d\n", hipGetErrorString(e), __FILE__, __LINE__); exit(1);} } while (0)

// Sum 16 bytes per iteration into a register; one thread per 16B chunk, grid-stride.
// Result written so nothing is optimised away.
__global__ void read_seq(const uint4 * __restrict__ src, size_t n4, float * __restrict__ sink) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    uint32_t acc = 0;
    for (; i < n4; i += stride) {
        uint4 v = src[i];
        acc ^= v.x ^ v.y ^ v.z ^ v.w;
    }
    if (acc == 0xDEADBEEFu) { sink[threadIdx.x & 255] = (float) acc; }  // never taken; keeps it live
}

// Same, but each thread walks with a large stride so consecutive accesses are far apart.
// Approximates reading one 90-byte expert row then jumping to a distant row.
__global__ void read_strided(const uint4 * __restrict__ src, size_t n4, size_t step, float * __restrict__ sink) {
    size_t lane = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t nthreads = (size_t) gridDim.x * blockDim.x;
    uint32_t acc = 0;
    for (size_t blk = 0; blk * nthreads * step < n4; ++blk) {
        size_t i = (blk * nthreads + lane) * step;
        if (i < n4) { uint4 v = src[i]; acc ^= v.x ^ v.y ^ v.z ^ v.w; }
    }
    if (acc == 0xDEADBEEFu) { sink[threadIdx.x & 255] = (float) acc; }
}

__global__ void copy_kernel(const uint4 * __restrict__ src, uint4 * __restrict__ dst, size_t n4) {
    size_t i = (size_t) blockIdx.x * blockDim.x + threadIdx.x;
    const size_t stride = (size_t) gridDim.x * blockDim.x;
    for (; i < n4; i += stride) { dst[i] = src[i]; }
}

static double now_ms() {
    hipDeviceSynchronize();
    return 0.0;  // unused; we time with events below
}

static float time_kernel(void (*launch)(void *), void * arg, int reps) {
    (void) launch; (void) arg; (void) reps; return 0.0f;
}

int main(int argc, char ** argv) {
    double size_gb = (argc > 1) ? atof(argv[1]) : 4.0;
    const size_t bytes = (size_t)(size_gb * 1024.0 * 1024.0 * 1024.0);
    const size_t n4    = bytes / 16;

    hipDeviceProp_t prop;
    HIP_CHECK(hipGetDeviceProperties(&prop, 0));
    printf("device: %s\ntotalGlobalMem: %.2f GB   memBusWidth: %d bit   memoryClockRate: %.0f MHz\n",
           prop.name, prop.totalGlobalMem / 1073741824.0, prop.memoryBusWidth, prop.memoryClockRate / 1000.0);
    printf("theoretical: %.1f GB/s\n\n", 2.0 * prop.memoryClockRate * 1000.0 * (prop.memoryBusWidth / 8.0) / 1e9);

    uint4 * src = nullptr, * dst = nullptr;
    float * sink = nullptr;
    HIP_CHECK(hipMalloc(&src, bytes));
    HIP_CHECK(hipMalloc(&dst, bytes));
    HIP_CHECK(hipMalloc(&sink, 1024 * sizeof(float)));
    HIP_CHECK(hipMemset(src, 0xA5, bytes));

    const int block = 256;
    const int grid  = 1024;

    hipEvent_t ev0, ev1;
    HIP_CHECK(hipEventCreate(&ev0));
    HIP_CHECK(hipEventCreate(&ev1));

    // warm
    read_seq<<<grid, block>>>(src, n4, sink);
    HIP_CHECK(hipDeviceSynchronize());

    const int reps = 5;

    // 1. sequential read
    {
        HIP_CHECK(hipEventRecord(ev0));
        for (int r = 0; r < reps; ++r) { read_seq<<<grid, block>>>(src, n4, sink); }
        HIP_CHECK(hipEventRecord(ev1));
        HIP_CHECK(hipDeviceSynchronize());
        float ms = 0; HIP_CHECK(hipEventElapsedTime(&ms, ev0, ev1));
        double total = (double) bytes * reps;
        printf("sequential read   : %8.2f ms/rep   %7.1f GB/s\n", ms / reps, total / (ms / 1000.0) / 1e9);
    }

    // 2. stride sweep: where does coalescing break down? threads are 1 element apart within a
    //    warp, so consecutive threads touch addresses `step` apart. Small step = coalesced;
    //    large step = one cache line per thread = latency-bound.
    {
        const size_t strides[] = { 1, 4, 16, 64, 256, 1024 };
        printf("stride sweep (consecutive threads `step` uint4 apart):\n");
        for (size_t s : strides) {
            const size_t nt = (size_t) grid * block;
            const size_t per_thread = n4 / (nt * s);
            if (per_thread == 0) { printf("   step %6zu: (too large)\n", s); continue; }
            HIP_CHECK(hipEventRecord(ev0));
            for (int r = 0; r < reps; ++r) { read_strided<<<grid, block>>>(src, n4, s, sink); }
            HIP_CHECK(hipEventRecord(ev1));
            HIP_CHECK(hipDeviceSynchronize());
            float ms = 0; HIP_CHECK(hipEventElapsedTime(&ms, ev0, ev1));
            const double touched = (double) per_thread * nt * 16 * reps;
            printf("   step %6zu: %8.2f ms/rep  %7.1f GB/s  (%5.1f MB touched/rep)\n",
                   s, ms / reps, touched / (ms / 1000.0) / 1e9, touched / reps / 1e6);
        }
    }

    // 3. copy (read + write)
    {
        HIP_CHECK(hipEventRecord(ev0));
        for (int r = 0; r < reps; ++r) { copy_kernel<<<grid, block>>>(src, dst, n4); }
        HIP_CHECK(hipEventRecord(ev1));
        HIP_CHECK(hipDeviceSynchronize());
        float ms = 0; HIP_CHECK(hipEventElapsedTime(&ms, ev0, ev1));
        double moved = (double) bytes * 2 * reps;   // read + write
        const double per_rep_s = (ms / reps) / 1000.0;
        printf("copy (read+write) : %8.2f ms/rep   %7.1f GB/s combined (%.1f GB/s each way)\n",
               ms / reps, moved / (ms / 1000.0) / 1e9, bytes / per_rep_s / 1e9);
    }

    hipFree(src); hipFree(dst); hipFree(sink);
    return 0;
}
