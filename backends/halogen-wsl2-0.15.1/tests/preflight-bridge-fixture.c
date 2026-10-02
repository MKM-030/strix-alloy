#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "../patches/hip-preflight-plan.h"

struct halogen_preflight_range_v1 fixture_ranges[2] = {{0, 4096}, {8192, 12288}};
uintptr_t fixture_begin, fixture_end;
uintptr_t fixture_object[2] = {0x100000000ULL, 16384};
uint64_t fixture_floor = 17179869184ULL, fixture_available;
uint64_t fixture_aggregate = 8192;
uint64_t fixture_before[18], fixture_after[18];
uint64_t fixture_frame_before[15], fixture_frame_after[15];
unsigned char fixture_fp_before[512] __attribute__((aligned(16)));
unsigned char fixture_fp_after[512] __attribute__((aligned(16)));
unsigned char fixture_writable[64];
void *fixture_bridge;
extern void fixture_abi(void);
extern int fixture_admission(void);
extern void fixture_original(void);
extern unsigned char fixture_site[], fixture_bad_signature[];
static const char *scenario;
static unsigned char *occupied_candidate;

static void occupy_candidate(int argc, char **argv, char **envp) {
    (void)argc; (void)argv;
    /* glibc has not yet published environ during executable preinit. */
    int requested = 0;
    for (char **item = envp; *item; ++item)
        if (!strcmp(*item, "FIXTURE_OCCUPY_CANDIDATE=1")) requested = 1;
    if (!requested) return;
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    void *candidate = (void *)(((uintptr_t)fixture_site & ~(page - 1)) + 0x200000);
    occupied_candidate = mmap(candidate, page, PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(occupied_candidate == candidate);
    memset(occupied_candidate, 0xa7, page);
}
__attribute__((section(".preinit_array"), used))
static void (*const preinit_occupy)(int, char **, char **) = occupy_candidate;

int halogen_hybrid_preflight_v1(uintptr_t base, size_t bytes,
 const struct halogen_preflight_range_v1 *ranges, size_t count,
 size_t aggregate, size_t *host) {
    assert(base == fixture_object[0] && bytes == fixture_object[1]);
    assert(ranges == fixture_ranges && count == 2 && aggregate == fixture_aggregate);
    assert(((uintptr_t)__builtin_frame_address(0) & 15) == 0);
    /* Deliberately destroy caller-saved floating state; trampoline restores it. */
    unsigned mxcsr = 0x1f80;
    __asm__ volatile("fninit; ldmxcsr %0; pxor %%xmm0, %%xmm0; pxor %%xmm15, %%xmm15"
                     : : "m"(mxcsr) : "xmm0", "xmm15");
    if (!strcmp(scenario, "planner_error")) return -1;
    *host = !strcmp(scenario, "too_large") ? aggregate + 1 :
            !strcmp(scenario, "overflow") ? SIZE_MAX - 1024 : 4096;
    return 0;
}

static void assert_rx(const void *address) {
    FILE *f = fopen("/proc/self/maps", "r");
    assert(f);
    char line[1024], perms[5]; unsigned long begin, end; int found = 0;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%lx-%lx %4s", &begin, &end, perms) == 3 &&
            (uintptr_t)address >= begin && (uintptr_t)address < end) {
            assert(!strcmp(perms, "r-xp")); found = 1; break;
        }
    }
    assert(fclose(f) == 0 && found);
}

int main(int argc, char **argv) {
    assert(argc == 2); scenario = argv[1];
    if (!strcmp(scenario, "inert")) { puts("inert"); return 0; }
    fixture_begin = (uintptr_t)fixture_ranges;
    fixture_end = fixture_begin + sizeof fixture_ranges;
    fixture_available = fixture_floor + (!strcmp(scenario, "low") ? 4095 : 4096);
    if (!strcmp(scenario, "reversed")) fixture_end = fixture_begin - 16;
    if (!strcmp(scenario, "misaligned")) fixture_begin++;
    if (!strcmp(scenario, "oversized")) fixture_end = fixture_begin + 1048576 * 16ULL;
    if (!strcmp(scenario, "null_object")) fixture_object[0] = 0;
    if (!strcmp(scenario, "floor")) fixture_floor--;
    if (!strcmp(scenario, "overflow")) fixture_aggregate = SIZE_MAX;
    fixture_bridge = dlsym(RTLD_DEFAULT, "halogen_preflight_trampoline");
    if (!fixture_bridge) fixture_bridge = fixture_original;
    if (!strcmp(scenario, "admission") || !strcmp(scenario, "low")) {
        int admitted = fixture_admission();
        assert(admitted == !!strcmp(scenario, "low"));
        assert(fixture_aggregate == 8192);
        assert(fixture_site[0] == 0xe8);
        int32_t displacement; memcpy(&displacement, fixture_site + 1, 4);
        assert_rx(fixture_site);
        assert_rx(fixture_site + 5 + displacement);
        static const unsigned char untouched[] = {0x48,0x01,0xd0,0x48,0x29,0xf0,
            0x4c,0x8b,0x6c,0x24,0x30,0x4c,0x8b,0x7c,0x24,0x08,
            0x0f,0x87,0x1f,0x08,0x00,0x00};
        assert(!memcmp(fixture_site + 5, untouched, sizeof untouched));
        if (occupied_candidate) {
            for (size_t i = 0; i < (size_t)sysconf(_SC_PAGESIZE); ++i)
                assert(occupied_candidate[i] == 0xa7);
            puts("occupied candidate unchanged");
        }
        puts("admission and RX verified"); return 0;
    }
    fixture_abi();
    assert(fixture_after[0] == 4096);
    for (size_t i = 1; i < 18; ++i) assert(fixture_before[i] == fixture_after[i]);
    assert(!memcmp(fixture_fp_before, fixture_fp_after, 512));
    assert(!memcmp(fixture_frame_before, fixture_frame_after, 120));
    assert(fixture_aggregate == 8192);
    puts("ABI GP/flags/x87/MXCSR/XMM/stack/frame verified");
    return 0;
}
