/* Opt-in, bounded immutable-weight copies in dedicated GPU memory.
 * Preload BEFORE hip-register-private-rw.so. Copy only read-only .hgn ranges
 * requested with hipHostRegisterReadOnly; remaining ranges use real registration.
 * Each emulated range owns a real hipMalloc allocation and completed H2D copy.
 * No device-pointer dereference on the CPU, no forged capacity, no driver edit.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

#ifndef HALOGEN_RESEARCH_VGM64
#define HALOGEN_RESEARCH_VGM64 0
#endif
#if HALOGEN_RESEARCH_VGM64 != 0 && HALOGEN_RESEARCH_VGM64 != 1
#error HALOGEN_RESEARCH_VGM64 must be 0 or 1
#endif
#ifndef HALOGEN_PREFLIGHT_V1
#define HALOGEN_PREFLIGHT_V1 0
#endif
#if HALOGEN_PREFLIGHT_V1 != 0 && HALOGEN_PREFLIGHT_V1 != 1
#error HALOGEN_PREFLIGHT_V1 must be 0 or 1
#endif
#if HALOGEN_PREFLIGHT_V1 && !HALOGEN_RESEARCH_VGM64
#error HALOGEN_PREFLIGHT_V1 requires HALOGEN_RESEARCH_VGM64=1
#endif
#if HALOGEN_PREFLIGHT_V1
#include "hip-preflight-plan.h"
#endif

typedef int (*reg_fn)(void *, size_t, unsigned);
typedef int (*get_fn)(void **, void *, unsigned);
typedef int (*free_fn)(void *);
typedef int (*malloc_fn)(void **, size_t);
typedef int (*copy_fn)(void *, const void *, size_t, int);
typedef struct { uintptr_t host; void *device; size_t bytes; } entry;
static entry copies[4096];
static size_t count, total, cap;
static int reclaim_copy;
#if HALOGEN_RESEARCH_VGM64
static int config_valid;
#endif
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t once = PTHREAD_ONCE_INIT;

#if HALOGEN_PREFLIGHT_V1
typedef struct { uintptr_t pointer; size_t bytes; int copy; } planned_range;
static planned_range planned[252];
static size_t planned_count, planned_next, host_total, expected_copy, expected_host;
static size_t executed_copy, executed_host;
static unsigned preflight_phase;
static int preflight_poisoned;
/* The first failed copy poisons registration permanently, so at most one
 * uncredited allocation can need deferred cleanup. Never expose it via copies. */
static entry cleanup_pending;

/* All state transitions use mutex. Poison is irreversible, including cleanup. */
static int preflight_reject(const char *reason) {
    preflight_poisoned = 1;
    fprintf(stderr, "[preflight] reject phase=%u next=%zu copied=%zu host=%zu reason=%s\n",
            preflight_phase, planned_next, total, host_total, reason);
    return 1;
}

static int preflight_copy_fits(size_t bytes, size_t used, size_t entries) {
    return cap && entries < 4096 && used <= cap && bytes <= cap - used;
}
#endif

static void configure(void) {
    const char *value = getenv("HALOGEN_HYBRID_COPY_BYTES");
#if HALOGEN_PREFLIGHT_V1
    const char *preflight_profile = getenv("HALOGEN_PREFLIGHT_PROFILE");
    const char *preflight_reclaim = getenv("HALOGEN_HYBRID_RECLAIM_COPY");
    if (!preflight_profile || strcmp(preflight_profile, "flash0138-copy48-v1") ||
        !value || strcmp(value, "51539607552") ||
        !preflight_reclaim || strcmp(preflight_reclaim, "1")) {
        fprintf(stderr, "[preflight] reject reason=exact-runtime-optins\n");
        return;
    }
#endif
#if HALOGEN_RESEARCH_VGM64
    const char *profile = getenv("HALOGEN_HYBRID_PROFILE");
    if (!profile || strcmp(profile, "vgm64-copy48-v1") || !value || !*value) {
        fprintf(stderr, "[hybrid] research profile/copy cap missing or invalid\n");
        return;
    }
    for (const unsigned char *digit = (const unsigned char *)value; *digit; ++digit)
        if (*digit < '0' || *digit > '9') {
            fprintf(stderr, "[hybrid] invalid research copy cap\n");
            return;
        }
#else
    if (!value || !*value) return;
#endif
    char *end;
    errno = 0;
    unsigned long long parsed = strtoull(value, &end, 10);
    if (errno || *end || *value == '-' ||
#if HALOGEN_RESEARCH_VGM64
        !parsed || parsed > UINT64_C(51539607552)) {
#else
        parsed > ((size_t)28 << 30)) {
#endif
        fprintf(stderr, "[hybrid] invalid copy cap; device-copy path disabled\n");
        return;
    }
    cap = (size_t)parsed;
#if HALOGEN_RESEARCH_VGM64
    config_valid = 1;
#endif
    const char *reclaim = getenv("HALOGEN_HYBRID_RECLAIM_COPY");
    reclaim_copy = reclaim && !strcmp(reclaim, "1");
    fprintf(stderr, "[hybrid] device-copy cap=%zu bytes\n", cap);
}

static size_t available(void) {
    FILE *file = fopen("/proc/meminfo", "r");
    if (!file) return 0;
    char line[256];
    unsigned long long kb = 0;
    while (fgets(line, sizeof line, file))
        if (sscanf(line, "MemAvailable: %llu kB", &kb) == 1) break;
    fclose(file);
    return (size_t)kb * 1024;
}

static int immutable_model(uintptr_t pointer, size_t bytes) {
    FILE *file = fopen("/proc/self/maps", "r");
    if (!file) return 0;
    char line[8192], perms[5];
    unsigned long low, high;
    int found = 0;
    while (fgets(line, sizeof line, file)) {
        if (sscanf(line, "%lx-%lx %4s", &low, &high, perms) != 3) continue;
        if (pointer >= low && pointer + bytes <= high) {
            char *suffix = strstr(line, ".hgn");
            found = !strcmp(perms, "r--p") && suffix && suffix[4] == '\n';
            break;
        }
    }
    fclose(file);
    return found;
}

#if HALOGEN_PREFLIGHT_V1
int halogen_hybrid_preflight_v1(
    uintptr_t mapping_base, size_t mapping_bytes,
    const struct halogen_preflight_range_v1 *ranges, size_t range_count,
    size_t aggregate_bytes, size_t *host_required_bytes) {
    pthread_once(&once, configure);
    pthread_mutex_lock(&mutex);
    const char *failure = NULL;
    planned_range candidate[252];
    size_t sum = 0, copied = total, host = host_total, entries = count;
    size_t phase_copy = 0, phase_host = 0;
    if (preflight_poisoned || !config_valid) failure = "state-or-config";
    else if (preflight_phase > 1 || planned_next != planned_count ||
             total != executed_copy || host_total != executed_host ||
             (preflight_phase && (total != expected_copy || host_total != expected_host)) ||
             (!preflight_phase && (count || total || host_total))) failure = "phase-state";
    else if (!ranges || !host_required_bytes || !mapping_base ||
             mapping_bytes > UINTPTR_MAX - mapping_base) failure = "mapping-or-pointer";
    else if (mapping_bytes != (preflight_phase ? UINT64_C(2572466560) : UINT64_C(124068083904)) ||
             range_count != (preflight_phase ? 1u : 252u) ||
             aggregate_bytes != (preflight_phase ? UINT64_C(2572351872) : UINT64_C(70434994368)))
        failure = "phase-shape";
    else if ((uintptr_t)ranges > UINTPTR_MAX - range_count * sizeof *ranges ||
             (uintptr_t)host_required_bytes > UINTPTR_MAX - sizeof *host_required_bytes)
        failure = "metadata-pointer-overflow";
    if (!failure) for (size_t i = 0; i < range_count; ++i) {
        uint64_t begin = ranges[i].begin, end = ranges[i].end;
        if (begin >= end || end > mapping_bytes || end - begin > SIZE_MAX ||
            (i && begin < ranges[i - 1].end)) { failure = "range-order-or-bounds"; break; }
        size_t bytes = (size_t)(end - begin);
        if (bytes > SIZE_MAX - sum) { failure = "range-sum-overflow"; break; }
        uintptr_t pointer = mapping_base + (uintptr_t)begin;
        if (!immutable_model(pointer, bytes)) { failure = "immutable-hgn-eligibility"; break; }
        int copy = preflight_copy_fits(bytes, copied, entries);
        candidate[i] = (planned_range){pointer, bytes, copy};
        sum += bytes;
        if (copy) { copied += bytes; phase_copy += bytes; ++entries; }
        else {
            if (host > UINT64_C(25769803776) || bytes > UINT64_C(25769803776) - host) {
                failure = "host-ceiling"; break;
            }
            host += bytes; phase_host += bytes;
        }
    }
    if (!failure && (sum != aggregate_bytes ||
        phase_copy != (preflight_phase ? 0 : UINT64_C(50433337536)) ||
        phase_host != (preflight_phase ? UINT64_C(2572351872) : UINT64_C(20001656832))))
        failure = "sum-or-placement";
    if (failure) {
        int result = preflight_reject(failure);
        pthread_mutex_unlock(&mutex);
        return result;
    }
    memcpy(planned, candidate, range_count * sizeof *planned);
    planned_count = range_count;
    planned_next = 0;
    expected_copy = copied;
    expected_host = host;
    ++preflight_phase;
    *host_required_bytes = phase_host;
    fprintf(stderr, "[preflight] plan phase=%u ranges=%zu aggregate=%zu copy=%zu host=%zu\n",
            preflight_phase, range_count, aggregate_bytes, phase_copy, phase_host);
    pthread_mutex_unlock(&mutex);
    return 0;
}

/* Called only after successful real copy/registration; never on retry/cleanup. */
static int preflight_advance(int copied, size_t bytes) {
    if (copied) executed_copy += bytes;
    else { host_total += bytes; executed_host += bytes; }
    ++planned_next;
    if (planned_next == planned_count) {
        if (total != expected_copy || host_total != expected_host)
            return preflight_reject("completion-totals");
        fprintf(stderr, "[preflight] complete phase=%u copied=%zu host=%zu\n",
                preflight_phase, total, host_total);
    }
    return 0;
}
#endif

/* Optional startup-only cache relief AFTER the synchronous H2D completed.
 * The GPU allocation owns its copy. Keep the CPU mapping/address valid and
 * drop only whole pages whose bytes match the backing file. A read-only VMA
 * alone does NOT prove the absence of earlier private COW modifications.
 * Caller/model contract: these immutable input files and mappings are not
 * concurrently changed. Registered ranges never enter this function.
 */
static void reclaim_completed_copy(uintptr_t pointer, size_t bytes) {
    if (!reclaim_copy || bytes < (size_t)1 << 20) return;
    long page_value = sysconf(_SC_PAGESIZE);
    if (page_value <= 0) return;
    size_t page = (size_t)page_value;
    size_t prefix = (page - pointer % page) % page;
    if (prefix >= bytes) return;
    uintptr_t first = pointer + prefix;
    size_t span = (bytes - prefix) / page * page;
    if (!span) return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps) return;
    char line[8192], permissions[5];
    unsigned long low, high;
    unsigned long long offset, inode;
    unsigned device_major, device_minor;
    int fd = -1;
    off_t file_offset = 0;
    struct stat before, after;
    while (fgets(line, sizeof line, maps)) {
        int start = 0;
        if (sscanf(line, "%lx-%lx %4s %llx %x:%x %llu %n", &low, &high,
                   permissions, &offset, &device_major, &device_minor, &inode, &start) != 7)
            continue;
        if (pointer < low || pointer + bytes > high) continue;
        if (strcmp(permissions, "r--p") || start <= 0 || line[start] != '/') break;
        char *path = line + start;
        size_t length = strlen(path);
        if (length < 5 || path[length - 1] != '\n') break;
        path[--length] = 0;
        if (strcmp(path + length - 4, ".hgn") || strchr(path, '\\')) break;
        if (offset > INT64_MAX || first - low > (uint64_t)INT64_MAX - offset) break;
        uint64_t position = offset + (first - low);
        if (span > (uint64_t)INT64_MAX - position) break;
        fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0) break;
        if (fstat(fd, &before) || !S_ISREG(before.st_mode) || before.st_size < 0 ||
            (uint64_t)before.st_ino != inode || major(before.st_dev) != device_major ||
            minor(before.st_dev) != device_minor || position + span > (uint64_t)before.st_size) {
            close(fd);
            fd = -1;
            break;
        }
        file_offset = (off_t)position;
        break;
    }
    fclose(maps);
    if (fd < 0) {
        fprintf(stderr, "[hybrid] copy-cache skipped: file identity/range not verified\n");
        return;
    }
    size_t chunk = (size_t)1 << 20;
    unsigned char *check = malloc(chunk);
    int matches = check != NULL;
    for (size_t at = 0; matches && at < span;) {
        size_t wanted = span - at < chunk ? span - at : chunk;
        ssize_t got = pread(fd, check, wanted, file_offset + (off_t)at);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0 || memcmp(check, (void *)(first + at), (size_t)got)) {
            matches = 0;
            break;
        }
        at += (size_t)got;
    }
    free(check);
    if (fstat(fd, &after) || before.st_size != after.st_size ||
        before.st_mtim.tv_sec != after.st_mtim.tv_sec ||
        before.st_mtim.tv_nsec != after.st_mtim.tv_nsec ||
        before.st_ctim.tv_sec != after.st_ctim.tv_sec ||
        before.st_ctim.tv_nsec != after.st_ctim.tv_nsec) matches = 0;
    if (!matches) {
        fprintf(stderr, "[hybrid] copy-cache skipped: host/file bytes differ or verification failed\n");
    } else if (madvise((void *)first, span, MADV_DONTNEED)) {
        fprintf(stderr, "[hybrid] copy-cache madvise failed errno=%d\n", errno);
    } else {
        int result = posix_fadvise(fd, file_offset, (off_t)span, POSIX_FADV_DONTNEED);
        fprintf(stderr, "[hybrid] copy-cache advised bytes=%zu file_offset=%lld result=%d\n",
                span, (long long)file_offset, result);
    }
    close(fd);
}

int hipHostRegister(void *host, size_t bytes, unsigned flags) {
#if !HALOGEN_RESEARCH_VGM64
    reg_fn next = (reg_fn)dlsym(RTLD_NEXT, "hipHostRegister");
    if (!next) return 999;
#endif
    pthread_once(&once, configure);
#if HALOGEN_RESEARCH_VGM64 && !HALOGEN_PREFLIGHT_V1
    if (!config_valid) return 1;
    reg_fn next = (reg_fn)dlsym(RTLD_NEXT, "hipHostRegister");
    if (!next) return 999;
#endif
    uintptr_t pointer = (uintptr_t)host;
#if !HALOGEN_PREFLIGHT_V1
    if (!bytes || pointer > UINTPTR_MAX - bytes) return 1;
#endif
    pthread_mutex_lock(&mutex);
#if HALOGEN_PREFLIGHT_V1
    reg_fn next = (reg_fn)dlsym(RTLD_NEXT, "hipHostRegister");
    if (preflight_poisoned || !config_valid || !next || !preflight_phase ||
        planned_next >= planned_count || !bytes || !pointer || pointer > UINTPTR_MAX - bytes ||
        flags != 10 || pointer != planned[planned_next].pointer ||
        bytes != planned[planned_next].bytes || total != executed_copy || host_total != executed_host) {
        int result = preflight_reject("registration-state-or-range");
        pthread_mutex_unlock(&mutex);
        return result;
    }
#endif
    for (size_t i = 0; i < count; ++i) {
        if (pointer < copies[i].host + copies[i].bytes &&
            copies[i].host < pointer + bytes) {
#if HALOGEN_PREFLIGHT_V1
            preflight_reject("registration-overlap");
#endif
            pthread_mutex_unlock(&mutex);
            return 1; /* Reject duplicate/overlapping registrations. */
        }
    }
#if HALOGEN_PREFLIGHT_V1
    int immutable = immutable_model(pointer, bytes);
    int actual_copy = preflight_copy_fits(bytes, total, count) && immutable;
    if (!immutable || actual_copy != planned[planned_next].copy) {
        int result = preflight_reject("registration-branch-drift");
        pthread_mutex_unlock(&mutex);
        return result;
    }
    if (!actual_copy) {
#else
    if (!cap || !(flags & 8u) || (flags & ~11u) ||
        count == 4096 || bytes > cap - total || !immutable_model(pointer, bytes)) {
#endif
        int result = next(host, bytes, flags);
#if HALOGEN_PREFLIGHT_V1
        if (result) preflight_reject("host-registration-failed");
        else result = preflight_advance(0, bytes);
#endif
        pthread_mutex_unlock(&mutex);
        return result;
    }
    size_t free_host = available(), reserve = (size_t)12 << 30;
    if (free_host < reserve || bytes > free_host - reserve) {
#if HALOGEN_PREFLIGHT_V1
        preflight_reject("guest-reserve");
#endif
        fprintf(stderr, "[hybrid] host reserve refusal bytes=%zu available=%zu\n", bytes, free_host);
        pthread_mutex_unlock(&mutex);
        return 2;
    }
    malloc_fn allocate = (malloc_fn)dlsym(RTLD_NEXT, "hipMalloc");
    free_fn release = (free_fn)dlsym(RTLD_NEXT, "hipFree");
    copy_fn copy = (copy_fn)dlsym(RTLD_NEXT, "hipMemcpy");
    if (!allocate || !release || !copy) {
#if HALOGEN_PREFLIGHT_V1
        preflight_reject("missing-hip-symbol");
#endif
        pthread_mutex_unlock(&mutex);
        return 999;
    }
    void *device = NULL;
    int result = allocate(&device, bytes);
    if (result == 0) result = copy(device, host, bytes, 1);
    if (result == 0) {
        copies[count++] = (entry){pointer, device, bytes};
        total += bytes;
        reclaim_completed_copy(pointer, bytes);
    } else if (device) {
        int cleanup = release(device);
        if (cleanup) fprintf(stderr, "[hybrid] failed-copy cleanup HIP error=%d\n", cleanup);
#if HALOGEN_PREFLIGHT_V1
        if (cleanup) cleanup_pending = (entry){pointer, device, bytes};
#endif
    }
    fprintf(stderr, "[hybrid] device-copy bytes=%zu result=%d copied=%zu\n", bytes, result, total);
#if HALOGEN_PREFLIGHT_V1
    if (result) preflight_reject("device-copy-failed");
    else result = preflight_advance(1, bytes);
#endif
    pthread_mutex_unlock(&mutex);
    return result;
}

int hipHostGetDevicePointer(void **device, void *host, unsigned flags) {
    if (!device) return 1;
    pthread_mutex_lock(&mutex);
    uintptr_t pointer = (uintptr_t)host;
#if HALOGEN_PREFLIGHT_V1
    if (cleanup_pending.device && pointer >= cleanup_pending.host &&
        pointer - cleanup_pending.host < cleanup_pending.bytes) {
        pthread_mutex_unlock(&mutex);
        return 1;
    }
#endif
    for (size_t i = 0; i < count; ++i) {
        if (pointer >= copies[i].host && pointer - copies[i].host < copies[i].bytes) {
            if (flags) { pthread_mutex_unlock(&mutex); return 1; }
            *device = (char *)copies[i].device + (pointer - copies[i].host);
            pthread_mutex_unlock(&mutex);
            return 0;
        }
    }
    pthread_mutex_unlock(&mutex);
    get_fn next = (get_fn)dlsym(RTLD_NEXT, "hipHostGetDevicePointer");
    return next ? next(device, host, flags) : 999;
}

int hipHostUnregister(void *host) {
    pthread_mutex_lock(&mutex);
#if HALOGEN_PREFLIGHT_V1
    preflight_reject("unregister-invalidates-plan");
    if (cleanup_pending.device && (uintptr_t)host == cleanup_pending.host) {
        free_fn release = (free_fn)dlsym(RTLD_NEXT, "hipFree");
        int result = release ? release(cleanup_pending.device) : 999;
        fprintf(stderr, "[preflight] cleanup-only bytes=%zu result=%d\n",
                cleanup_pending.bytes, result);
        if (!result) cleanup_pending = (entry){0};
        pthread_mutex_unlock(&mutex);
        return result;
    }
#endif
    for (size_t i = 0; i < count; ++i) {
        if ((uintptr_t)host == copies[i].host) {
            free_fn release = (free_fn)dlsym(RTLD_NEXT, "hipFree");
            int result = release ? release(copies[i].device) : 999;
            if (result == 0) {
                total -= copies[i].bytes;
                copies[i] = copies[--count];
            }
            pthread_mutex_unlock(&mutex);
            return result;
        }
    }
    pthread_mutex_unlock(&mutex);
    free_fn next = (free_fn)dlsym(RTLD_NEXT, "hipHostUnregister");
    return next ? next(host) : 999;
}
