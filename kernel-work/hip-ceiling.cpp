// hip-ceiling.cpp - precise allocation ceiling, one path per process.
// Usage: hip-ceiling.exe [device|managed|pinned]
// One binary search per process: sequential alloc/free probing understates the ceiling
// (lazy reclaim / fragmentation), so each path gets a fresh process.
#include <hip/hip_runtime.h>
#include <cstdio>
#include <cstring>

static double gib(size_t b) { return (double)b / 1073741824.0; }

int main(int argc, char ** argv) {
    const char * mode = (argc > 1) ? argv[1] : "device";
    int dev = 0; hipGetDevice(&dev);
    hipDeviceProp_t prop{}; hipGetDeviceProperties(&prop, dev);

    size_t freeb = 0, totb = 0;
    hipError_t me = hipMemGetInfo(&freeb, &totb);
    std::printf("mode=%-8s device=%s\n", mode, prop.name);
    std::printf("  prop.totalGlobalMem = %.2f GiB\n", gib(prop.totalGlobalMem));
    std::printf("  hipMemGetInfo       = %s (%.2f GiB free / %.2f GiB total)\n",
                hipGetErrorString(me), gib(freeb), gib(totb));

    size_t lo = 0, hi = 96ull << 30, best = 0;
    while (hi - lo > (1ull << 20)) {
        size_t mid = lo + (hi - lo) / 2;
        void * p = nullptr;
        hipError_t e;
        if      (strcmp(mode, "managed") == 0) e = hipMallocManaged(&p, mid);
        else if (strcmp(mode, "pinned")  == 0) e = hipHostMalloc(&p, mid, hipHostMallocDefault);
        else                                    e = hipMalloc(&p, mid);
        if (e == hipSuccess) {
            volatile char * c = (volatile char *)p;
            c[0] = 1; c[mid - 4096] = 1;   // prove it is backed, not just reserved
            best = mid; lo = mid;
            if      (strcmp(mode, "managed") == 0) hipFree(p);
            else if (strcmp(mode, "pinned")  == 0) hipHostFree(p);
            else                                    hipFree(p);
        } else {
            (void)hipGetLastError();
            hi = mid;
        }
    }
    std::printf("  ceiling = %zu bytes = %.2f GiB\n", best, gib(best));
    const size_t need = 70874867968ull;
    std::printf("  model needs %.2f GiB -> %s by %.2f GiB\n",
                gib(need), (gib(best) >= gib(need) ? "FITS" : "SHORT"), gib(need) - gib(best));
    return 0;
}
