// hip-managed-probe.cpp — can hipMallocManaged reach host RAM on this Windows WDDM carve?
// Decides whether the freed host RAM (115 GB) is usable as GPU-side weight storage.
#include <hip/hip_runtime.h>
#include <cstdio>

int main() {
    int dev = 0;
    hipGetDevice(&dev);
    hipDeviceProp_t prop{};
    hipGetDeviceProperties(&prop, dev);
    size_t freeb = 0, totb = 0;
    hipMemGetInfo(&freeb, &totb);
    std::printf("device            : %s\n", prop.name);
    std::printf("integrated        : %d  (0 = dGPU)\n", prop.integrated);
    std::printf("managedMemory     : %d\n", prop.managedMemory);
    std::printf("hipMemGetInfo     : free %.2f GB / total %.2f GB\n",
                freeb / 1e9, totb / 1e9);
    std::printf("cudaMemGetInfo-ish pool is the carve-bounded device pool\n\n");

    const size_t gib = 1ull << 30;
    size_t sizes[] = { 4, 16, 32, 40, 48, 56, 58, 60, 64, 70, 80 };
    for (size_t s : sizes) {
        void *p = nullptr;
        hipError_t e = hipMallocManaged(&p, s * gib);
        std::printf("hipMallocManaged %3zu GiB -> %-28s", s, hipGetErrorString(e));
        if (e == hipSuccess) {
            // touch a page inside the allocation: proves it is backed, not just reserved
            volatile char *c = (volatile char *)p;
            c[0] = 1; c[(s * gib) - 4096] = 1;
            std::printf(" backed+resident");
            hipFree(p);
        }
        std::printf("\n");
    }

    // Same question for plain device malloc, for contrast.
    std::printf("\n");
    size_t plains[] = { 32, 48, 56, 60, 64, 70 };
    for (size_t s : plains) {
        void *p = nullptr;
        hipError_t e = hipMalloc(&p, s * gib);
        std::printf("hipMalloc       %3zu GiB -> %s\n", s, hipGetErrorString(e));
        if (e == hipSuccess) hipFree(p);
    }
    return 0;
}
