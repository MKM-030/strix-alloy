/* WSL/DXG adapter: make only private read-only .hgn VMAs writable for HIP pinning.
 * MAP_PRIVATE preserves the read-only model file. No fake registration success,
 * replacement pointers, or fallback device copies. Opt in through LD_PRELOAD.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <pthread.h>

#ifndef HALOGEN_RESEARCH_VGM64
#define HALOGEN_RESEARCH_VGM64 0
#endif
#if HALOGEN_RESEARCH_VGM64 != 0 && HALOGEN_RESEARCH_VGM64 != 1
#error HALOGEN_RESEARCH_VGM64 must be 0 or 1
#endif

typedef int (*reg_fn)(void *, size_t, unsigned);
typedef int (*unreg_fn)(void *);
typedef struct { void *ptr; void *start; size_t bytes, span; } entry;
static entry registered[4096];
static size_t count, total;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;

#if HALOGEN_RESEARCH_VGM64
static int research_profile_valid(void) {
    const char *profile = getenv("HALOGEN_HYBRID_PROFILE");
    return profile && !strcmp(profile, "vgm64-copy48-v1");
}
#endif

void *mmap(void *addr, size_t length, int prot, int flags, int fd, off_t offset) {
    typedef void *(*mmap_fn)(void *, size_t, int, int, int, off_t);
    mmap_fn real = (mmap_fn)dlsym(RTLD_NEXT, "mmap");
    if (!real) return MAP_FAILED;
    if (fd >= 0 && prot == PROT_READ && (flags & MAP_SHARED) && !(flags & MAP_FIXED)) {
        char descriptor[64], path[4096];
        snprintf(descriptor, sizeof descriptor, "/proc/self/fd/%d", fd);
        ssize_t n = readlink(descriptor, path, sizeof path - 1);
        if (n >= 4 && n < (ssize_t)sizeof path) {
            path[n] = 0;
            if (!strcmp(path + n - 4, ".hgn")) {
                flags = (flags & ~MAP_SHARED) | MAP_PRIVATE;
                fprintf(stderr, "[private-rw] private file mapping bytes=%zu path=%s\n", length, path);
            }
        }
    }
    return real(addr, length, prot, flags, fd, offset);
}

static size_t available(void) {
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return 0;
    char line[256]; unsigned long long kb = 0;
    while (fgets(line, sizeof line, f))
        if (sscanf(line, "MemAvailable: %llu kB", &kb) == 1) break;
    fclose(f);
    return (size_t)kb * 1024;
}

static int eligible(uintptr_t p, size_t n) {
    if (!n || p > UINTPTR_MAX - n) return 0;
    FILE *f = fopen("/proc/self/maps", "r");
    if (!f) return 0;
    char line[8192], perms[5]; unsigned long lo, hi;
    int ok = 0;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%lx-%lx %4s", &lo, &hi, perms) != 3) continue;
        if (p >= lo && p + n <= hi) {
            ok = !strcmp(perms, "r--p") && strstr(line, ".hgn") != NULL;
#if HALOGEN_RESEARCH_VGM64
            if (ok) {
                size_t length = strlen(line);
                ok = length >= 5 && !strcmp(line + length - 5, ".hgn\n");
            }
#endif
            if (!ok) fprintf(stderr, "[private-rw] unchanged VMA %s", line);
            break;
        }
    }
    fclose(f);
    if (!ok) fprintf(stderr, "[private-rw] not eligible ptr=%p bytes=%zu\n", (void *)p, n);
    return ok;
}

int hipHostRegister(void *p, size_t n, unsigned flags) {
#if HALOGEN_RESEARCH_VGM64
    if (!research_profile_valid() || !(flags & 8u) || (flags & ~11u)) return 1;
#endif
    reg_fn real = (reg_fn)dlsym(RTLD_NEXT, "hipHostRegister");
    if (!real) return 999;
    pthread_mutex_lock(&lock);
    uintptr_t pointer = (uintptr_t)p;
    if (!n || pointer > UINTPTR_MAX - n) {
        pthread_mutex_unlock(&lock);
        return 1;
    }
    for (size_t i = 0; i < count; ++i) {
        uintptr_t other = (uintptr_t)registered[i].ptr;
        if (pointer < other + registered[i].bytes && other < pointer + n) {
            pthread_mutex_unlock(&lock);
            return 712; /* hipErrorHostMemoryAlreadyRegistered */
        }
    }
    if (!eligible(pointer, n)) {
#if HALOGEN_RESEARCH_VGM64
        pthread_mutex_unlock(&lock);
        return 1;
#else
        int result = real(p, n, flags);
        pthread_mutex_unlock(&lock);
        return result;
#endif
    }
    size_t floor = (size_t)12 << 30;
#if HALOGEN_RESEARCH_VGM64
    size_t cap = (size_t)24 << 30;
#else
    size_t cap = (size_t)72 << 30;
#endif
    size_t avail = available();
    if (count == 4096 || n > cap - total || avail < floor || n > avail - floor) {
        fprintf(stderr, "[private-rw] refuse bytes=%zu registered=%zu available=%zu floor=%zu\n", n, total, avail, floor);
        pthread_mutex_unlock(&lock);
        return 2;
    }
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    uintptr_t first = (uintptr_t)p & ~(page - 1);
    uintptr_t last = ((uintptr_t)p + n + page - 1) & ~(page - 1);
    size_t span = last - first;
    if (mprotect((void *)first, span, PROT_READ | PROT_WRITE) != 0) {
        perror("[private-rw] mprotect");
        pthread_mutex_unlock(&lock);
        return 1;
    }
    int result = real(p, n, flags);
    if (result == 0) {
        registered[count++] = (entry){p, (void *)first, n, span};
        total += n;
    } else {
        mprotect((void *)first, span, PROT_READ);
    }
    fprintf(stderr, "[private-rw] register bytes=%zu flags=%u result=%d total=%zu available=%zu\n", n, flags, result, total, available());
    pthread_mutex_unlock(&lock);
    return result;
}

int hipHostUnregister(void *p) {
    unreg_fn real = (unreg_fn)dlsym(RTLD_NEXT, "hipHostUnregister");
    if (!real) return 999;
    pthread_mutex_lock(&lock);
    int result = real(p);
    if (result == 0) for (size_t i = 0; i < count; ++i) if (registered[i].ptr == p) {
        mprotect(registered[i].start, registered[i].span, PROT_READ);
        total -= registered[i].bytes;
        registered[i] = registered[--count];
        break;
    }
    pthread_mutex_unlock(&lock);
    return result;
}
