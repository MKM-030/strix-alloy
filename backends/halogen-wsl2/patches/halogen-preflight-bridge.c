/* Research-only, exact-engine, process-local demand-load correction.
 * Never changes memory reports, admission floor, comparison or the disk ELF.
 * Link ONLY with the preflight-enabled hybrid planner and the assembly file. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <link.h>
#include <openssl/evp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>
#include "hip-preflight-plan.h"

#if !defined(__x86_64__) || !defined(__linux__)
#error "This bridge supports only the audited Linux x86-64 engine"
#endif
#ifdef HALOGEN_BRIDGE_FIXTURE
/* Compile-time-only tiny CPU ELF. Production contains no runtime bypass. */
#if HALOGEN_BRIDGE_FIXTURE != 1
#error "HALOGEN_BRIDGE_FIXTURE must equal 1 when defined"
#endif
#define ENGINE_SHA HALOGEN_BRIDGE_FIXTURE_SHA256
#define ENGINE_RVA ((uintptr_t)HALOGEN_BRIDGE_FIXTURE_RVA)
#else
#define ENGINE_SHA "39382df17e7bd922a302d7dbfaaaa80d5dbb4a813e50268265a74c70c8679625"
#define ENGINE_RVA ((uintptr_t)0xc8f020)
#endif
#define FLOOR_BYTES UINT64_C(17179869184)
#define MAX_RANGES 65536U
static const unsigned char signature[] = {
    0x48,0x8b,0x44,0x24,0x58, 0x48,0x01,0xd0, 0x48,0x29,0xf0,
    0x4c,0x8b,0x6c,0x24,0x30, 0x4c,0x8b,0x7c,0x24,0x08,
    0x0f,0x87,0x1f,0x08,0x00,0x00
};
static int activated, trace_only;
extern void halogen_preflight_trampoline(void);

static _Noreturn void fatal(int code, const char *reason) {
    dprintf(STDERR_FILENO, "[preflight-bridge] fatal code=%d reason=%s\n", code, reason);
    _exit(code);
}
static int exact_env(const char *name, const char *wanted) {
    const char *value = getenv(name);
    return value && !strcmp(value, wanted);
}
static void configuration(void) {
    if (!exact_env("HALOGEN_PREFLIGHT_PROFILE", "flash0138-copy48-v1") ||
        !exact_env("HALOGEN_HYBRID_PROFILE", "vgm64-copy48-v1") ||
        !exact_env("HALOGEN_HYBRID_COPY_BYTES", "51539607552") ||
        !exact_env("HALOGEN_HYBRID_RECLAIM_COPY", "1") ||
        !exact_env("HALOGEN_FLASH_PIN_TRUNK", "1")) fatal(78, "profile");
    const char *trace = getenv("HALOGEN_PREFLIGHT_TRACE_ONLY");
    if (trace && strcmp(trace, "0") && strcmp(trace, "1")) fatal(78, "trace-option");
    trace_only = trace && !strcmp(trace, "1");
}

static int same_file(const struct stat *a, const struct stat *b) {
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
        a->st_size == b->st_size && a->st_mode == b->st_mode &&
        a->st_mtim.tv_sec == b->st_mtim.tv_sec && a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec == b->st_ctim.tv_sec && a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}

static struct stat verify_file(void) {
    struct stat first, last; Elf64_Ehdr eh;
    int fd = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &first) || !S_ISREG(first.st_mode) || first.st_size < (off_t)sizeof eh)
        fatal(78, "executable-open-stat");
    if (pread(fd, &eh, sizeof eh, 0) != sizeof eh ||
        memcmp(eh.e_ident, ELFMAG, SELFMAG) || eh.e_ident[EI_CLASS] != ELFCLASS64 ||
        eh.e_ident[EI_DATA] != ELFDATA2LSB || eh.e_machine != EM_X86_64 ||
        eh.e_type != ET_DYN || eh.e_phentsize != sizeof(Elf64_Phdr) || !eh.e_phnum)
        fatal(78, "elf-format");
    void *crypto = dlopen("libcrypto.so.3", RTLD_NOW | RTLD_LOCAL);
    if (!crypto) fatal(78, "crypto-open");
#define CRYPTO_FN(name) __typeof__(&name) p_##name = (__typeof__(&name))dlsym(crypto, #name); \
    if (!p_##name) fatal(78, "crypto-symbol")
    CRYPTO_FN(EVP_MD_CTX_new); CRYPTO_FN(EVP_MD_CTX_free); CRYPTO_FN(EVP_sha256);
    CRYPTO_FN(EVP_DigestInit_ex); CRYPTO_FN(EVP_DigestUpdate); CRYPTO_FN(EVP_DigestFinal_ex);
#undef CRYPTO_FN
    EVP_MD_CTX *ctx = p_EVP_MD_CTX_new();
    if (!ctx || p_EVP_DigestInit_ex(ctx, p_EVP_sha256(), NULL) != 1) fatal(78, "digest-init");
    unsigned char buffer[65536], digest[EVP_MAX_MD_SIZE];
    off_t consumed = 0;
    while (consumed < first.st_size) {
        size_t wanted = (uint64_t)(first.st_size - consumed) < sizeof buffer ?
            (size_t)(first.st_size - consumed) : sizeof buffer;
        ssize_t n = pread(fd, buffer, wanted, consumed);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0 || p_EVP_DigestUpdate(ctx, buffer, (size_t)n) != 1) fatal(78, "digest-read");
        consumed += n;
    }
    unsigned int length = 0;
    if (pread(fd, buffer, 1, consumed) != 0 || fstat(fd, &last) || !same_file(&first, &last) ||
        p_EVP_DigestFinal_ex(ctx, digest, &length) != 1 || length != 32)
        fatal(78, "digest-consistency");
    p_EVP_MD_CTX_free(ctx);
    if (close(fd) || dlclose(crypto)) fatal(78, "digest-close");
    char hex[65];
    for (size_t i = 0; i < 32; ++i) snprintf(hex + i * 2, 3, "%02x", digest[i]);
    if (strcmp(hex, ENGINE_SHA)) fatal(78, "elf-sha256");
    return first;
}

/* /proc maps validates actual page state, including mprotect changes absent
 * from ELF headers. A span must be fully contained in one readable mapping. */
static int mapped_span(uintptr_t start, size_t length, const char *wanted,
                       const struct stat *identity, uint64_t file_offset) {
    if (!start || !length || length > UINTPTR_MAX - start) return 0;
    FILE *f = fopen("/proc/self/maps", "re");
    if (!f) return 0;
    char line[4096], perms[5];
    unsigned long lo, hi, offset, inode; unsigned int major_id, minor_id;
    int found = 0;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%lx-%lx %4s %lx %x:%x %lu", &lo, &hi, perms,
                   &offset, &major_id, &minor_id, &inode) != 7) continue;
        if (start < lo || start + length > hi) continue;
        if (wanted ? strcmp(perms, wanted) != 0 : perms[0] != 'r') break;
        if (identity && (inode != identity->st_ino || major_id != major(identity->st_dev) ||
                         minor_id != minor(identity->st_dev) ||
                         file_offset != offset + (start - lo))) break;
        found = 1; break;
    }
    if (ferror(f)) found = 0;
    if (fclose(f)) return 0;
    return found;
}

struct target { uintptr_t site, page; size_t page_bytes; uint64_t file_offset; int count; };
static int main_headers(struct dl_phdr_info *info, size_t ignored, void *opaque) {
    (void)ignored;
    if (info->dlpi_name && info->dlpi_name[0]) return 0;
    struct target *target = opaque;
    if (ENGINE_RVA > UINTPTR_MAX - info->dlpi_addr) fatal(78, "base-overflow");
    uintptr_t site = info->dlpi_addr + ENGINE_RVA;
    if (site > UINTPTR_MAX - sizeof signature) fatal(78, "site-overflow");
    uintptr_t page = site & ~(uintptr_t)(target->page_bytes - 1);
    if (page > UINTPTR_MAX - target->page_bytes || site + sizeof signature > page + target->page_bytes)
        fatal(78, "page-boundary");
    for (size_t i = 0; i < info->dlpi_phnum; ++i) {
        const Elf64_Phdr *p = &info->dlpi_phdr[i];
        if (p->p_type != PT_LOAD || p->p_flags != (PF_R | PF_X)) continue;
        if (p->p_vaddr > UINTPTR_MAX - info->dlpi_addr || p->p_filesz > UINTPTR_MAX - p->p_vaddr ||
            p->p_memsz > UINTPTR_MAX - (info->dlpi_addr + p->p_vaddr)) fatal(78, "segment-overflow");
        uintptr_t begin = info->dlpi_addr + p->p_vaddr;
        uintptr_t end = begin + p->p_memsz;
        if (site < begin || site + sizeof signature > end || ENGINE_RVA < p->p_vaddr ||
            ENGINE_RVA + sizeof signature > p->p_vaddr + p->p_filesz) continue;
        if (p->p_offset > UINT64_MAX - (ENGINE_RVA - p->p_vaddr)) fatal(78, "offset-overflow");
        target->site = site; target->page = page;
        target->file_offset = p->p_offset + ENGINE_RVA - p->p_vaddr;
        target->count++;
    }
    return 1;
}

static void *near_thunk(uintptr_t site, size_t page_bytes) {
    uintptr_t anchor = site & ~(uintptr_t)(page_bytes - 1);
    for (unsigned i = 0; i < 256; ++i) {
        uintptr_t distance = (uintptr_t)(i / 2 + 1) * 0x200000;
        if ((i & 1) ? anchor < distance : distance > UINTPTR_MAX - anchor) continue;
        uintptr_t candidate = (i & 1) ? anchor - distance : anchor + distance;
        if (!candidate || page_bytes > UINTPTR_MAX - candidate) continue;
        int64_t relative = candidate >= site + 5 ? (int64_t)(candidate - (site + 5)) :
            -(int64_t)((site + 5) - candidate);
        if (relative < INT32_MIN || relative > INT32_MAX) continue;
        void *area = mmap((void *)candidate, page_bytes, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (area == MAP_FAILED) {
            if (errno == EEXIST) continue;
            fatal(78, "thunk-map");
        }
        if (area != (void *)candidate) {
            if (munmap(area, page_bytes)) fatal(78, "thunk-unmap");
            fatal(78, "fixed-noreplace-unsupported");
        }
        unsigned char thunk[14] = {0xff, 0x25, 0, 0, 0, 0};
        uintptr_t address = (uintptr_t)halogen_preflight_trampoline;
        memcpy(thunk + 6, &address, sizeof address);
        memcpy(area, thunk, sizeof thunk);
        __builtin___clear_cache(area, (char *)area + sizeof thunk);
        if (mprotect(area, page_bytes, PROT_READ | PROT_EXEC) ||
            !mapped_span(candidate, page_bytes, "r-xp", NULL, 0)) fatal(78, "thunk-rx");
        return area;
    }
    fatal(78, "thunk-candidates-exhausted");
}

__attribute__((constructor)) static void install(void) {
    char executable[4096];
    ssize_t length = readlink("/proc/self/exe", executable, sizeof executable - 1);
    if (length < 0 || (size_t)length >= sizeof executable - 1) fatal(78, "executable-name");
    executable[length] = 0;
    const char *base = strrchr(executable, '/'); base = base ? base + 1 : executable;
    if (strcmp(base, "flash_serve")) return;
    configuration();
    struct stat identity = verify_file();
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0 || ((unsigned long)page_size & ((unsigned long)page_size - 1)))
        fatal(78, "page-size");
    struct target target = {.page_bytes = (size_t)page_size};
    if (dl_iterate_phdr(main_headers, &target) != 1 || target.count != 1 ||
        !mapped_span(target.site, sizeof signature, "r-xp", &identity, target.file_offset) ||
        !mapped_span(target.page, target.page_bytes, "r-xp", NULL, 0)) fatal(78, "target-rx");
    if (memcmp((void *)target.site, signature, sizeof signature)) fatal(78, "code-signature");
    void *thunk = near_thunk(target.site, target.page_bytes);
    int64_t delta = (uintptr_t)thunk >= target.site + 5 ?
        (int64_t)((uintptr_t)thunk - (target.site + 5)) :
        -(int64_t)((target.site + 5) - (uintptr_t)thunk);
    if (delta < INT32_MIN || delta > INT32_MAX) fatal(78, "call-reach");
    unsigned char call[5] = {0xe8}; int32_t displacement = (int32_t)delta;
    memcpy(call + 1, &displacement, 4);
    /* No RWX interval: this constructor runs before the audited engine site. */
    if (mprotect((void *)target.page, target.page_bytes, PROT_READ | PROT_WRITE))
        fatal(78, "text-rw");
    memcpy((void *)target.site, call, sizeof call);
    __builtin___clear_cache((char *)target.site, (char *)target.site + sizeof call);
    if (mprotect((void *)target.page, target.page_bytes, PROT_READ | PROT_EXEC) ||
        !mapped_span(target.page, target.page_bytes, "r-xp", NULL, 0)) fatal(78, "text-rx");
    activated = 1;
    if (dprintf(STDERR_FILENO, "[preflight-bridge] active sha256=%s rva=0x%" PRIxPTR " trace=%d\n",
                ENGINE_SHA, ENGINE_RVA, trace_only) < 0) fatal(78, "activation-log");
}

/* Called with untouched original engine frame; never supplies an arithmetic
 * sentinel on error: all errors terminate before demand+floor can wrap. */
__attribute__((visibility("hidden")))
size_t halogen_preflight_bridge_demand(const unsigned char *frame, uintptr_t range_end,
                                      uint64_t floor_bytes) {
    if (!activated || ((uintptr_t)frame & 15) || floor_bytes != FLOOR_BYTES ||
        !mapped_span((uintptr_t)frame, 0x60, NULL, NULL, 0)) fatal(79, "frame-floor");
    uintptr_t begin, object, mapping; size_t aggregate, mapping_bytes;
    memcpy(&begin, frame + 8, sizeof begin);
    memcpy(&object, frame + 16, sizeof object);
    memcpy(&aggregate, frame + 88, sizeof aggregate);
    if (!begin || (begin & 7) || (range_end & 7) || range_end <= begin ||
        (range_end - begin) % sizeof(struct halogen_preflight_range_v1) ||
        (range_end - begin) / sizeof(struct halogen_preflight_range_v1) > MAX_RANGES ||
        !mapped_span(begin, range_end - begin, NULL, NULL, 0) ||
        !mapped_span(object, 16, NULL, NULL, 0)) fatal(79, "vector-object");
    memcpy(&mapping, (void *)object, sizeof mapping);
    memcpy(&mapping_bytes, (void *)(object + 8), sizeof mapping_bytes);
    if (!mapping || !mapping_bytes || mapping_bytes > UINTPTR_MAX - mapping) fatal(79, "mapping");
    const struct halogen_preflight_range_v1 *ranges = (const void *)begin;
    size_t count = (range_end - begin) / sizeof *ranges, host = 0;
    if (halogen_hybrid_preflight_v1(mapping, mapping_bytes, ranges, count, aggregate, &host))
        fatal(79, "planner");
    if (host > aggregate || host > SIZE_MAX - floor_bytes) fatal(79, "demand-overflow");
    if (dprintf(STDERR_FILENO,
                "[preflight-bridge] demand aggregate=%zu host=%zu mapping=%zu count=%zu floor=%" PRIu64 "\n",
                aggregate, host, mapping_bytes, count, floor_bytes) < 0) fatal(79, "demand-log");
    if (trace_only) {
        for (size_t i = 0; i < count; ++i)
            if (dprintf(STDERR_FILENO, "[preflight-bridge] range[%zu]=%" PRIu64 ":%" PRIu64 "\n",
                        i, ranges[i].begin, ranges[i].end) < 0) fatal(79, "trace-log");
        _exit(77);
    }
    return host;
}
