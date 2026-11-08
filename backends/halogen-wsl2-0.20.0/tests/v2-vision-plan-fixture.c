/* Exercise the actual planner and registration path without model allocation.
 * Only HIP, file identity and /proc boundaries are substituted. */
#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>

static const uintptr_t main_base = UINT64_C(0x100000000);
static const uintptr_t tower_base = UINT64_C(0x4000000000);
static const size_t main_mapping = UINT64_C(66687678432);
static const size_t main_payload = UINT64_C(66687358944);
static const size_t tower_mapping = UINT64_C(897916416);
static const size_t tower_payload = UINT64_C(897863168);
static size_t free_kb = (size_t)128 << 20;
static int wrong_path, wrong_inode, wrong_device, wrong_size, wrong_offset, writable, shifted;
static int fail_malloc, fail_copy, fail_free, malloc_calls, copy_calls, free_calls, register_calls;
static FILE *fixture_fopen(const char *path, const char *mode) {
    FILE *file;
    if (!strcmp(path, "/proc/self/maps")) {
        file = tmpfile(); assert(file);
        fprintf(file, "%lx-%lx r--p 00000000 08:01 41 /models/qwen38-flash-next-v2.hgn\n",
                (unsigned long)main_base, (unsigned long)(main_base + main_mapping + 4095));
        fprintf(file, "%lx-%lx %s %08x 08:%02x %u %s\n",
                (unsigned long)(tower_base + (shifted ? 4096 : 0)),
                (unsigned long)(tower_base + tower_mapping), writable ? "rw-p" : "r--p",
                wrong_offset ? 4096 : 0, wrong_device ? 2 : 1, wrong_inode ? 43 : 42,
                wrong_path ? "/models/other-vision.hgn" : "/models/qwen38-flash-next-vision.hgn");
        rewind(file); return file;
    }
    if (!strcmp(path, "/proc/meminfo")) {
        file = tmpfile(); assert(file);
        fprintf(file, "MemAvailable: %zu kB\n", free_kb);
        rewind(file); return file;
    }
    return fopen(path, mode);
}
static int __attribute__((unused)) fixture_stat(const char *path, struct stat *value) {
    if (strcmp(path, "/models/qwen38-flash-next-vision.hgn")) return -1;
    memset(value, 0, sizeof *value);
    value->st_size = (off_t)(tower_mapping + (wrong_size ? 1 : 0));
    value->st_dev = makedev(8, 1); value->st_ino = 42; value->st_mode = S_IFREG | 0444;
    return 0;
}
static int fixture_allocate(void **p, size_t bytes) {
    (void)bytes; ++malloc_calls;
    if (!fail_malloc) *p = (void *)(uintptr_t)(UINT64_C(0x8000000000) * (unsigned)malloc_calls);
    return fail_malloc;
}
static int fixture_copy(void *d, const void *s, size_t bytes, int kind) {
    (void)d; (void)s; (void)bytes; (void)kind; ++copy_calls; return fail_copy;
}
static int fixture_free(void *p) { (void)p; ++free_calls; return fail_free; }
static int fixture_register(void *p, size_t n, unsigned flags) {
    (void)p; (void)n; (void)flags; ++register_calls; return 0;
}
static int fixture_get(void **p, void *h, unsigned f) { (void)p; (void)h; (void)f; return 999; }
static int fixture_unregister(void *p) { (void)p; return 0; }
static void *fixture_dlsym(void *handle, const char *name) {
    (void)handle;
    if (!strcmp(name, "hipMalloc")) return (void *)fixture_allocate;
    if (!strcmp(name, "hipMemcpy")) return (void *)fixture_copy;
    if (!strcmp(name, "hipFree")) return (void *)fixture_free;
    if (!strcmp(name, "hipHostRegister")) return (void *)fixture_register;
    if (!strcmp(name, "hipHostGetDevicePointer")) return (void *)fixture_get;
    if (!strcmp(name, "hipHostUnregister")) return (void *)fixture_unregister;
    return NULL;
}
#define fopen fixture_fopen
#define stat(path, value) fixture_stat(path, value)
#define dlsym fixture_dlsym
#include "../patches/hip-register-hybrid.c"
#undef fopen
#undef stat
#undef dlsym

static struct halogen_preflight_range_v1 main_range = {319488, 66687678432};
static struct halogen_preflight_range_v1 tower_range = {53248, 897916416};
static size_t required = 123;
static int plan_main(void) {
    int result = halogen_hybrid_preflight_v1(main_base, main_mapping, &main_range, 1, main_payload, &required);
    /* Cache advice is a separate tested concern; no real payload is mapped. */
    reclaim_copy = 0;
    return result;
}
static int plan_tower(size_t map_bytes, size_t aggregate) {
    return halogen_hybrid_preflight_v1(tower_base, map_bytes, &tower_range, 1, aggregate, &required);
}
static int register_main(void) {
    return hipHostRegister((void *)(main_base + main_range.begin), main_payload, 10);
}
static int register_tower(void) {
    return hipHostRegister((void *)(tower_base + tower_range.begin), tower_payload, 10);
}
static void assert_rejected_without_publication(int result, int allocations) {
    assert(result != 0 && required == 123 && malloc_calls == allocations);
    assert(preflight_poisoned);
    assert(register_tower() != 0 && malloc_calls == allocations);
    assert(total == (allocations ? main_payload : 0));
}
int main(int argc, char **argv) {
    assert(argc == 2); const char *test = argv[1];
    if (!strcmp(test, "tower_first")) {
        assert_rejected_without_publication(plan_tower(tower_mapping, tower_payload), 0); return 0;
    }
    if (!strcmp(test, "invalid_env")) {
        assert(plan_main() != 0 && required == 123 && malloc_calls == 0); return 0;
    }
    assert(plan_main() == 0 && required == 0 && expected_copy == main_payload);
    if (!strcmp(test, "incomplete_main")) {
        required = 123; assert_rejected_without_publication(plan_tower(tower_mapping, tower_payload), 0); return 0;
    }
    assert(register_main() == 0 && total == main_payload && count == 1);
    required = 123;
    if (!strcmp(test, "text_only") || !strcmp(test, "repeat_main")) {
        int result = !strcmp(test, "text_only") ? plan_tower(tower_mapping, tower_payload) : plan_main();
        assert_rejected_without_publication(result, 1); return 0;
    }
    size_t map_bytes = tower_mapping, aggregate = tower_payload;
    int invalid = 1;
    if (!strcmp(test, "wrong_map_size")) ++map_bytes;
    else if (!strcmp(test, "wrong_aggregate")) --aggregate;
    else if (!strcmp(test, "wrong_range_start")) --tower_range.begin;
    else if (!strcmp(test, "wrong_range_end")) --tower_range.end;
    else if (!strcmp(test, "wrong_path")) wrong_path = 1;
    else if (!strcmp(test, "wrong_inode")) wrong_inode = 1;
    else if (!strcmp(test, "wrong_device")) wrong_device = 1;
    else if (!strcmp(test, "wrong_file_size")) wrong_size = 1;
    else if (!strcmp(test, "wrong_file_offset")) wrong_offset = 1;
    else if (!strcmp(test, "writable_map")) writable = 1;
    else if (!strcmp(test, "shifted_map")) shifted = 1;
    else if (!strcmp(test, "copy_cap")) cap = main_payload + tower_payload - 1;
    else invalid = 0;
    if (invalid) {
        assert_rejected_without_publication(plan_tower(map_bytes, aggregate), 1); return 0;
    }
    assert(plan_tower(tower_mapping, tower_payload) == 0 && required == 0);
    assert(expected_copy == main_payload + tower_payload && expected_host == 0 && total == main_payload);
    if (!strcmp(test, "identity_inode_drift") || !strcmp(test, "identity_path_drift")) {
        if (!strcmp(test, "identity_inode_drift")) wrong_inode = 1; else wrong_path = 1;
        assert(register_tower() != 0 && malloc_calls == 1 && total == main_payload && preflight_poisoned);
        return 0;
    }
    if (!strcmp(test, "reserve")) {
        free_kb = (((size_t)12 << 30) + HALOGEN_TRANSFER_CHUNK - 1024) / 1024;
        assert(register_tower() != 0 && malloc_calls == 1 && total == main_payload && preflight_poisoned); return 0;
    }
    if (!strcmp(test, "allocation_fail") || !strcmp(test, "copy_fail") || !strcmp(test, "copy_free_fail")) {
        if (!strcmp(test, "allocation_fail")) fail_malloc = 2; else fail_copy = 7;
        if (!strcmp(test, "copy_free_fail")) fail_free = 8;
        assert(register_tower() != 0 && total == main_payload && count == 1 && planned_next == 0);
        assert(preflight_poisoned && malloc_calls == 2 && register_calls == 0);
        assert(free_calls == (fail_malloc ? 0 : 1));
        if (fail_free) {
            void *output = (void *)(uintptr_t)123;
            assert(cleanup_pending.bytes == tower_payload);
            assert(hipHostGetDevicePointer(&output, (void *)(tower_base + tower_range.begin), 0) != 0);
            assert(output == (void *)(uintptr_t)123);
        }
        return 0;
    }
    assert(register_tower() == 0 && total == main_payload + tower_payload && count == 2);
    assert(total == UINT64_C(67585222112) && total <= UINT64_C(68719476736));
    assert(malloc_calls == 2 && register_calls == 0 && host_total == 0);
    assert(copy_calls == (int)((main_payload + HALOGEN_TRANSFER_CHUNK - 1) / HALOGEN_TRANSFER_CHUNK +
                              (tower_payload + HALOGEN_TRANSFER_CHUNK - 1) / HALOGEN_TRANSFER_CHUNK));
    if (!strcmp(test, "third_phase")) {
        required = 123;
        assert(plan_tower(tower_mapping, tower_payload) != 0 && required == 123 && malloc_calls == 2 && preflight_poisoned);
    }
    return 0;
}
