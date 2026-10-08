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

/* Source-only, opt-in scalar transfer candidate for exact sealed Linux x86-64
 * engine ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913.
 * The external wrapper must verify the full engine and active preload hashes.
 * This library also checks the exact engine instruction bytes locally.
 * Every unmatched hipMemcpy preserves its arguments, result, and errno.
 * No payload content, scalar value, or kernel argument content is recorded. */
typedef int hipError_t;
typedef enum {
    hipMemcpyHostToHost = 0, hipMemcpyHostToDevice = 1,
    hipMemcpyDeviceToHost = 2, hipMemcpyDeviceToDevice = 3,
    hipMemcpyDefault = 4, hipMemcpyDeviceToDeviceNoCU = 1024
} hipMemcpyKind;
typedef struct ihipStream_t *hipStream_t;
typedef void *hipDeviceptr_t;
#define LEGACY_STREAM ((hipStream_t)1)
#define CALLER_RVA UINT64_C(0x17b91be)
#define GUARD_RVA UINT64_C(0x17b91a5)
#define MAX_FILE_BYTES (UINT64_C(1024) * 1024)

static const unsigned char instruction_guard[] = {
    0x48,0x8b,0x3d,0xdc,0x0d,0x14,0x00,0xba,0x04,0x00,0x00,0x00,
    0x4c,0x89,0xe6,0xb9,0x01,0x00,0x00,0x00,0xe8,0x82,0x90,0x13,
    0x00,0x85,0xc0,0x0f,0x85,0x9f,0x18,0x00,0x00,0x80,0xbc,0x24,
    0xe0,0x01,0x00,0x00,0x00,0x4c,0x89,0xa4,0x24,0xb0,0x00,0x00,0x00
};

/* Native little-endian V1 schema; fixed header/records; no destructor/footer.
 * Header flags: 1 = exact executable path + local instructions validated,
 * 2 = little endian, 4 = scalar passed by value on explicit legacy stream.
 * Record flags: 1 = substitution attempted, 2 = error, 4 = error-path fence.
 * Counts and sequence follow completed append order, starting at 1.
 * substituted_total counts attempted substitutions, including failed calls.
 * fence_result is applicable only with flag 4; no normal-path fence is added. */
struct scalar_header {
    char magic[8];
    uint32_t version, header_size, record_size, clock_id;
    uint64_t main_base, max_file_bytes, caller_rva, guard_rva;
    uint32_t pid, flags;
};
struct scalar_record {
    uint64_t sequence, start_ns, end_ns, tid, substituted_total, error_total;
    int32_t result, fence_result;
    uint32_t flags, reserved;
};
_Static_assert(sizeof(void *) == 8 && sizeof(int) == 4, "sealed x86-64 ABI");
_Static_assert(sizeof(hipMemcpyKind) == 4, "sealed HIP enum ABI");
_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "little endian required");
_Static_assert(sizeof(instruction_guard) == 49, "local code guard size");
_Static_assert(sizeof(struct scalar_header) == 64, "header schema");
_Static_assert(sizeof(struct scalar_record) == 64, "record schema");

typedef hipError_t (*memcpy_fn)(void *, const void *, size_t, hipMemcpyKind);
typedef hipError_t (*fill_fn)(hipDeviceptr_t, int, size_t, hipStream_t);
typedef hipError_t (*sync_fn)(hipStream_t);
static _Atomic(void *) next_memcpy;
static fill_fn next_fill;
static sync_fn next_sync;
static _Atomic int active;
static uintptr_t main_base;
static int guarded_main;
static pid_t candidate_pid;
static int output_fd = -1;
static atomic_flag receipt_lock = ATOMIC_FLAG_INIT;
static _Thread_local int in_receipt;
static uint64_t written_bytes, substitutions, errors;

static void fail_closed(void)
{
    static const char message[] = "scalar_async: candidate guard or receipt failure\n";
    ssize_t diagnostic_written = write(STDERR_FILENO, message, sizeof(message) - 1);
    (void)diagnostic_written;
    _exit(125);
}

static void *required_next(const char *name)
{
    void *address = dlsym(RTLD_NEXT, name);
    if (!address) fail_closed();
    return address;
}

static memcpy_fn original_memcpy(void)
{
    void *address = atomic_load_explicit(&next_memcpy, memory_order_acquire);
    if (!address) {
        address = required_next("hipMemcpy");
        atomic_store_explicit(&next_memcpy, address, memory_order_release);
    }
    return (memcpy_fn)address;
}

static int find_main(struct dl_phdr_info *info, size_t size, void *unused)
{
    (void)size;
    (void)unused;
    if (info->dlpi_name && info->dlpi_name[0]) return 0;
    main_base = (uintptr_t)info->dlpi_addr;
    if (main_base > UINTPTR_MAX - GUARD_RVA - sizeof(instruction_guard)) return 1;
    uintptr_t guard_address = main_base + GUARD_RVA;
    for (ElfW(Half) i = 0; i < info->dlpi_phnum; ++i) {
        const ElfW(Phdr) *p = &info->dlpi_phdr[i];
        if (p->p_type != PT_LOAD || (p->p_flags & (PF_R | PF_X)) != (PF_R | PF_X) ||
            p->p_vaddr > UINTPTR_MAX - main_base) continue;
        uintptr_t begin = main_base + (uintptr_t)p->p_vaddr;
        if (p->p_memsz > UINTPTR_MAX - begin) continue;
        uintptr_t end = begin + (uintptr_t)p->p_memsz;
        if (guard_address >= begin && guard_address <= end &&
            sizeof(instruction_guard) <= end - guard_address &&
            !memcmp((const void *)guard_address, instruction_guard, sizeof(instruction_guard))) {
            guarded_main = 1;
        }
    }
    return 1;
}

__attribute__((constructor)) static void initialize_candidate(void)
{
    int incoming_errno = errno;
    const char *enabled = getenv("HG0172_SCALAR_ASYNC_ENABLE");
    if (!enabled || strcmp(enabled, "1")) { errno = incoming_errno; return; }
    const char *path = getenv("HG0172_SCALAR_ASYNC_PATH");
    if (!path || path[0] != '/') fail_closed();
    static const char expected[] = "/usr/local/bin/flash_serve";
    char executable[4096];
    ssize_t n = readlink("/proc/self/exe", executable, sizeof(executable));
    if (n != (ssize_t)(sizeof(expected) - 1) ||
        memcmp(executable, expected, sizeof(expected) - 1)) fail_closed();
    dl_iterate_phdr(find_main, NULL);
    if (!guarded_main) fail_closed();
    candidate_pid = getpid();
    if (candidate_pid <= 0) fail_closed();
    (void)original_memcpy();
    next_fill = (fill_fn)required_next("hipMemsetD32Async");
    next_sync = (sync_fn)required_next("hipStreamSynchronize");
    output_fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_APPEND | O_CLOEXEC, 0600);
    if (output_fd < 0) fail_closed();
    struct scalar_header header = {
        .magic = {'H','G','S','C','0','1','7','2'}, .version = 1,
        .header_size = sizeof(header), .record_size = sizeof(struct scalar_record),
        .clock_id = CLOCK_BOOTTIME, .main_base = main_base,
        .max_file_bytes = MAX_FILE_BYTES, .caller_rva = CALLER_RVA,
        .guard_rva = GUARD_RVA, .pid = (uint32_t)candidate_pid, .flags = 7
    };
    if (write(output_fd, &header, sizeof(header)) != (ssize_t)sizeof(header)) fail_closed();
    written_bytes = sizeof(header);
    atomic_store_explicit(&active, 1, memory_order_release);
    errno = incoming_errno;
}

static uint64_t timestamp(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_BOOTTIME, &t) || t.tv_sec < 0 || t.tv_nsec < 0 ||
        t.tv_nsec >= 1000000000L ||
        (uint64_t)t.tv_sec > (UINT64_MAX - (uint64_t)t.tv_nsec) / UINT64_C(1000000000))
        fail_closed();
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static void record_substitution(struct scalar_record *record)
{
    if (in_receipt) fail_closed();
    in_receipt = 1;
    while (atomic_flag_test_and_set_explicit(&receipt_lock, memory_order_acquire)) {}
    if (written_bytes > MAX_FILE_BYTES - sizeof(*record) || substitutions == UINT64_MAX)
        fail_closed();
    record->sequence = record->substituted_total = ++substitutions;
    if (record->flags & 2) ++errors;
    record->error_total = errors;
    if (write(output_fd, record, sizeof(*record)) != (ssize_t)sizeof(*record)) fail_closed();
    written_bytes += sizeof(*record);
    atomic_flag_clear_explicit(&receipt_lock, memory_order_release);
    in_receipt = 0;
}

hipError_t hipMemcpy(void *dst, const void *src, size_t sizeBytes, hipMemcpyKind kind)
{
    int incoming_errno = errno;
    memcpy_fn next = original_memcpy();
    uintptr_t caller = (uintptr_t)__builtin_extract_return_addr(__builtin_return_address(0));
    if (!atomic_load_explicit(&active, memory_order_acquire) ||
        caller != main_base + CALLER_RVA || sizeBytes != 4 ||
        kind != hipMemcpyHostToDevice || !dst || !src ||
        ((uintptr_t)dst & (uintptr_t)3) != 0 || getpid() != candidate_pid) {
        errno = incoming_errno;
        return next(dst, src, sizeBytes, kind);
    }
    if (memcmp((const void *)(main_base + GUARD_RVA), instruction_guard, sizeof(instruction_guard)))
        fail_closed();
    /* Consume the original host bits once, by value; no asynchronous host DMA.
     * A D32 fill writes this same int representation once (4 bytes), then
     * original consumers stay ordered on the verified legacy/default queue. */
    int value;
    memcpy(&value, src, sizeof(value));
    long tid = syscall(SYS_gettid);
    if (tid <= 0) fail_closed();
    struct scalar_record record = {.tid = (uint64_t)tid, .flags = 1};
    record.start_ns = timestamp();
    errno = incoming_errno;
    hipError_t result = next_fill(dst, value, 1, LEGACY_STREAM);
    int target_errno = errno;
    record.end_ns = timestamp();
    if (record.end_ns < record.start_ns) fail_closed();
    record.result = result;
    if (result) {
        /* Never replay after a potentially queued fill. Drain before the
         * existing engine error branch exits; preserve the fill error. */
        record.flags |= 2 | 4;
        record.fence_result = next_sync(LEGACY_STREAM);
    }
    record_substitution(&record);
    errno = target_errno;
    return result;
}
