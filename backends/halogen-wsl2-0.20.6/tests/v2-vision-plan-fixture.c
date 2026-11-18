/* Exercise the actual V2 planner and registration path without model allocation.
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
static const uintptr_t r2_base = UINT64_C(0x3000000000);
static const uintptr_t tower_base = UINT64_C(0x4000000000);
static const size_t main_mapping = UINT64_C(66687678432);
static const size_t embedded_main_payload = UINT64_C(66687358944);
static const size_t r2_main_payload = UINT64_C(65163800576);
static const size_t r2_mapping = UINT64_C(1523568192);
static const size_t r2_payload = UINT64_C(1523564096);
static const size_t tower_mapping = UINT64_C(897916416);
static const size_t tower_payload = UINT64_C(897863168);

enum identity_target { IDENTITY_NONE, IDENTITY_MAIN, IDENTITY_R2, IDENTITY_TOWER };
static enum identity_target tamper_target;
static size_t free_kb = (size_t)128 << 20;
static int wrong_path, wrong_inode, wrong_device, wrong_size, wrong_offset, writable, shifted;
static int wrong_generation, mutate_during_copy, mutation_applied;
static int fail_malloc, fail_copy, fail_free, malloc_calls, copy_calls, free_calls, register_calls;

static int targeted(enum identity_target target, int flag) {
    return tamper_target == target && flag;
}

static void mapping_line(FILE *file, uintptr_t base, size_t bytes, enum identity_target target,
                         unsigned inode, const char *path, const char *wrong_path_value) {
    fprintf(file, "%lx-%lx %s %08x 08:%02x %u %s\n",
            (unsigned long)(base + (targeted(target, shifted) ? 4096 : 0)),
            (unsigned long)(base + bytes), targeted(target, writable) ? "rw-p" : "r--p",
            targeted(target, wrong_offset) ? 4096 : 0,
            targeted(target, wrong_device) ? 2 : 1,
            targeted(target, wrong_inode) ? inode + 100 : inode,
            targeted(target, wrong_path) ? wrong_path_value : path);
}

static FILE *fixture_fopen(const char *path, const char *mode) {
    FILE *file;
    if (!strcmp(path, "/proc/self/maps")) {
        file = tmpfile(); assert(file);
        mapping_line(file, main_base, main_mapping, IDENTITY_MAIN, 41,
                     "/models/qwen38-flash-next-v2.hgn", "/models/other-v2.hgn");
        mapping_line(file, r2_base, r2_mapping, IDENTITY_R2, 42,
                     "/models/qwen38-flash-next-drafter-r2.hgn", "/models/other-drafter-r2.hgn");
        mapping_line(file, tower_base, tower_mapping, IDENTITY_TOWER, 43,
                     "/models/qwen38-flash-next-vision.hgn", "/models/other-vision.hgn");
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
    enum identity_target target;
    size_t bytes;
    unsigned inode;
    if (!strcmp(path, "/models/qwen38-flash-next-v2.hgn")) {
        target = IDENTITY_MAIN; bytes = main_mapping; inode = 41;
    } else if (!strcmp(path, "/models/qwen38-flash-next-drafter-r2.hgn")) {
        target = IDENTITY_R2; bytes = r2_mapping; inode = 42;
    } else if (!strcmp(path, "/models/qwen38-flash-next-vision.hgn")) {
        target = IDENTITY_TOWER; bytes = tower_mapping; inode = 43;
    } else {
        return -1;
    }
    memset(value, 0, sizeof *value);
    value->st_size = (off_t)(bytes + (targeted(target, wrong_size) ? 1 : 0));
    value->st_dev = makedev(8, 1); value->st_ino = inode; value->st_mode = S_IFREG | 0444;
    value->st_mtim.tv_sec = 10; value->st_mtim.tv_nsec = 1;
    value->st_ctim.tv_sec = 20;
    value->st_ctim.tv_nsec = 2 + (targeted(target, wrong_generation) ? 1 : 0);
    return 0;
}

static int fixture_allocate(void **p, size_t bytes) {
    (void)bytes; ++malloc_calls;
    if (!fail_malloc) *p = (void *)(uintptr_t)(UINT64_C(0x8000000000) * (unsigned)malloc_calls);
    return fail_malloc;
}
static int fixture_copy(void *d, const void *s, size_t bytes, int kind) {
    (void)d; (void)s; (void)bytes; (void)kind; ++copy_calls;
    if (mutate_during_copy && !mutation_applied) {
        wrong_generation = 1; mutation_applied = 1;
    }
    return fail_copy;
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

static struct halogen_preflight_range_v1 embedded_main_range = {319488, 66687678432};
static struct halogen_preflight_range_v1 r2_main_range = {319488, 65164120064};
static struct halogen_preflight_range_v1 r2_range = {4096, 1523568192};
static struct halogen_preflight_range_v1 tower_range = {53248, 897916416};
static size_t required = 123;

static int plan_range(uintptr_t base, size_t mapping, struct halogen_preflight_range_v1 *range,
                      size_t aggregate) {
    int result = halogen_hybrid_preflight_v1(base, mapping, range, 1, aggregate, &required);
    /* Cache advice is a separate tested concern; no real payload is mapped. */
    reclaim_copy = 0;
    return result;
}
static int plan_embedded_main(void) {
    return plan_range(main_base, main_mapping, &embedded_main_range, embedded_main_payload);
}
static int plan_r2_main(void) {
    return plan_range(main_base, main_mapping, &r2_main_range, r2_main_payload);
}
static int plan_r2(size_t mapping, size_t aggregate) {
    return plan_range(r2_base, mapping, &r2_range, aggregate);
}
static int plan_tower(size_t mapping, size_t aggregate) {
    return plan_range(tower_base, mapping, &tower_range, aggregate);
}
static int register_range(uintptr_t base, const struct halogen_preflight_range_v1 *range,
                          size_t payload) {
    return hipHostRegister((void *)(base + range->begin), payload, 10);
}
static int register_embedded_main(void) {
    return register_range(main_base, &embedded_main_range, embedded_main_payload);
}
static int register_r2_main(void) {
    return register_range(main_base, &r2_main_range, r2_main_payload);
}
static int register_r2(void) { return register_range(r2_base, &r2_range, r2_payload); }
static int register_tower(void) { return register_range(tower_base, &tower_range, tower_payload); }

struct publication {
    size_t count, total, host_total, expected_copy, expected_host;
    size_t executed_copy, executed_host, planned_count, planned_next;
    unsigned phase;
    int allocations;
    planned_range first_plan;
    enum v2_mode mode;
    enum v2_kind kind;
};
static struct publication publication(void) {
    return (struct publication){count, total, host_total, expected_copy, expected_host,
        executed_copy, executed_host, planned_count, planned_next, preflight_phase, malloc_calls,
        planned[0], v2_mode, v2_planned_kind};
}
static void assert_publication_unchanged(struct publication before) {
    assert(count == before.count && total == before.total && host_total == before.host_total);
    assert(expected_copy == before.expected_copy && expected_host == before.expected_host);
    assert(executed_copy == before.executed_copy && executed_host == before.executed_host);
    assert(planned_count == before.planned_count && planned_next == before.planned_next);
    assert(preflight_phase == before.phase && malloc_calls == before.allocations);
    assert(planned[0].pointer == before.first_plan.pointer &&
           planned[0].bytes == before.first_plan.bytes && planned[0].copy == before.first_plan.copy);
    assert(v2_mode == before.mode && v2_planned_kind == before.kind);
}
static void assert_unpublished_pointer(uintptr_t pointer) {
    void *output = (void *)(uintptr_t)123;
    assert(hipHostGetDevicePointer(&output, (void *)pointer, 0) != 0);
    assert(output == (void *)(uintptr_t)123);
}
static void assert_plan_rejected_without_publication(
    int result, struct publication before, uintptr_t unpublished_pointer) {
    assert(result != 0 && required == 123 && preflight_poisoned);
    assert_publication_unchanged(before);
    assert(register_r2() != 0);
    assert_publication_unchanged(before);
    assert_unpublished_pointer(unpublished_pointer);
}
static void assert_registration_rejected_without_publication(
    int result, size_t old_count, size_t old_total, int old_allocations,
    uintptr_t unpublished_pointer) {
    assert(result != 0 && preflight_poisoned);
    assert(count == old_count && total == old_total && host_total == 0);
    assert(malloc_calls == old_allocations);
    assert_unpublished_pointer(unpublished_pointer);
}
static void assert_copy_generation_rejected_without_publication(
    int result, size_t old_count, size_t old_total, int old_allocations,
    int old_frees, uintptr_t unpublished_pointer) {
    assert(result != 0 && preflight_poisoned);
    assert(count == old_count && total == old_total && host_total == 0);
    assert(malloc_calls == old_allocations + 1 && free_calls == old_frees + 1);
    assert(!cleanup_pending.device);
    assert_unpublished_pointer(unpublished_pointer);
}

static int is_case(const char *test, const char *name) { return !strcmp(test, name); }

static void exercise_embedded(const char *test) {
    assert(plan_embedded_main() == 0 && required == 0 && expected_copy == embedded_main_payload);
    if (is_case(test, "embedded_main_registration_order")) {
        assert_registration_rejected_without_publication(
            register_r2(), 0, 0, 0, r2_base + r2_range.begin); return;
    }
    assert(register_embedded_main() == 0 && total == embedded_main_payload && count == 1);
    required = 123;
    if (is_case(test, "embedded_text_success")) return;
    if (is_case(test, "embedded_repeat_main") || is_case(test, "embedded_r2_reordered")) {
        struct publication before = publication();
        int result = is_case(test, "embedded_repeat_main") ? plan_embedded_main() :
                     plan_r2(r2_mapping, r2_payload);
        assert_plan_rejected_without_publication(
            result, before, r2_base + r2_range.begin); return;
    }

    size_t mapping = tower_mapping, aggregate = tower_payload;
    int invalid = 1;
    tamper_target = IDENTITY_TOWER;
    if (is_case(test, "embedded_vision_wrong_map_size")) ++mapping;
    else if (is_case(test, "embedded_vision_wrong_aggregate")) --aggregate;
    else if (is_case(test, "embedded_vision_wrong_range_start")) --tower_range.begin;
    else if (is_case(test, "embedded_vision_wrong_range_end")) --tower_range.end;
    else if (is_case(test, "embedded_vision_wrong_path")) wrong_path = 1;
    else if (is_case(test, "embedded_vision_wrong_inode")) wrong_inode = 1;
    else if (is_case(test, "embedded_vision_wrong_device")) wrong_device = 1;
    else if (is_case(test, "embedded_vision_wrong_file_size")) wrong_size = 1;
    else if (is_case(test, "embedded_vision_wrong_file_offset")) wrong_offset = 1;
    else if (is_case(test, "embedded_vision_writable_map")) writable = 1;
    else if (is_case(test, "embedded_vision_shifted_map")) shifted = 1;
    else if (is_case(test, "embedded_vision_copy_cap")) cap = embedded_main_payload + tower_payload - 1;
    else invalid = 0;
    if (invalid) {
        struct publication before = publication();
        assert_plan_rejected_without_publication(
            plan_tower(mapping, aggregate), before, tower_base + tower_range.begin); return;
    }
    if (is_case(test, "embedded_vision_receipt_mismatch")) {
        struct publication before = publication();
        assert_plan_rejected_without_publication(
            plan_tower(mapping, aggregate), before, tower_base + tower_range.begin); return;
    }
    assert(plan_tower(tower_mapping, tower_payload) == 0 && required == 0);
    assert(expected_copy == embedded_main_payload + tower_payload && total == embedded_main_payload);
    if (is_case(test, "embedded_vision_registration_order")) {
        assert_registration_rejected_without_publication(
            register_r2(), 1, embedded_main_payload, 1, r2_base + r2_range.begin); return;
    }
    if (is_case(test, "embedded_vision_identity_inode_drift") ||
        is_case(test, "embedded_vision_identity_path_drift")) {
        if (is_case(test, "embedded_vision_identity_inode_drift")) wrong_inode = 1; else wrong_path = 1;
        assert_registration_rejected_without_publication(
            register_tower(), 1, embedded_main_payload, 1, tower_base + tower_range.begin); return;
    }
    if (is_case(test, "embedded_vision_identity_generation_drift")) {
        wrong_generation = 1;
        assert_registration_rejected_without_publication(
            register_tower(), 1, embedded_main_payload, 1,
            tower_base + tower_range.begin); return;
    }
    if (is_case(test, "embedded_vision_identity_copy_generation_drift")) {
        mutate_during_copy = 1;
        assert_copy_generation_rejected_without_publication(
            register_tower(), 1, embedded_main_payload, 1, 0,
            tower_base + tower_range.begin); return;
    }
    if (is_case(test, "embedded_vision_reserve")) {
        free_kb = (((size_t)12 << 30) + HALOGEN_TRANSFER_CHUNK - 1024) / 1024;
        int before = malloc_calls;
        assert(register_tower() != 0 && preflight_poisoned && count == 1 && total == embedded_main_payload);
        assert(malloc_calls == before && register_calls == 0); return;
    }
    if (is_case(test, "embedded_vision_allocation_fail") ||
        is_case(test, "embedded_vision_copy_fail") ||
        is_case(test, "embedded_vision_copy_free_fail")) {
        if (is_case(test, "embedded_vision_allocation_fail")) fail_malloc = 7; else fail_copy = 7;
        if (is_case(test, "embedded_vision_copy_free_fail")) fail_free = 8;
        assert(register_tower() != 0 && total == embedded_main_payload && count == 1 && planned_next == 0);
        assert(preflight_poisoned && malloc_calls == 2 && register_calls == 0);
        assert(free_calls == (fail_malloc ? 0 : 1));
        assert_unpublished_pointer(tower_base + tower_range.begin);
        if (fail_free) assert(cleanup_pending.bytes == tower_payload);
        return;
    }
    assert(register_tower() == 0 && total == embedded_main_payload + tower_payload && count == 2);
    assert(total == UINT64_C(67585222112) && total <= UINT64_C(68719476736));
    if (is_case(test, "embedded_vision_third_phase")) {
        required = 123; struct publication before = publication();
        assert_plan_rejected_without_publication(
            plan_tower(tower_mapping, tower_payload), before, r2_base + r2_range.begin);
    }
}

static void exercise_r2(const char *test) {
    assert(plan_r2_main() == 0 && required == 0 && expected_copy == r2_main_payload);
    if (is_case(test, "r2_main_registration_order")) {
        assert_registration_rejected_without_publication(
            register_r2(), 0, 0, 0, r2_base + r2_range.begin); return;
    }
    if (is_case(test, "r2_main_identity_generation_drift")) {
        tamper_target = IDENTITY_MAIN; wrong_generation = 1;
        assert_registration_rejected_without_publication(
            register_r2_main(), 0, 0, 0, main_base + r2_main_range.begin); return;
    }
    if (is_case(test, "r2_main_identity_copy_generation_drift")) {
        tamper_target = IDENTITY_MAIN; mutate_during_copy = 1;
        assert_copy_generation_rejected_without_publication(
            register_r2_main(), 0, 0, 0, 0, main_base + r2_main_range.begin); return;
    }
    if (is_case(test, "r2_main_allocation_fail") || is_case(test, "r2_main_copy_fail")) {
        if (is_case(test, "r2_main_allocation_fail")) fail_malloc = 7; else fail_copy = 7;
        assert(register_r2_main() != 0 && preflight_poisoned && count == 0 && total == 0);
        assert(malloc_calls == 1 && free_calls == (fail_malloc ? 0 : 1));
        assert_unpublished_pointer(main_base + r2_main_range.begin); return;
    }
    assert(register_r2_main() == 0 && total == r2_main_payload && count == 1);
    required = 123;
    if (is_case(test, "r2_missing")) {
        struct publication before = publication();
        assert_plan_rejected_without_publication(
            plan_tower(tower_mapping, tower_payload), before, r2_base + r2_range.begin); return;
    }
    if (is_case(test, "r2_repeat_main") || is_case(test, "r2_embedded_main_reordered")) {
        struct publication before = publication();
        int result = is_case(test, "r2_repeat_main") ? plan_r2_main() : plan_embedded_main();
        assert_plan_rejected_without_publication(
            result, before, r2_base + r2_range.begin); return;
    }

    size_t mapping = r2_mapping, aggregate = r2_payload;
    int invalid = 1;
    tamper_target = IDENTITY_R2;
    if (is_case(test, "r2_wrong_map_size")) ++mapping;
    else if (is_case(test, "r2_wrong_aggregate")) --aggregate;
    else if (is_case(test, "r2_wrong_range_start")) --r2_range.begin;
    else if (is_case(test, "r2_wrong_range_end")) --r2_range.end;
    else if (is_case(test, "r2_wrong_path")) wrong_path = 1;
    else if (is_case(test, "r2_wrong_inode")) wrong_inode = 1;
    else if (is_case(test, "r2_wrong_device")) wrong_device = 1;
    else if (is_case(test, "r2_wrong_file_size")) wrong_size = 1;
    else if (is_case(test, "r2_wrong_file_offset")) wrong_offset = 1;
    else if (is_case(test, "r2_writable_map")) writable = 1;
    else if (is_case(test, "r2_shifted_map")) shifted = 1;
    else if (is_case(test, "r2_copy_cap")) cap = r2_main_payload + r2_payload - 1;
    else invalid = 0;
    if (invalid) {
        struct publication before = publication();
        assert_plan_rejected_without_publication(
            plan_r2(mapping, aggregate), before, r2_base + r2_range.begin); return;
    }
    assert(plan_r2(r2_mapping, r2_payload) == 0 && required == 0);
    assert(expected_copy == r2_main_payload + r2_payload && total == r2_main_payload);
    if (is_case(test, "r2_registration_order")) {
        assert_registration_rejected_without_publication(
            register_tower(), 1, r2_main_payload, 1, tower_base + tower_range.begin); return;
    }
    if (is_case(test, "r2_identity_inode_drift") || is_case(test, "r2_identity_path_drift") ||
        is_case(test, "r2_identity_device_drift") || is_case(test, "r2_identity_size_drift")) {
        if (is_case(test, "r2_identity_inode_drift")) wrong_inode = 1;
        else if (is_case(test, "r2_identity_path_drift")) wrong_path = 1;
        else if (is_case(test, "r2_identity_device_drift")) wrong_device = 1;
        else wrong_size = 1;
        assert_registration_rejected_without_publication(
            register_r2(), 1, r2_main_payload, 1, r2_base + r2_range.begin); return;
    }
    if (is_case(test, "r2_identity_generation_drift")) {
        wrong_generation = 1;
        assert_registration_rejected_without_publication(
            register_r2(), 1, r2_main_payload, 1, r2_base + r2_range.begin); return;
    }
    if (is_case(test, "r2_identity_copy_generation_drift")) {
        mutate_during_copy = 1;
        assert_copy_generation_rejected_without_publication(
            register_r2(), 1, r2_main_payload, 1, 0,
            r2_base + r2_range.begin); return;
    }
    if (is_case(test, "r2_reserve")) {
        free_kb = (((size_t)12 << 30) + HALOGEN_TRANSFER_CHUNK - 1024) / 1024;
        int before = malloc_calls;
        assert(register_r2() != 0 && preflight_poisoned && count == 1 && total == r2_main_payload);
        assert(malloc_calls == before && register_calls == 0);
        assert_unpublished_pointer(r2_base + r2_range.begin); return;
    }
    if (is_case(test, "r2_allocation_fail") || is_case(test, "r2_copy_fail") ||
        is_case(test, "r2_copy_free_fail")) {
        if (is_case(test, "r2_allocation_fail")) fail_malloc = 7; else fail_copy = 7;
        if (is_case(test, "r2_copy_free_fail")) fail_free = 8;
        assert(register_r2() != 0 && total == r2_main_payload && count == 1 && planned_next == 0);
        assert(preflight_poisoned && malloc_calls == 2 && register_calls == 0);
        assert(free_calls == (fail_malloc ? 0 : 1));
        assert_unpublished_pointer(r2_base + r2_range.begin);
        if (fail_free) assert(cleanup_pending.bytes == r2_payload);
        return;
    }
    assert(register_r2() == 0 && total == r2_main_payload + r2_payload && count == 2);
    assert(total == UINT64_C(66687364672) && total <= UINT64_C(68719476736));
    if (is_case(test, "r2_text_success")) return;
    if (is_case(test, "r2_repeat_r2")) {
        required = 123; struct publication before = publication();
        assert_plan_rejected_without_publication(
            plan_r2(r2_mapping, r2_payload), before, tower_base + tower_range.begin); return;
    }
    required = 123;
    assert(plan_tower(tower_mapping, tower_payload) == 0 && required == 0);
    assert(expected_copy == r2_main_payload + r2_payload + tower_payload);
    if (is_case(test, "r2_vision_registration_order")) {
        assert_registration_rejected_without_publication(register_r2(), 2,
            r2_main_payload + r2_payload, 2, tower_base + tower_range.begin); return;
    }
    if (is_case(test, "r2_vision_allocation_fail") || is_case(test, "r2_vision_copy_fail") ||
        is_case(test, "r2_vision_copy_free_fail")) {
        if (is_case(test, "r2_vision_allocation_fail")) fail_malloc = 7; else fail_copy = 7;
        if (is_case(test, "r2_vision_copy_free_fail")) fail_free = 8;
        assert(register_tower() != 0 && total == r2_main_payload + r2_payload &&
               count == 2 && planned_next == 0);
        assert(preflight_poisoned && malloc_calls == 3 && register_calls == 0);
        assert(free_calls == (fail_malloc ? 0 : 1));
        assert_unpublished_pointer(tower_base + tower_range.begin);
        if (fail_free) assert(cleanup_pending.bytes == tower_payload);
        return;
    }
    assert(register_tower() == 0 && total == r2_main_payload + r2_payload + tower_payload && count == 3);
    assert(total == UINT64_C(67585227840) && total <= UINT64_C(68719476736));
    if (is_case(test, "r2_vision_third_phase")) {
        required = 123; struct publication before = publication();
        assert_plan_rejected_without_publication(
            plan_tower(tower_mapping, tower_payload), before, UINT64_C(0x5000000000));
    }
}

int main(int argc, char **argv) {
    assert(argc == 2); const char *test = argv[1];
    if (is_case(test, "null_ranges")) {
        struct publication before = publication();
        int result = halogen_hybrid_preflight_v1(
            main_base, main_mapping, NULL, 1, embedded_main_payload, &required);
        assert_plan_rejected_without_publication(
            result, before, r2_base + r2_range.begin); return 0;
    }
    if (is_case(test, "vision_first") || is_case(test, "r2_first")) {
        struct publication before = publication();
        int result = is_case(test, "vision_first") ? plan_tower(tower_mapping, tower_payload) :
                     plan_r2(r2_mapping, r2_payload);
        assert_plan_rejected_without_publication(
            result, before, r2_base + r2_range.begin); return 0;
    }
    if (is_case(test, "invalid_env")) {
        assert(plan_embedded_main() != 0 && required == 123 && malloc_calls == 0); return 0;
    }
    if (!strncmp(test, "embedded_", 9)) exercise_embedded(test);
    else if (!strncmp(test, "r2_", 3)) exercise_r2(test);
    else assert(!"unknown fixture case");
    return 0;
}
