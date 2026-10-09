/* Root-owned isolated validation probe. No model, engine pointer or NPU access.
 * All device spans are explicitly allocated here and remain live until cleanup.
 * Timing includes both waits, every D2H copy and all validation decisions.
 * Fixture upload, module/symbol loading and allocation are outside timing. */
#define _POSIX_C_SOURCE 200809L
#define BN64_ORACLE_LIBRARY
#include "oracle.c"
#include <dlfcn.h>
#include <inttypes.h>
#include <stdlib.h>
#include <time.h>

enum { H2D = 1, D2H = 2, PAIRS = 64, WARMUP_PAIRS = 8 };
static int (*p_hipMalloc)(void **, size_t);
static int (*p_hipFree)(void *);
static int (*p_hipMemcpy)(void *, const void *, size_t, int);
static int (*p_hipStreamSynchronize)(void *);
static int (*p_hipModuleLoad)(void **, const char *);
static int (*p_hipModuleGetFunction)(void **, void *, const char *);
static int (*p_hipModuleLaunchKernel)(void *, unsigned, unsigned, unsigned,
                                    unsigned, unsigned, unsigned, unsigned,
                                    void *, void **, void **);
static int (*p_hipModuleUnload)(void *);

typedef struct Device {
    void *raw, *ids, *prefix, *counts, *gu_buffer, *dn_buffer, *result;
    void *histogram_kernel, *post_kernel;
    unsigned char *guards[4];
} Device;
static uint64_t next_epoch = UINT64_C(0x2026100900000000);

static int checked(int code, const char *operation) {
    if (!code) return 1;
    fprintf(stderr, "HIP operation=%s status=%d\n", operation, code);
    return 0;
}
static int resolve(void *library, const char *name, void *destination, size_t bytes) {
    dlerror();
    void *symbol = dlsym(library, name);
    const char *error = dlerror();
    if (error || !symbol || bytes != sizeof(symbol)) {
        fprintf(stderr, "resolve %s: %s\n", name, error ? error : "pointer ABI");
        return 0;
    }
    memcpy(destination, &symbol, bytes);
    return 1;
}
#define LOAD(name) do { if (!resolve(library, #name, &p_##name, sizeof(p_##name))) goto cleanup; } while (0)
#define HIP(call) do { if (!checked((call), #call)) return 0; } while (0)

static uint64_t now_ns(void) {
    struct timespec stamp;
    if (clock_gettime(CLOCK_MONOTONIC_RAW, &stamp)) return 0;
    return (uint64_t)stamp.tv_sec * UINT64_C(1000000000) + (uint64_t)stamp.tv_nsec;
}
static int valid_status(const Bn64ValidationResult *result, uint64_t epoch,
                        uint32_t stage) {
    if (result->epoch == epoch && result->stage == stage &&
        result->magic == BN64_RESULT_MAGIC) return 1;
    fprintf(stderr, "stale or malformed result: epoch=%" PRIu64 " stage=%u magic=%u\n",
            result->epoch, result->stage, result->magic);
    return 0;
}
static int histogram(Device *device, uint64_t epoch, Bn64ValidationResult *result) {
    void *arguments[] = { &device->raw, &device->ids, &device->prefix,
                          &epoch, &device->result };
    memset(result, 0xcc, sizeof(*result));
    HIP(p_hipMemcpy(device->result, result, sizeof(*result), H2D));
    HIP(p_hipModuleLaunchKernel(device->histogram_kernel, 1, 1, 1,
                                BN64_THREADS, 1, 1, 0, NULL, arguments, NULL));
    HIP(p_hipStreamSynchronize(NULL)); /* First mandatory decision boundary. */
    HIP(p_hipMemcpy(result, device->result, sizeof(*result), D2H));
    return valid_status(result, epoch, BN64_STAGE_HISTOGRAM);
}
static int post(Device *device, int32_t gu, int32_t dn, uint64_t epoch,
                Bn64ValidationResult *result) {
    void *arguments[] = { &device->counts, &gu, &dn,
                          &device->guards[0], &device->guards[1],
                          &device->guards[2], &device->guards[3],
                          &epoch, &device->result };
    memset(result, 0xcc, sizeof(*result));
    HIP(p_hipMemcpy(device->result, result, sizeof(*result), H2D));
    HIP(p_hipModuleLaunchKernel(device->post_kernel, 1, 1, 1,
                                BN64_THREADS, 1, 1, 0, NULL, arguments, NULL));
    HIP(p_hipStreamSynchronize(NULL)); /* Second mandatory decision boundary. */
    HIP(p_hipMemcpy(result, device->result, sizeof(*result), D2H));
    return valid_status(result, epoch, BN64_STAGE_POST_ITEMS);
}
static int upload(Device *device, const Bn64Fixture *fixture,
                  unsigned char *gu_buffer, unsigned char *dn_buffer) {
    const size_t gu_size = BN64_GU_ITEMS_BYTES + 2 * BN64_GUARD_BYTES;
    const size_t dn_size = BN64_DN_ITEMS_BYTES + 2 * BN64_GUARD_BYTES;
    memset(gu_buffer, (int)fixture->payload_byte, gu_size);
    memset(dn_buffer, (int)fixture->payload_byte, dn_size);
    memcpy(gu_buffer, fixture->guards[0], BN64_GUARD_BYTES);
    memcpy(gu_buffer + BN64_GUARD_BYTES + BN64_GU_ITEMS_BYTES,
           fixture->guards[1], BN64_GUARD_BYTES);
    memcpy(dn_buffer, fixture->guards[2], BN64_GUARD_BYTES);
    memcpy(dn_buffer + BN64_GUARD_BYTES + BN64_DN_ITEMS_BYTES,
           fixture->guards[3], BN64_GUARD_BYTES);
    HIP(p_hipMemcpy(device->raw, fixture->raw, sizeof(fixture->raw), H2D));
    HIP(p_hipMemcpy(device->ids, fixture->ids, sizeof(fixture->ids), H2D));
    HIP(p_hipMemcpy(device->prefix, fixture->prefix, sizeof(fixture->prefix), H2D));
    HIP(p_hipMemcpy(device->counts, fixture->counts, sizeof(fixture->counts), H2D));
    HIP(p_hipMemcpy(device->gu_buffer, gu_buffer, gu_size, H2D));
    HIP(p_hipMemcpy(device->dn_buffer, dn_buffer, dn_size, H2D));
    return 1;
}

/* Literal successful legacy validation path: three + five blocking copies. */
static int legacy_transaction(Device *device) {
    int32_t raw[BN64_EXPERTS + 2], ids[BN64_EXPERTS], prefix[BN64_EXPERTS + 1];
    int32_t counts[2], gu = 0, dn = 0;
    unsigned char buffer[BN64_GUARD_BYTES];
    HIP(p_hipStreamSynchronize(NULL));
    HIP(p_hipMemcpy(raw, device->raw, sizeof(raw), D2H));
    HIP(p_hipMemcpy(ids, device->ids, sizeof(ids), D2H));
    HIP(p_hipMemcpy(prefix, device->prefix, sizeof(prefix), D2H));
    if (!bn64_legacy_histogram(raw, ids, prefix, 1, &gu, &dn)) return 0;
    HIP(p_hipStreamSynchronize(NULL));
    HIP(p_hipMemcpy(counts, device->counts, sizeof(counts), D2H));
    if (counts[0] != gu || counts[1] != dn) return 0;
    for (unsigned g = 0; g < 4; ++g) {
        HIP(p_hipMemcpy(buffer, device->guards[g], BN64_GUARD_BYTES, D2H));
        for (size_t j = 0; j < sizeof(buffer); ++j)
            if (buffer[j] != 0xa5) return 0;
    }
    return 1;
}
static int device_transaction(Device *device) {
    Bn64ValidationResult first, second;
    uint64_t epoch = ++next_epoch;
    if (!histogram(device, epoch, &first) || first.failures) return 0;
    if (first.segments < 1 || first.segments > BN64_CAPACITY ||
        first.expected_gu != 5 * first.segments ||
        first.expected_dn != 10 * first.segments) return 0;
    if (!post(device, (int32_t)first.expected_gu, (int32_t)first.expected_dn,
              epoch, &second) || second.failures) return 0;
    return second.segments == first.segments &&
           second.expected_gu == first.expected_gu && second.expected_dn == first.expected_dn;
}
static int compare_result(const Bn64ValidationResult *actual,
                          const Bn64ValidationResult *expected, const char *name) {
    if (!memcmp(actual, expected, sizeof(*actual))) return 1;
    fprintf(stderr, "result mismatch fixture=%s stage=%u actual_bits=%u expected_bits=%u\n",
            name, expected->stage, actual->failures, expected->failures);
    return 0;
}
static int correctness(Device *device, unsigned char *gu_buffer, unsigned char *dn_buffer) {
    Bn64Fixture fixture;
    for (size_t i = 0; i < BN64_FIXTURE_COUNT; ++i) {
        if (!bn64_fixture_init(i, &fixture) || !upload(device, &fixture, gu_buffer, dn_buffer)) return 0;
        uint64_t epoch = ++next_epoch;
        Bn64ValidationResult actual, expected;
        bn64_oracle_histogram(fixture.raw, fixture.ids, fixture.prefix, epoch, &expected);
        if (!histogram(device, epoch, &actual) || !compare_result(&actual, &expected, fixture.name)) return 0;
        int stage_two = 0;
        if (!actual.failures) {
            int32_t gu = (int32_t)actual.expected_gu, dn = (int32_t)actual.expected_dn;
            const unsigned char *guards[4] = { fixture.guards[0], fixture.guards[1],
                                               fixture.guards[2], fixture.guards[3] };
            bn64_oracle_post(fixture.counts, gu, dn, guards, epoch, &expected);
            if (!post(device, gu, dn, epoch, &actual) ||
                !compare_result(&actual, &expected, fixture.name)) return 0;
            stage_two = 1;
        }
        printf("{\"type\":\"fixture\",\"fixture\":\"%s\",\"passed\":true,\"post_submitted\":%s}\n",
               fixture.name, stage_two ? "true" : "false");
    }
    return 1;
}
static int timed(Device *device, int accelerated, uint64_t *elapsed) {
    uint64_t start = now_ns();
    int accepted = accelerated ? device_transaction(device) : legacy_transaction(device);
    uint64_t end = now_ns();
    if (!accepted || !start || end <= start) {
        fprintf(stderr, "timed arm failed: accelerated=%d accepted=%d\n", accelerated, accepted);
        return 0;
    }
    *elapsed = end - start;
    return 1;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (bn64_oracle_selftest()) return 1;
    if (argc == 2 && !strcmp(argv[1], "--oracle-only")) {
        printf("{\"type\":\"oracle\",\"passed\":true,\"fixtures\":%u,\"hardware_executed\":false}\n", BN64_FIXTURE_COUNT);
        return 0;
    }
    if (argc != 3) {
        fprintf(stderr, "usage: host --oracle-only OR host module.hsaco libamdhip64.so\n");
        return 2;
    }
    Device device = {0};
    void *library = NULL, *module = NULL;
    unsigned char *gu_buffer = NULL, *dn_buffer = NULL;
    int exit_code = 1;
    unsigned paired = 0;
    const size_t gu_size = BN64_GU_ITEMS_BYTES + 2 * BN64_GUARD_BYTES;
    const size_t dn_size = BN64_DN_ITEMS_BYTES + 2 * BN64_GUARD_BYTES;
    library = dlopen(argv[2], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "dlopen: %s\n", dlerror()); goto cleanup; }
    LOAD(hipMalloc); LOAD(hipFree); LOAD(hipMemcpy); LOAD(hipStreamSynchronize);
    LOAD(hipModuleLoad); LOAD(hipModuleGetFunction); LOAD(hipModuleLaunchKernel); LOAD(hipModuleUnload);
    void **allocations[] = { &device.raw, &device.ids, &device.prefix, &device.counts,
                             &device.gu_buffer, &device.dn_buffer, &device.result };
    const size_t sizes[] = { (BN64_EXPERTS + 2) * sizeof(int32_t), BN64_EXPERTS * sizeof(int32_t),
                            (BN64_EXPERTS + 1) * sizeof(int32_t), 2 * sizeof(int32_t),
                            gu_size, dn_size, sizeof(Bn64ValidationResult) };
    for (size_t i = 0; i < sizeof(sizes) / sizeof(sizes[0]); ++i)
        if (!checked(p_hipMalloc(allocations[i], sizes[i]), "hipMalloc-owned-fixture")) goto cleanup;
    device.guards[0] = device.gu_buffer;
    device.guards[1] = (unsigned char *)device.gu_buffer + BN64_GUARD_BYTES + BN64_GU_ITEMS_BYTES;
    device.guards[2] = device.dn_buffer;
    device.guards[3] = (unsigned char *)device.dn_buffer + BN64_GUARD_BYTES + BN64_DN_ITEMS_BYTES;
    gu_buffer = malloc(gu_size); dn_buffer = malloc(dn_size);
    if (!gu_buffer || !dn_buffer) goto cleanup;
    if (!checked(p_hipModuleLoad(&module, argv[1]), "hipModuleLoad") ||
        !checked(p_hipModuleGetFunction(&device.histogram_kernel, module, "bn64_validate_histogram"), "histogram-symbol") ||
        !checked(p_hipModuleGetFunction(&device.post_kernel, module, "bn64_validate_post"), "post-symbol")) goto cleanup;
    if (!correctness(&device, gu_buffer, dn_buffer)) goto cleanup;
    const size_t kinds[] = { F_UNIFORM, F_SPARSE_BOUNDARIES, F_SKEW_MAX, F_SINGLE_LAST };
    for (size_t shape = 0; shape < sizeof(kinds) / sizeof(kinds[0]); ++shape) {
        Bn64Fixture fixture;
        if (!bn64_fixture_init(kinds[shape], &fixture) ||
            !upload(&device, &fixture, gu_buffer, dn_buffer)) goto cleanup;
        for (unsigned pair = 0; pair < WARMUP_PAIRS + PAIRS; ++pair) {
            uint64_t legacy = 0, aggregate = 0;
            int accelerated_first = (pair & 1) != 0;
            if (accelerated_first) {
                if (!timed(&device, 1, &aggregate) || !timed(&device, 0, &legacy)) goto cleanup;
            } else {
                if (!timed(&device, 0, &legacy) || !timed(&device, 1, &aggregate)) goto cleanup;
            }
            if (pair < WARMUP_PAIRS) continue;
            ++paired;
            printf("{\"type\":\"paired\",\"fixture\":\"%s\",\"pair\":%u,\"accelerated_first\":%s,"
                   "\"legacy_ns\":%" PRIu64 ",\"aggregate_ns\":%" PRIu64 "}\n",
                   fixture.name, pair - WARMUP_PAIRS, accelerated_first ? "true" : "false", legacy, aggregate);
        }
    }
    exit_code = 0;
cleanup:
    /* Free each owned span on every error path; never operate on engine memory. */
    if (p_hipFree) {
        void *spans[] = { device.raw, device.ids, device.prefix, device.counts,
                          device.gu_buffer, device.dn_buffer, device.result };
        for (size_t i = 0; i < sizeof(spans) / sizeof(spans[0]); ++i)
            if (spans[i] && !checked(p_hipFree(spans[i]), "hipFree-owned-fixture")) exit_code = 1;
    }
    if (module && p_hipModuleUnload && !checked(p_hipModuleUnload(module), "hipModuleUnload")) exit_code = 1;
    free(gu_buffer); free(dn_buffer);
    if (library && dlclose(library)) exit_code = 1;
    if (!exit_code)
        printf("{\"type\":\"summary\",\"passed\":true,\"fixtures\":%u,\"pairs\":%u,"
               "\"warmup_pairs_per_shape\":%u,\"clock\":\"CLOCK_MONOTONIC_RAW\","
               "\"legacy_D2H_calls_per_transaction\":8,\"aggregate_D2H_calls_per_transaction\":2,"
               "\"legacy_D2H_bytes_per_transaction\":22548,\"aggregate_D2H_bytes_per_transaction\":64,"
               "\"aggregate_poison_H2D_calls_per_transaction\":2,\"aggregate_poison_H2D_bytes_per_transaction\":64,"
               "\"explicit_waits_per_arm\":2,\"GPU_allocated_bytes\":452660,"
               "\"engine_requests\":0,\"NPU_executed\":false,\"serving_gain_qualified\":false}\n",
               BN64_FIXTURE_COUNT, paired, WARMUP_PAIRS);
    return exit_code;
}
