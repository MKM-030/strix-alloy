#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <link.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

/* Default-off Linux x86-64 registration-only experiment. No launch, function
 * registration, unregister, module, device or stream APIs are interposed or
 * called here. All initialization occurs at the first registration invocation;
 * no preload constructor ordering is assumed. */
typedef void **(*register_fn)(const void *);
struct hip_wrapper {
    uint32_t magic, version;
    const void *binary, *dummy;
};
_Static_assert(sizeof(void *) == 8 && sizeof(struct hip_wrapper) == 24,
               "pinned installed HIP wrapper ABI");
_Static_assert(offsetof(struct hip_wrapper, binary) == 8 &&
               offsetof(struct hip_wrapper, dummy) == 16, "HIP wrapper fields");
_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "pinned little endian image");

static const char engine_path[] = "/usr/local/bin/flash_serve";
static const char runtime_path[] =
    "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7";
static const char engine_sha[] =
    "ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913";
static const char runtime_sha[] =
    "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5";
static const char bundle_sha[] =
    "c1eb5027c1ce7441ba2eba93e4f6c1805b2131423eaa20da0f21045b989aae67";
static const char candidate_sha[] =
    "39053af36ed652892f7082af4eca5cd153b593260448b3c91a67f277cd0f1259";
static const char candidate_bundle_sha[] =
    "f668c44ee907d72d07e4cc89eb3234dc384a9ec5c39b8e702b49e616690892ff";
enum {
    ENGINE_BYTES = 26178504, RUNTIME_BYTES = 28933697,
    BUNDLE_BYTES = 17769520, PAYLOAD_OFFSET = 4096, PAYLOAD_BYTES = 17765424,
    BUNDLE_RVA = 0x51000, WRAPPER_RVA = 0x18f9248
};
/* Exactly the changed bytes from the frozen patch-receipt.json. Offsets are
 * relative to the gfx1151 payload, not the complete clang offload bundle. */
static const struct { size_t offset; unsigned char old_byte, new_byte; } patches[] = {
    { 448442, 0x7d, 0x78 },
    { 2093040, 0x0f, 0x0e },
    { 3893566, 0xf2, 0xda },
    { 3893598, 0xe5, 0xb5 },
    { 3894210, 0xf0, 0xee },
    { 3894234, 0xf4, 0xda },
    { 3894300, 0x78, 0x77 },
    { 3894308, 0x7a, 0x6d },
    { 3894414, 0xf2, 0xee },
    { 3894512, 0x79, 0x77 },
    { 3894542, 0xf6, 0xee },
    { 3894562, 0xf8, 0xda },
    { 3894596, 0x7b, 0x77 },
    { 3894604, 0x7c, 0x6d }
};
_Static_assert(sizeof(patches) / sizeof(patches[0]) == 14, "frozen fourteen-byte change");
_Static_assert(PAYLOAD_OFFSET + PAYLOAD_BYTES == BUNDLE_BYTES, "complete bundle extent");

/* Self-contained SHA256 keeps preparation CPU-only and avoids loading another
 * DSO or relying on its constructors during the engine's registration ctor. */
struct sha256_state {
    uint32_t h[8]; uint64_t bytes; size_t used; unsigned char block[64];
};
static uint32_t rotate(uint32_t value, unsigned bits) {
    return (value >> bits) | (value << (32 - bits));
}
static void sha256_block(struct sha256_state *s, const unsigned char *input) {
    static const uint32_t k[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    };
    uint32_t w[64];
    for (unsigned i = 0; i < 16; i++)
        w[i] = ((uint32_t)input[4*i] << 24) | ((uint32_t)input[4*i+1] << 16) |
               ((uint32_t)input[4*i+2] << 8) | (uint32_t)input[4*i+3];
    for (unsigned i = 16; i < 64; i++) {
        uint32_t a = w[i-15], b = w[i-2];
        w[i] = w[i-16] + (rotate(a,7) ^ rotate(a,18) ^ (a>>3)) + w[i-7] +
               (rotate(b,17) ^ rotate(b,19) ^ (b>>10));
    }
    uint32_t a=s->h[0],b=s->h[1],c=s->h[2],d=s->h[3];
    uint32_t e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
    for (unsigned i = 0; i < 64; i++) {
        uint32_t t1 = h + (rotate(e,6) ^ rotate(e,11) ^ rotate(e,25)) +
                      ((e & f) ^ (~e & g)) + k[i] + w[i];
        uint32_t t2 = (rotate(a,2) ^ rotate(a,13) ^ rotate(a,22)) +
                      ((a & b) ^ (a & c) ^ (b & c));
        h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;
    s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha256_start(struct sha256_state *s) {
    static const uint32_t initial[8] = {
        0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
        0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19
    };
    memcpy(s->h, initial, sizeof(initial)); s->bytes=0; s->used=0;
}
static void sha256_update(struct sha256_state *s, const void *data, size_t bytes) {
    const unsigned char *input = data; s->bytes += bytes;
    while (bytes) {
        size_t count = 64 - s->used; if (count > bytes) count = bytes;
        memcpy(s->block + s->used, input, count);
        s->used += count; input += count; bytes -= count;
        if (s->used == 64) { sha256_block(s, s->block); s->used=0; }
    }
}
static void sha256_finish(struct sha256_state *s, char hex[65]) {
    static const char digits[] = "0123456789abcdef";
    uint64_t bits = s->bytes * 8;
    s->block[s->used++] = 0x80;
    if (s->used > 56) {
        memset(s->block + s->used, 0, 64 - s->used);
        sha256_block(s, s->block); s->used=0;
    }
    memset(s->block + s->used, 0, 56 - s->used);
    for (unsigned i = 0; i < 8; i++) s->block[63-i] = (unsigned char)(bits >> (8*i));
    sha256_block(s, s->block);
    for (unsigned i = 0; i < 32; i++) {
        unsigned byte = (s->h[i/4] >> (24 - 8*(i%4))) & 255;
        hex[2*i]=digits[byte>>4]; hex[2*i+1]=digits[byte&15];
    }
    hex[64]=0;
}
static int memory_matches(const void *data, size_t bytes, const char *expected) {
    struct sha256_state s; char hex[65];
    sha256_start(&s); sha256_update(&s, data, bytes); sha256_finish(&s, hex);
    return !strcmp(hex, expected);
}
static int unchanged_file(const struct stat *a, const struct stat *b) {
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino && a->st_size == b->st_size &&
        a->st_mtim.tv_sec == b->st_mtim.tv_sec && a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec == b->st_ctim.tv_sec && a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}
static int file_matches(const char *path, size_t bytes, const char *expected,
                        struct stat *identity) {
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 0;
    struct stat before, after; int matched=0;
    if (fstat(fd, &before) || !S_ISREG(before.st_mode) || before.st_size != (off_t)bytes)
        goto done;
    struct sha256_state s; char hex[65]; unsigned char buffer[65536]; size_t left=bytes;
    sha256_start(&s);
    while (left) {
        size_t count = left < sizeof(buffer) ? left : sizeof(buffer);
        ssize_t got = read(fd, buffer, count);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) goto done;
        sha256_update(&s, buffer, (size_t)got); left -= (size_t)got;
    }
    if (fstat(fd, &after) || !unchanged_file(&before, &after)) goto done;
    sha256_finish(&s, hex); matched = !strcmp(hex, expected);
    if (matched && identity) *identity=before;
done:
    close(fd); return matched;
}

struct main_image { uintptr_t base; int found, wrapper_readable, bundle_readable; };
static int readable_range(const struct dl_phdr_info *info, uintptr_t rva, size_t bytes) {
    for (unsigned i = 0; i < info->dlpi_phnum; i++) {
        const ElfW(Phdr) *p = info->dlpi_phdr + i;
        if (p->p_type == PT_LOAD && (p->p_flags & PF_R) && rva >= p->p_vaddr &&
            rva - p->p_vaddr <= p->p_memsz && bytes <= p->p_memsz - (rva - p->p_vaddr))
            return 1;
    }
    return 0;
}
static int find_main(struct dl_phdr_info *info, size_t bytes, void *context) {
    (void)bytes;
    if (info->dlpi_name && *info->dlpi_name) return 0;
    struct main_image *image = context;
    image->base = (uintptr_t)info->dlpi_addr; image->found=1;
    image->wrapper_readable = readable_range(info, WRAPPER_RVA, sizeof(struct hip_wrapper));
    image->bundle_readable = readable_range(info, BUNDLE_RVA, BUNDLE_BYTES);
    return 1;
}
/* Match the opened pinned library to the file actually mapped at the resolved
 * native registration address. A replaced pathname or deleted old mapping is
 * rejected even if a different file at that path has the expected hash. */
static int mapped_runtime_matches(uintptr_t address, const struct stat *identity) {
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps) return 0;
    char line[8192]; int matched=0;
    while (fgets(line, sizeof(line), maps)) {
        unsigned long long first,last,offset,inode; unsigned major_number,minor_number;
        char permissions[5]; int consumed=0;
        if (sscanf(line, "%llx-%llx %4s %llx %x:%x %llu %n", &first, &last, permissions,
                   &offset, &major_number, &minor_number, &inode, &consumed) != 7 ||
            consumed <= 0 || address < first || address >= last) continue;
        char *path = line + consumed;
        path[strcspn(path, "\r\n")] = 0;
        matched = inode == (unsigned long long)identity->st_ino &&
            makedev(major_number, minor_number) == identity->st_dev &&
            !strcmp(path, runtime_path);
        break;
    }
    fclose(maps); return matched;
}

enum { UNSEEN, PASS_THROUGH, ARMED, READY };
static pthread_mutex_t preparation_lock = PTHREAD_MUTEX_INITIALIZER;
static unsigned preparation_state;
static struct main_image main_image;
static const struct hip_wrapper *retained_wrapper;
static _Atomic uintptr_t native_address;
static _Atomic pid_t owner_pid;
static _Atomic unsigned receipt_emitted;
static _Thread_local unsigned hook_depth;

__attribute__((visibility("default"))) void **__hipRegisterFatBinary(const void *data);
static register_fn native_target(void) {
    uintptr_t address = atomic_load_explicit(&native_address, memory_order_acquire);
    if (!address) {
        void *symbol = dlsym(RTLD_NEXT, "__hipRegisterFatBinary");
        /* A mandatory missing native target cannot be replaced by a synthetic
         * handle, a fabricated success, or a second registration attempt. */
        if (!symbol || symbol == (void *)(uintptr_t)__hipRegisterFatBinary) _exit(127);
        address=(uintptr_t)symbol;
        atomic_store_explicit(&native_address, address, memory_order_release);
    }
    return (register_fn)address;
}
static void initialize_identity(register_fn native) {
    preparation_state=PASS_THROUGH;
    const char *enabled = getenv("HG0172_HC6_REGISTER_REMAP");
    if (!enabled || strcmp(enabled, "1")) return;
    dl_iterate_phdr(find_main, &main_image);
    if (!main_image.found || !main_image.wrapper_readable || !main_image.bundle_readable ||
        main_image.base > UINTPTR_MAX - (WRAPPER_RVA + sizeof(struct hip_wrapper))) return;
    struct stat executable, engine, runtime;
    if (!file_matches(engine_path, ENGINE_BYTES, engine_sha, &engine) ||
        stat("/proc/self/exe", &executable) || engine.st_dev != executable.st_dev ||
        engine.st_ino != executable.st_ino) return;
    Dl_info origin;
    if (!dladdr((const void *)(uintptr_t)native, &origin) || !origin.dli_fname ||
        strcmp(origin.dli_fname, runtime_path) ||
        !file_matches(runtime_path, RUNTIME_BYTES, runtime_sha, &runtime) ||
        !mapped_runtime_matches((uintptr_t)native, &runtime)) return;
    preparation_state=ARMED;
}
static int wrapper_matches(const struct hip_wrapper *wrapper) {
    return wrapper->magic == 0x48495046 && wrapper->version == 1 &&
        wrapper->binary == (const void *)(main_image.base + BUNDLE_RVA) && wrapper->dummy == NULL;
}
static const void *prepare_input(const void *data, register_fn native) {
    const void *input=data;
    if (pthread_mutex_lock(&preparation_lock)) return data;
    if (preparation_state == UNSEEN) initialize_identity(native);
    if (preparation_state != ARMED && preparation_state != READY) goto done;
    if (data != (const void *)(main_image.base + WRAPPER_RVA)) goto done;
    const struct hip_wrapper *original=data;
    if (!wrapper_matches(original)) goto done;
    if (preparation_state == READY) { input=retained_wrapper; goto done; }
    /* No HIP call occurs before all identity, byte and protection checks pass.
     * Failure here still permits exactly one original stock registration. */
    preparation_state=PASS_THROUGH;
    unsigned char *bundle=mmap(NULL, BUNDLE_BYTES, PROT_READ | PROT_WRITE,
                              MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (bundle == MAP_FAILED) goto done;
    struct hip_wrapper *wrapper=mmap(NULL, sizeof(*wrapper), PROT_READ | PROT_WRITE,
                                    MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (wrapper == MAP_FAILED) { munmap(bundle, BUNDLE_BYTES); goto done; }
    memcpy(bundle, original->binary, BUNDLE_BYTES);
    if (!memory_matches(bundle, BUNDLE_BYTES, bundle_sha)) goto bad;
    for (size_t i = 0; i < sizeof(patches) / sizeof(patches[0]); i++) {
        size_t offset = PAYLOAD_OFFSET + patches[i].offset;
        if (patches[i].offset >= PAYLOAD_BYTES || bundle[offset] != patches[i].old_byte) goto bad;
        bundle[offset]=patches[i].new_byte;
    }
    if (!memory_matches(bundle + PAYLOAD_OFFSET, PAYLOAD_BYTES, candidate_sha) ||
        !memory_matches(bundle, BUNDLE_BYTES, candidate_bundle_sha)) goto bad;
    memcpy(wrapper, original, sizeof(*wrapper)); wrapper->binary=bundle;
    if (mprotect(bundle, BUNDLE_BYTES, PROT_READ) ||
        mprotect(wrapper, sizeof(*wrapper), PROT_READ)) goto bad;
    retained_wrapper=wrapper; preparation_state=READY; input=wrapper; goto done;
bad:
    munmap(wrapper, sizeof(*wrapper)); munmap(bundle, BUNDLE_BYTES);
done:
    pthread_mutex_unlock(&preparation_lock); return input;
}

__attribute__((visibility("default"))) void **__hipRegisterFatBinary(const void *data) {
    int entry_errno=errno;
    unsigned nested=hook_depth++;
    register_fn native=native_target();
    pid_t pid=getpid(), expected=0;
    atomic_compare_exchange_strong_explicit(&owner_pid, &expected, pid,
                                            memory_order_relaxed, memory_order_relaxed);
    const void *input=data;
    if (!nested && atomic_load_explicit(&owner_pid, memory_order_relaxed) == pid)
        input=prepare_input(data, native);
    errno=entry_errno;
    void **handle=native(input);  /* the sole native call for this invocation */
    int native_errno=errno;
    if (input != data && !atomic_exchange_explicit(&receipt_emitted, 1, memory_order_relaxed))
        dprintf(STDERR_FILENO,
            "HGHC6_REGISTER_V1 pid=%lld bundle=%s payload=%s changed_bytes=14 handle=%p status=%s\n",
            (long long)pid, candidate_bundle_sha, candidate_sha, (void *)handle,
            handle ? "nonnull" : "null");
    hook_depth--; errno=native_errno; return handle;
}

/* Both anonymous read-only mappings deliberately survive to process exit.
 * No destructor frees them or calls HIP. The engine receives the exact native
 * handle and its existing __hipRegisterFunction / __hipUnregisterFatBinary
 * imports retain normal ownership. A repeated registration uses the same clone
 * image key. Even a null native result never triggers stock fallback/retry. */
