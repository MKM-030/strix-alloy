#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <link.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

/* Linux x86-64 ABI from the sealed hip_runtime_api.h / driver_types.h.
 * No HIP SDK headers or libraries are needed to build this interposer. */
typedef int hipError_t;
typedef enum {
    hipMemcpyHostToHost = 0, hipMemcpyHostToDevice = 1,
    hipMemcpyDeviceToHost = 2, hipMemcpyDeviceToDevice = 3,
    hipMemcpyDefault = 4, hipMemcpyDeviceToDeviceNoCU = 1024
} hipMemcpyKind;
typedef struct ihipStream_t *hipStream_t;
typedef struct ihipModuleSymbol_t *hipFunction_t;
typedef struct dim3 { uint32_t x, y, z; } dim3;

enum { API_MEMCPY = 1, API_MEMCPY_ASYNC = 2, API_DEVICE_SYNC = 3,
       API_STREAM_SYNC = 4, API_MODULE_LAUNCH = 5, API_LAUNCH = 6 };
enum { RECORD_EXTERNAL_CALLER = 1 };
#define MAX_FILE_BYTES (UINT64_C(64) * 1024 * 1024)
#define MAX_TEXT_RANGES 32

/* Version 1: native little-endian fixed-size records, no trailer.
 * Header flags: bit 0 = main executable ranges validated; bit 1 = little
 * endian; bit 2 = sequence assigned under the append lock after API return.
 * sequence starts at 1, follows file order, and counts successful records.
 * Caller RVA is return-address minus main load base, or UINT64_MAX when
 * outside main executable PF_X/PT_LOAD ranges (record flag bit 0).
 * direction is the original hipMemcpyKind for copies and -1 otherwise.
 * Nonapplicable size/src/dst/stream/function fields are zero. No pointed-to
 * memory, kernel arguments, source bytes, or token contents are read. */
struct census_header {
    char magic[8];
    uint32_t version, header_size, record_size, clock_id;
    uint64_t main_base, max_file_bytes;
    uint32_t pid, reserved32;
    uint64_t flags, reserved64;
};
struct census_record {
    uint64_t sequence, start_ns, end_ns, caller_rva, tid;
    uint64_t size_bytes, src, dst, stream, function;
    int32_t result, direction;
    uint32_t api, flags;
};
_Static_assert(sizeof(void *) == 8 && sizeof(int) == 4, "x86-64 ABI required");
_Static_assert(sizeof(hipMemcpyKind) == 4 && sizeof(dim3) == 12, "sealed HIP ABI required");
_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "little endian required");
_Static_assert(sizeof(struct census_header) == 64, "header schema");
_Static_assert(sizeof(struct census_record) == 96, "record schema");

static _Atomic int enabled;
static atomic_flag append_lock = ATOMIC_FLAG_INIT;
static _Thread_local int in_append;
static int output_fd = -1;
static pid_t observer_pid;
static uint64_t written_bytes, written_records;
static uintptr_t main_base;
static struct { uintptr_t begin, end; } text_ranges[MAX_TEXT_RANGES];
static size_t text_count;
static int main_valid;
static _Atomic(void *) next_memcpy, next_memcpy_async, next_device_sync;
static _Atomic(void *) next_stream_sync, next_module_launch;
static _Atomic(void *) next_launch;

static void disable_observation(void)
{
    atomic_store_explicit(&enabled, 0, memory_order_release);
}

static int find_main(struct dl_phdr_info *info, size_t size, void *data)
{
    (void)size;
    (void)data;
    if (info->dlpi_name && info->dlpi_name[0]) return 0;
    main_base = (uintptr_t)info->dlpi_addr; /* Zero is valid for non-PIE. */
    for (ElfW(Half) i = 0; i < info->dlpi_phnum; ++i) {
        const ElfW(Phdr) *p = &info->dlpi_phdr[i];
        if (p->p_type != PT_LOAD || !(p->p_flags & PF_X)) continue;
        if (text_count == MAX_TEXT_RANGES || p->p_vaddr > UINTPTR_MAX - main_base)
            return 1;
        uintptr_t begin = main_base + (uintptr_t)p->p_vaddr;
        if (!p->p_memsz || p->p_memsz > UINTPTR_MAX - begin) return 1;
        text_ranges[text_count].begin = begin;
        text_ranges[text_count++].end = begin + (uintptr_t)p->p_memsz;
    }
    main_valid = text_count != 0;
    return 1;
}

__attribute__((constructor)) static void initialize_observation(void)
{
    int saved_errno = errno;
    const char *path = getenv("HG0172_HOST_CENSUS_PATH");
    char executable[4096];
    static const char expected[] = "/usr/local/bin/flash_serve";
    if (!path) goto done;
    ssize_t n = readlink("/proc/self/exe", executable, sizeof(executable));
    if (n != (ssize_t)(sizeof(expected) - 1) ||
        memcmp(executable, expected, sizeof(expected) - 1)) goto done;
    dl_iterate_phdr(find_main, NULL);
    if (!main_valid) goto done;
    observer_pid = getpid();
    if (observer_pid <= 0) goto done;
    output_fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_APPEND | O_CLOEXEC, 0600);
    if (output_fd < 0) goto done;
    struct census_header header = {
        .magic = {'H', 'G', 'H', 'C', '0', '1', '7', '2'},
        .version = 1, .header_size = sizeof(header),
        .record_size = sizeof(struct census_record), .clock_id = CLOCK_BOOTTIME,
        .main_base = main_base, .max_file_bytes = MAX_FILE_BYTES,
        .pid = (uint32_t)observer_pid, .flags = 7
    };
    if (write(output_fd, &header, sizeof(header)) != (ssize_t)sizeof(header)) goto done;
    written_bytes = sizeof(header);
    atomic_store_explicit(&enabled, 1, memory_order_release);
done:
    errno = saved_errno;
}

static void *resolve_next(_Atomic(void *) *slot, const char *name)
{
    void *address = atomic_load_explicit(slot, memory_order_acquire);
    if (!address) {
        address = dlsym(RTLD_NEXT, name);
        if (!address) {
            static const char message[] = "host_census: missing RTLD_NEXT HIP target\n";
            ssize_t diagnostic_written = write(STDERR_FILENO, message, sizeof(message) - 1);
            (void)diagnostic_written;
            _exit(127); /* No fabricated HIP result or alternate loader path. */
        }
        atomic_store_explicit(slot, address, memory_order_release);
    }
    return address;
}

static int timestamp(uint64_t *ns)
{
    struct timespec t;
    if (clock_gettime(CLOCK_BOOTTIME, &t) || t.tv_sec < 0 || t.tv_nsec < 0 ||
        t.tv_nsec >= 1000000000L ||
        (uint64_t)t.tv_sec > (UINT64_MAX - (uint64_t)t.tv_nsec) / UINT64_C(1000000000)) {
        disable_observation();
        return 0;
    }
    *ns = (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
    return 1;
}

static int begin_record(struct census_record *record, uintptr_t caller, uint32_t api,
                        void *dst, const void *src, size_t bytes, int direction,
                        hipStream_t stream, hipFunction_t function)
{
    if (!atomic_load_explicit(&enabled, memory_order_acquire)) return 0;
    /* A forked child must not share the file with its copied byte counter. */
    if (getpid() != observer_pid) { disable_observation(); return 0; }
    record->api = api;
    record->caller_rva = UINT64_MAX;
    record->flags = RECORD_EXTERNAL_CALLER;
    for (size_t i = 0; i < text_count; ++i) {
        if (caller >= text_ranges[i].begin && caller < text_ranges[i].end) {
            record->caller_rva = caller - main_base;
            record->flags = 0;
            break;
        }
    }
    long tid = syscall(SYS_gettid);
    if (tid <= 0) { disable_observation(); return 0; }
    record->tid = (uint64_t)tid;
    record->size_bytes = bytes;
    record->src = (uintptr_t)src;
    record->dst = (uintptr_t)dst;
    record->stream = (uintptr_t)stream;
    record->function = (uintptr_t)function;
    record->direction = direction;
    return timestamp(&record->start_ns);
}

static void finish_record(struct census_record *record, hipError_t result)
{
    if (!timestamp(&record->end_ns)) return;
    if (record->end_ns < record->start_ns) { disable_observation(); return; }
    record->result = result;
    if (in_append) { disable_observation(); return; }
    in_append = 1;
    while (atomic_flag_test_and_set_explicit(&append_lock, memory_order_acquire)) {
        if (!atomic_load_explicit(&enabled, memory_order_acquire)) {
            in_append = 0;
            return;
        }
    }
    if (atomic_load_explicit(&enabled, memory_order_acquire)) {
        if (written_bytes > MAX_FILE_BYTES - sizeof(*record)) {
            disable_observation();
        } else {
            record->sequence = written_records + 1;
            ssize_t n = write(output_fd, record, sizeof(*record));
            if (n != (ssize_t)sizeof(*record)) {
                disable_observation();
            } else {
                written_bytes += sizeof(*record);
                ++written_records;
            }
        }
    }
    atomic_flag_clear_explicit(&append_lock, memory_order_release);
    in_append = 0;
}

#define CALLER_ADDRESS ((uintptr_t)__builtin_extract_return_addr(__builtin_return_address(0)))
#define PREPARE(TYPE, SLOT, NAME, API, DST, SRC, BYTES, KIND, STREAM, FUNCTION) \
    int incoming_errno = errno; \
    TYPE next = (TYPE)resolve_next(&(SLOT), (NAME)); \
    struct census_record record = {0}; \
    int observe = begin_record(&record, CALLER_ADDRESS, (API), (DST), (SRC), \
                               (BYTES), (KIND), (STREAM), (FUNCTION)); \
    errno = incoming_errno
#define COMPLETE(CALL) \
    hipError_t result = (CALL); \
    int target_errno = errno; \
    if (observe) finish_record(&record, result); \
    errno = target_errno; \
    return result

hipError_t hipMemcpy(void *dst, const void *src, size_t sizeBytes, hipMemcpyKind kind)
{
    typedef hipError_t (*target_type)(void *, const void *, size_t, hipMemcpyKind);
    PREPARE(target_type, next_memcpy, "hipMemcpy", API_MEMCPY,
            dst, src, sizeBytes, kind, NULL, NULL);
    COMPLETE(next(dst, src, sizeBytes, kind));
}

hipError_t hipMemcpyAsync(void *dst, const void *src, size_t sizeBytes,
                          hipMemcpyKind kind, hipStream_t stream)
{
    typedef hipError_t (*target_type)(void *, const void *, size_t, hipMemcpyKind, hipStream_t);
    PREPARE(target_type, next_memcpy_async, "hipMemcpyAsync", API_MEMCPY_ASYNC,
            dst, src, sizeBytes, kind, stream, NULL);
    COMPLETE(next(dst, src, sizeBytes, kind, stream));
}

hipError_t hipDeviceSynchronize(void)
{
    typedef hipError_t (*target_type)(void);
    PREPARE(target_type, next_device_sync, "hipDeviceSynchronize", API_DEVICE_SYNC,
            NULL, NULL, 0, -1, NULL, NULL);
    COMPLETE(next());
}

hipError_t hipStreamSynchronize(hipStream_t stream)
{
    typedef hipError_t (*target_type)(hipStream_t);
    PREPARE(target_type, next_stream_sync, "hipStreamSynchronize", API_STREAM_SYNC,
            NULL, NULL, 0, -1, stream, NULL);
    COMPLETE(next(stream));
}

hipError_t hipModuleLaunchKernel(hipFunction_t f,
    unsigned int gridDimX, unsigned int gridDimY, unsigned int gridDimZ,
    unsigned int blockDimX, unsigned int blockDimY, unsigned int blockDimZ,
    unsigned int sharedMemBytes, hipStream_t stream, void **kernelParams, void **extra)
{
    typedef hipError_t (*target_type)(hipFunction_t, unsigned int, unsigned int,
        unsigned int, unsigned int, unsigned int, unsigned int, unsigned int,
        hipStream_t, void **, void **);
    PREPARE(target_type, next_module_launch, "hipModuleLaunchKernel", API_MODULE_LAUNCH,
            NULL, NULL, 0, -1, stream, f);
    COMPLETE(next(f, gridDimX, gridDimY, gridDimZ, blockDimX, blockDimY, blockDimZ,
                  sharedMemBytes, stream, kernelParams, extra));
}

/* hipLaunchKernel is the exact engine enqueue API at caller RVA 0x17be948.
 * A prepended observer sees main-engine calls; the existing active preload's
 * own RTLD_NEXT preflight copies intentionally bypass this earlier DSO. */
hipError_t hipLaunchKernel(const void *function_address, dim3 numBlocks,
    dim3 dimBlocks, void **args, size_t sharedMemBytes, hipStream_t stream)
{
    typedef hipError_t (*target_type)(const void *, dim3, dim3, void **, size_t, hipStream_t);
    PREPARE(target_type, next_launch, "hipLaunchKernel", API_LAUNCH,
            NULL, NULL, 0, -1, stream, (hipFunction_t)function_address);
    COMPLETE(next(function_address, numBlocks, dimBlocks, args, sharedMemBytes, stream));
}
