#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <link.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/wait.h>
#include <unistd.h>

/* CPU-only boundary doubles: the real adapter still reads/hashes the pinned
 * files, checks the wrapper/bundle, patches, protects, retains and forwards.
 * Each scenario must be a fresh process; no reset entry point is added to the
 * production adapter. No HIP library is linked, loaded or executed. */
static const char *fixture_engine, *fixture_runtime, *scenario;
static unsigned char *fixture_main;
static size_t fixture_main_bytes = 0x1900000;
static unsigned native_calls;
static const void *native_input;
static void *native_handle_storage;
static int enabled = 1, bad_maps_inode, bad_load_range;

static void **fake_register(const void *input) {
    if (!native_calls) assert(errno == ERANGE);
    native_calls++;
    native_input = input;
    if (!strcmp(scenario, "native-null")) { errno = EIO; return NULL; }
    errno = EBUSY;
    return &native_handle_storage;
}
static char *fake_getenv(const char *name) {
    assert(!strcmp(name, "HG0172_HC6_REGISTER_REMAP"));
    errno = ENOTTY;
    return enabled ? "1" : NULL;
}
static void *fake_dlsym(void *scope, const char *name) {
    assert(scope == RTLD_NEXT);
    assert(!strcmp(name, "__hipRegisterFatBinary"));
    return (void *)(uintptr_t)fake_register;
}
static int fake_dladdr(const void *address, Dl_info *info) {
    assert(address == (const void *)(uintptr_t)fake_register);
    memset(info, 0, sizeof(*info));
    info->dli_fname = "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7";
    info->dli_fbase = (void *)(uintptr_t)fake_register;
    return 1;
}
static int fake_dl_iterate_phdr(int (*callback)(struct dl_phdr_info *, size_t, void *),
                              void *context) {
    ElfW(Phdr) load = {0};
    load.p_type = PT_LOAD; load.p_flags = PF_R;
    load.p_memsz = load.p_filesz = bad_load_range ? 0x1000 : fixture_main_bytes;
    struct dl_phdr_info info = {0};
    info.dlpi_addr = (ElfW(Addr))(uintptr_t)fixture_main;
    info.dlpi_name = ""; info.dlpi_phdr = &load; info.dlpi_phnum = 1;
    return callback(&info, sizeof(info), context);
}
static int fake_open(const char *path, int flags, ...) {
    if (!strcmp(path, "/usr/local/bin/flash_serve")) path = fixture_engine;
    else if (!strcmp(path, "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7"))
        path = fixture_runtime;
    else assert(!"unexpected adapter open");
    return open(path, flags);
}
static int fake_stat(const char *path, struct stat *result) {
    assert(!strcmp(path, "/proc/self/exe"));
    return stat(fixture_engine, result);
}
static FILE *fake_fopen(const char *path, const char *mode) {
    assert(!strcmp(path, "/proc/self/maps") && !strcmp(mode, "r"));
    struct stat st;
    assert(!stat(fixture_runtime, &st));
    FILE *maps = tmpfile(); assert(maps);
    uintptr_t address = (uintptr_t)fake_register;
    assert(fprintf(maps, "%lx-%lx r-xp 00000000 %x:%x %llu %s\n",
        (unsigned long)(address - 1), (unsigned long)(address + 1),
        major(st.st_dev), minor(st.st_dev),
        (unsigned long long)st.st_ino + (unsigned)bad_maps_inode,
        "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7") > 0);
    rewind(maps); return maps;
}

#define getenv fake_getenv
#define dlsym fake_dlsym
#define dladdr fake_dladdr
#define dl_iterate_phdr fake_dl_iterate_phdr
#define open fake_open
#define stat(path, result) fake_stat(path, result)
#define fopen fake_fopen
#include "registration.c"
#undef getenv
#undef dlsym
#undef dladdr
#undef dl_iterate_phdr
#undef open
#undef stat
#undef fopen

static unsigned char *read_fixture(const char *path, size_t bytes) {
    FILE *file = fopen(path, "rb"); assert(file);
    unsigned char *image = malloc(bytes); assert(image);
    assert(fread(image, 1, bytes, file) == bytes);
    assert(fgetc(file) == EOF); assert(!fclose(file)); return image;
}
static void expect_read_only(const void *address) {
    struct rlimit no_core = {0, 0}; assert(!setrlimit(RLIMIT_CORE, &no_core));
    pid_t child = fork(); assert(child >= 0);
    if (!child) { *(volatile unsigned char *)address = 0; _exit(99); }
    int status; assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGSEGV);
}

int main(int argc, char **argv) {
    assert(argc == 5);
    scenario = argv[1]; fixture_engine = argv[2]; fixture_runtime = argv[3];
    unsigned char *engine = read_fixture(fixture_engine, 26178504);
    unsigned char *expected_candidate = read_fixture(argv[4], 17765424);
    fixture_main = mmap(NULL, fixture_main_bytes, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(fixture_main != MAP_FAILED);
    memcpy(fixture_main, engine, 26178504);
    /* ELF data PT_LOAD uses RVA=file+0x3000. Apply only the real wrapper's
     * binary relocation; stock constructor provides this relocated pointer. */
    unsigned char *wrapper = fixture_main + 0x18f9248;
    memcpy(wrapper, engine + 0x18f6248, 24);
    uintptr_t binary = (uintptr_t)(fixture_main + 0x51000);
    memcpy(wrapper + 8, &binary, 8);
    const void *input = wrapper;
    int substituted = !strcmp(scenario, "enabled") || !strcmp(scenario, "native-null");
    if (!strcmp(scenario, "off")) enabled = 0;
    else if (!strcmp(scenario, "unrelated")) input = (const void *)(uintptr_t)1;
    else if (!strcmp(scenario, "wrong-magic")) wrapper[0] ^= 1;
    else if (!strcmp(scenario, "wrong-version")) wrapper[4] ^= 1;
    else if (!strcmp(scenario, "wrong-dummy")) wrapper[16] = 1;
    else if (!strcmp(scenario, "wrong-binary")) wrapper[8] ^= 1;
    else if (!strcmp(scenario, "wrong-bundle")) fixture_main[0x51000 + 4095] ^= 1;
    else if (!strcmp(scenario, "wrong-engine-file")) fixture_engine = "/dev/null";
    else if (!strcmp(scenario, "wrong-runtime-file")) fixture_runtime = "/dev/null";
    else if (!strcmp(scenario, "wrong-runtime-inode")) bad_maps_inode = 1;
    else if (!strcmp(scenario, "wrong-load-range")) bad_load_range = 1;
    else assert(substituted);

    unsigned char original_bundle[4096];
    memcpy(original_bundle, fixture_main + 0x51000, sizeof(original_bundle));
    errno = ERANGE;
    void **result = __hipRegisterFatBinary(input);
    assert(native_calls == 1);  /* catches either no forward or fallback retry */
    assert(result == (!strcmp(scenario, "native-null") ? NULL : &native_handle_storage));
    assert(errno == (!strcmp(scenario, "native-null") ? EIO : EBUSY));
    assert(!memcmp(original_bundle, fixture_main + 0x51000, sizeof(original_bundle)));
    if (!substituted) {
        assert(native_input == input);
    } else {
        assert(native_input != input);
        const unsigned char *clone_wrapper = native_input;
        uintptr_t clone_binary;
        memcpy(&clone_binary, clone_wrapper + 8, 8);
        assert(clone_binary != binary);
        assert(!memcmp(clone_wrapper, wrapper, 8));
        assert(!memcmp(clone_wrapper + 16, wrapper + 16, 8));
        assert(!memcmp((const void *)clone_binary, original_bundle, 4096));
        assert(!memcmp((const unsigned char *)clone_binary + 4096,
                       expected_candidate, 17765424));
        assert(!memcmp(fixture_main + 0x51000 + 4096,
                       engine + 0x51000 + 4096, 17765424));
        expect_read_only(clone_wrapper); expect_read_only((const void *)clone_binary);
        /* The native double deliberately retains these pointers. They stay
         * readable after return, an unrelated call, and repeated registration.
         * Repetition must preserve HIP's image-pointer module key. */
        const void *retained_wrapper = native_input;
        assert(__hipRegisterFatBinary((const void *)(uintptr_t)1) == result);
        assert(native_calls == 2 && native_input == (const void *)(uintptr_t)1);
        assert(!memcmp((const unsigned char *)clone_binary + 4096,
                       expected_candidate, 17765424));
        assert(__hipRegisterFatBinary(wrapper) == result);
        assert(native_calls == 3 && native_input == retained_wrapper);
        assert(!memcmp((const unsigned char *)clone_binary + 4096,
                       expected_candidate, 17765424));
    }
    printf("PASS %s\n", scenario);
    return 0;
}
