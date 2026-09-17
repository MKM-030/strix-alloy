// hip-host-probe.cpp — can we PIN host memory at the sizes needed for weight storage?
//
// The only way host RAM can hold GPU-computed weights is a pinned (page-locked) mapping
// read directly by the GPU — that is what `ROCm_Host` (ggml-cuda.cu:1302 cudaMallocHost) is.
// If pinning caps out well below the 66 GiB weight set, "use the regular RAM instead"
// cannot work regardless of how much host RAM is free.
#include <hip/hip_runtime.h>
#include <cstdio>

int main() {
    size_t freeb = 0, totb = 0;
    hipMemGetInfo(&freeb, &totb);
    std::printf("pool: free %.2f GB / total %.2f GB\n\n", freeb / 1e9, totb / 1e9);

    const size_t gib = 1ull << 30;
    size_t sizes[] = { 4, 16, 32, 40, 48, 56, 60, 66, 72 };

    std::printf("--- hipHostMalloc (pinned, what ROCm_Host uses) ---\n");
    for (size_t s : sizes) {
        void *p = nullptr;
        hipError_t e = hipHostMalloc(&p, s * gib, hipHostMallocDefault);
        std::printf("  %3zu GiB -> %-24s", s, hipGetErrorString(e));
        if (e == hipSuccess) {
            volatile char *c = (volatile char *)p;
            c[0] = 1; c[(s * gib) - 4096] = 1;
            std::printf(" touched ok");
            hipHostFree(p);
        }
        std::printf("\n");
    }

    std::printf("\n--- hipMallocManaged (for the record) ---\n");
    for (size_t s : sizes) {
        void *p = nullptr;
        hipError_t e = hipMallocManaged(&p, s * gib);
        std::printf("  %3zu GiB -> %s\n", s, hipGetErrorString(e));
        if (e == hipSuccess) hipFree(p);
    }
    return 0;
}
