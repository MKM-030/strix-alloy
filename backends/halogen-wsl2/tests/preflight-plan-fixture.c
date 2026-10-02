/* No payload mapping/allocation: only the HIP and /proc system boundaries are
 * substituted. Planning, eligibility parser, branch selection and state are real. */
#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int eligible_maps = 1, fail_malloc, fail_copy, fail_register, fail_free;
static int malloc_calls, copy_calls, register_calls, free_calls, missing_symbol;
static int get_calls;
static void *last_freed;
static size_t free_kb = (size_t)128 << 20;
static FILE *fixture_fopen(const char *path, const char *mode) {
    if (!strcmp(path, "/proc/self/maps")) {
        const char *maps = eligible_maps ?
            "100000000-8000000000 r--p 00000000 00:00 1 /preflight-fixture.hgn\n" :
            "100000000-8000000000 rw-p 00000000 00:00 1 /preflight-fixture.hgn\n";
        FILE *file = tmpfile();
        assert(file);
        fputs(maps, file);
        rewind(file);
        return file;
    }
    if (!strcmp(path, "/proc/meminfo")) {
        FILE *file = tmpfile();
        assert(file);
        fprintf(file, "MemAvailable: %zu kB\n", free_kb);
        rewind(file);
        return file;
    }
    return fopen(path, mode);
}
static int fixture_register(void *p, size_t n, unsigned f) {
    (void)p; (void)n; (void)f; ++register_calls; return fail_register;
}
static int fixture_allocate(void **p, size_t n) {
    (void)n; ++malloc_calls;
    if (!fail_malloc) *p = (void *)(uintptr_t)(0x1000 * malloc_calls);
    return fail_malloc;
}
static int fixture_copy(void *d, const void *s, size_t n, int kind) {
    (void)d; (void)s; (void)n; (void)kind; ++copy_calls; return fail_copy;
}
static int fixture_free(void *p) { last_freed = p; ++free_calls; return fail_free; }
static int fixture_get(void **device, void *host, unsigned flags) {
    (void)host; (void)flags; ++get_calls;
    *device = (void *)(uintptr_t)0xbad;
    return 0;
}
static int fixture_unregister(void *p) { (void)p; return 0; }
static void *fixture_dlsym(void *handle, const char *symbol) {
    (void)handle;
    if (missing_symbol) return NULL;
    if (!strcmp(symbol, "hipHostRegister")) return (void *)fixture_register;
    if (!strcmp(symbol, "hipMalloc")) return (void *)fixture_allocate;
    if (!strcmp(symbol, "hipMemcpy")) return (void *)fixture_copy;
    if (!strcmp(symbol, "hipFree")) return (void *)fixture_free;
    if (!strcmp(symbol, "hipHostUnregister")) return (void *)fixture_unregister;
    if (!strcmp(symbol, "hipHostGetDevicePointer")) return (void *)fixture_get;
    return NULL;
}
#define fopen fixture_fopen
#define dlsym fixture_dlsym
#include "../patches/hip-register-hybrid.c"
#undef fopen
#undef dlsym

/* Weak declaration lets RED fail by assertion when the new API is absent. */
#if !defined(HALOGEN_PREFLIGHT_PLAN_H)
struct halogen_preflight_range_v1 { uint64_t begin, end; };
#endif
extern int halogen_hybrid_preflight_v1(uintptr_t, size_t,
    const struct halogen_preflight_range_v1 *, size_t, size_t, size_t *)
    __attribute__((weak));

static struct halogen_preflight_range_v1 ranges[253];
static const uintptr_t base = UINT64_C(0x100000000);
static size_t required = 123;
static int plan_first(void) {
    return halogen_hybrid_preflight_v1(base, UINT64_C(124068083904), ranges, 252,
                                      UINT64_C(70434994368), &required);
}
static int plan_overlay(void) {
    return halogen_hybrid_preflight_v1(UINT64_C(0x4000000000), UINT64_C(2572466560),
                                      ranges + 252, 1, UINT64_C(2572351872), &required);
}
static int register_at(size_t i) {
    uintptr_t address = i == 252 ? UINT64_C(0x4000000000) : base;
    return hipHostRegister((void *)(address + ranges[i].begin),
                           ranges[i].end - ranges[i].begin, 10);
}
int main(int argc, char **argv) {
    assert(argc == 2);
    const char *test = argv[1];
    uint64_t offset = 0, n;
    for (size_t i = 0; i < 253; ++i) {
        assert(scanf("%lu", &n) == 1);
        if (i == 252) offset = 0;
        ranges[i] = (struct halogen_preflight_range_v1){offset, offset + n};
        offset += n;
    }
#if !defined(HALOGEN_PREFLIGHT_PLAN_H)
    assert(halogen_hybrid_preflight_v1 && "production preflight API is missing");
#endif
    if (!strcmp(test, "unplanned")) {
        assert(register_at(0) != 0 && malloc_calls == 0 && register_calls == 0);
        assert(plan_first() != 0);
        return 0;
    }
    if (!strcmp(test, "bad_config")) {
        assert(plan_first() != 0 && required == 123);
        assert(register_at(0) != 0 && malloc_calls == 0 && register_calls == 0);
        return 0;
    }
    if (!strcmp(test, "cap_boundary")) {
        pthread_once(&once, configure);
#if defined(HALOGEN_PREFLIGHT_PLAN_H)
        assert(preflight_copy_fits(4096, cap - 4096, 1));
        assert(!preflight_copy_fits(4097, cap - 4096, 1));
        assert(!preflight_copy_fits(1, cap, 1));
        assert(!preflight_copy_fits(1, cap + 1, 1));
        assert(!preflight_copy_fits(1, 0, 4096));
#endif
        return 0;
    }
    int bad = 1, result = -1;
    if (!strcmp(test, "null_ranges"))
        result = halogen_hybrid_preflight_v1(base, 124068083904, NULL, 252, 70434994368, &required);
    else if (!strcmp(test, "range_pointer_overflow"))
        result = halogen_hybrid_preflight_v1(base, 124068083904,
            (const struct halogen_preflight_range_v1 *)(UINTPTR_MAX - 8),
            252, 70434994368, &required);
    else if (!strcmp(test, "null_output"))
        result = halogen_hybrid_preflight_v1(base, 124068083904, ranges, 252, 70434994368, NULL);
    else if (!strcmp(test, "zero_base") || !strcmp(test, "base_overflow"))
        result = halogen_hybrid_preflight_v1(!strcmp(test, "zero_base") ? 0 : UINTPTR_MAX - 8,
            124068083904, ranges, 252, 70434994368, &required);
    else if (!strcmp(test, "count") || !strcmp(test, "count_huge"))
        result = halogen_hybrid_preflight_v1(base, 124068083904, ranges,
            !strcmp(test, "count") ? 251 : SIZE_MAX, 70434994368, &required);
    else if (!strcmp(test, "length"))
        result = halogen_hybrid_preflight_v1(base, 124068083905, ranges, 252, 70434994368, &required);
    else if (!strcmp(test, "sum")) ranges[2].end--;
    else if (!strcmp(test, "empty")) ranges[2].end = ranges[2].begin;
    else if (!strcmp(test, "ordering")) ranges[2] = ranges[0];
    else if (!strcmp(test, "overlap")) ranges[2].begin--;
    else if (!strcmp(test, "outside")) ranges[251].end = 124068083905;
    else if (!strcmp(test, "range_overflow")) ranges[251].end = UINT64_MAX;
    else if (!strcmp(test, "ineligible")) eligible_maps = 0;
    else if (!strcmp(test, "prior_copy")) total = 1;
    else if (!strcmp(test, "wrong_choices")) {
        /* Same count/sum, different sizes: arithmetic valid but profile differs. */
        n = ranges[251].end;
        for (size_t i = 0; i < 251; ++i)
            ranges[i] = (struct halogen_preflight_range_v1){i, i + 1};
        ranges[251] = (struct halogen_preflight_range_v1){251, n};
    } else if (!strcmp(test, "host_ceiling")) {
        /* First-fit leaves a >24GiB host range, despite the correct aggregate. */
        n = ranges[251].end;
        ranges[0] = (struct halogen_preflight_range_v1){0, UINT64_C(60000000000)};
        for (size_t i = 1; i < 252; ++i) {
            uint64_t begin = UINT64_C(60000000000) + i - 1;
            ranges[i] = (struct halogen_preflight_range_v1){begin, i == 251 ? n : begin + 1};
        }
    } else bad = 0;
    if (bad) {
        if (result == -1) result = plan_first();
        assert(result != 0 && required == 123);
        assert(register_at(0) != 0 && malloc_calls == 0 && register_calls == 0);
        assert(plan_first() != 0);
        return 0;
    }
    assert(plan_first() == 0 && required == UINT64_C(20001656832));
    if (!strcmp(test, "copy_and_free_fail")) {
        assert(register_at(0) == 0);
        size_t successful_bytes = total;
        uintptr_t failed_host = base + ranges[1].begin;
        fail_copy = 2; fail_free = 7;
        assert(register_at(1) == 2);
        assert(free_calls == 1 && last_freed == (void *)(uintptr_t)0x2000);
        assert(total == successful_bytes && count == 1 && planned_next == 1);
        assert(executed_copy == successful_bytes);
        /* Reject lookup locally even if a next layer would report success. */
        void *output = (void *)(uintptr_t)0xcafe;
        assert(hipHostGetDevicePointer(&output, (void *)failed_host, 0) != 0);
        assert(hipHostGetDevicePointer(&output, (void *)(failed_host + 1), 0) != 0);
        assert(output == (void *)(uintptr_t)0xcafe && get_calls == 0);
        assert(hipHostUnregister((void *)failed_host) == 7 && free_calls == 2);
        assert(total == successful_bytes && count == 1 && planned_next == 1);
        fail_copy = fail_free = 0;
        assert(hipHostUnregister((void *)failed_host) == 0 && free_calls == 3);
        assert(last_freed == (void *)(uintptr_t)0x2000);
        assert(total == successful_bytes && executed_copy == successful_bytes && count == 1);
        assert(hipHostUnregister((void *)failed_host) == 0 && free_calls == 3);
        assert(register_at(1) != 0 && plan_first() != 0 && plan_overlay() != 0);
        assert(malloc_calls == 2 && copy_calls == 2 && register_calls == 0);
        assert(total == successful_bytes && planned_next == 1);
        assert(hipHostUnregister((void *)base) == 0 && free_calls == 4 && total == 0);
        assert(register_at(0) != 0 && executed_copy == successful_bytes);
        return 0;
    }
    if (!strcmp(test, "incomplete") || !strcmp(test, "repeat")) {
        if (!strcmp(test, "incomplete")) assert(register_at(0) == 0);
        assert(plan_overlay() != 0 && plan_first() != 0);
        assert(register_at(0) != 0);
        return 0;
    }
    if (!strcmp(test, "wrong_pointer"))
        result = hipHostRegister((void *)(base + 1), ranges[0].end, 10);
    else if (!strcmp(test, "wrong_size"))
        result = hipHostRegister((void *)base, ranges[0].end - 1, 10);
    else if (!strcmp(test, "wrong_flags"))
        result = hipHostRegister((void *)base, ranges[0].end, 8);
    else if (!strcmp(test, "branch_drift")) eligible_maps = 0;
    else if (!strcmp(test, "malloc_fail")) fail_malloc = 2;
    else if (!strcmp(test, "copy_fail")) fail_copy = 2;
    else if (!strcmp(test, "reserve")) free_kb = (size_t)12 << 20;
    else if (!strcmp(test, "missing_symbol")) missing_symbol = 1;
    else bad = -1;
    if (bad != -1) {
        if (result == -1) result = register_at(0);
        assert(result != 0 && total == 0);
        if (fail_copy) assert(free_calls == 1);
        eligible_maps = 1; fail_malloc = fail_copy = missing_symbol = 0;
        free_kb = (size_t)128 << 20;
        assert(register_at(0) != 0 && plan_first() != 0);
        return 0;
    }
    size_t simulated = 0, host_bytes = 0;
    for (size_t i = 0; i < 252; ++i) {
        size_t bytes = ranges[i].end - ranges[i].begin;
        int copies_here = bytes <= UINT64_C(51539607552) - simulated;
        if (!copies_here && !strcmp(test, "register_fail")) fail_register = 2;
        if (!copies_here && !strcmp(test, "host_drift")) eligible_maps = 0;
        int old_copy = copy_calls, old_register = register_calls;
        result = register_at(i);
        if (fail_register || !eligible_maps) {
            assert(result != 0);
            fail_register = 0; eligible_maps = 1;
            assert(register_at(i) != 0 && plan_overlay() != 0);
            return 0;
        }
        assert(result == 0);
        assert(copy_calls - old_copy == copies_here);
        assert(register_calls - old_register == !copies_here);
        if (copies_here) simulated += bytes;
        else host_bytes += bytes;
    }
    assert(total == simulated && simulated == UINT64_C(50433337536));
    assert(host_bytes == UINT64_C(20001656832));
    if (!strcmp(test, "cleanup") || !strcmp(test, "free_fail") || !strcmp(test, "host_cleanup")) {
        fail_free = !strcmp(test, "free_fail");
        uintptr_t address = base;
        if (!strcmp(test, "host_cleanup")) {
            size_t i = 0, running = 0;
            while (ranges[i].end - ranges[i].begin <= UINT64_C(51539607552) - running) {
                running += ranges[i].end - ranges[i].begin; ++i;
            }
            address += ranges[i].begin;
        }
        assert(hipHostUnregister((void *)address) == fail_free);
        if (fail_free) { fail_free = 0; assert(hipHostUnregister((void *)address) == 0); }
        assert(plan_overlay() != 0 && register_at(0) != 0);
        return 0;
    }
    assert(plan_overlay() == 0 && required == UINT64_C(2572351872));
    assert(register_at(252) == 0 && total == simulated);
    assert(plan_overlay() != 0 && plan_first() != 0 && register_at(252) != 0);
    assert(hipHostUnregister((void *)base) == 0 && free_calls == 1);
    return 0;
}
