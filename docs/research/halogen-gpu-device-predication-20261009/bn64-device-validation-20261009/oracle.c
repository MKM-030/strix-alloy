/* Source-only independent legacy oracle and fixed synthetic fixtures.
 * Root may include this file in host.c after defining BN64_ORACLE_LIBRARY.
 * No HIP calls, native engine imports, or model data are used here. */
#define BN64_VALIDATION_ABI_ONLY
#include "validator.hip"
#include <limits.h>
#include <stdio.h>
#include <string.h>

typedef struct Bn64Fixture {
    const char *name;
    int32_t raw[BN64_EXPERTS + 2];
    int32_t ids[BN64_EXPERTS];
    int32_t prefix[BN64_EXPERTS + 1];
    int32_t counts[2];
    unsigned char guards[4][BN64_GUARD_BYTES];
    uint32_t payload_byte; /* Host may poison item payloads with this byte. */
    uint32_t expected_histogram_pass;
    uint32_t expected_post_pass;
    uint32_t expected_segments; /* Valid-histogram expected value only. */
} Bn64Fixture;

/* Literal CPU predicate order from the archived histogram(), with only
 * explicit output clearing added. item_bindings_nonnull represents the
 * original host gu_items/dn_items/counts nonnull gate. */
static int bn64_legacy_histogram(const int32_t *raw, const int32_t *ids,
                                 const int32_t *prefix,
                                 int item_bindings_nonnull,
                                 int32_t *expected_gu, int32_t *expected_dn) {
    int active, total, sum = 0, segments = 0, index = 0, previous = -1;
    *expected_gu = 0;
    *expected_dn = 0;
    if (!raw || !ids || !prefix || !item_bindings_nonnull) return 0;
    active = raw[BN64_EXPERTS];
    total = raw[BN64_EXPERTS + 1];
    if (active < 1 || active > BN64_EXPERTS || total != BN64_ROUTED_ROWS) return 0;
    for (int e = 0; e < BN64_EXPERTS; ++e) {
        int rows = raw[e];
        if (rows < 0 || rows > BN64_ROUTED_ROWS) return 0;
        if (rows) {
            if (index >= active || ids[index] != e || e <= previous ||
                prefix[index] != sum) return 0;
            previous = e;
            ++index;
        }
        if (sum > BN64_ROUTED_ROWS - rows) return 0;
        sum += rows;
        segments += (rows + 63) / 64;
    }
    if (sum != BN64_ROUTED_ROWS || index != active ||
        prefix[active] != BN64_ROUTED_ROWS || segments > BN64_CAPACITY) return 0;
    *expected_gu = 5 * segments;
    *expected_dn = 10 * segments;
    return 1;
}

/* The legacy counts check short-circuits before guards, and each guard scan
 * short-circuits at its first wrong byte. The GPU aggregate checks all bytes. */
static int bn64_legacy_post(const int32_t *counts, int32_t expected_gu,
                           int32_t expected_dn,
                           const unsigned char *const guards[4]) {
    if (!counts || counts[0] != expected_gu || counts[1] != expected_dn) return 0;
    for (int i = 0; i < 4; ++i) {
        if (!guards[i]) return 0;
        for (size_t j = 0; j < BN64_GUARD_BYTES; ++j)
            if (guards[i][j] != 0xa5) return 0;
    }
    return 1;
}

static Bn64ValidationResult bn64_oracle_histogram_value(const int32_t *raw,
                                                  const int32_t *ids,
                                                  const int32_t *prefix,
                                                  uint64_t epoch) {
    Bn64ValidationResult result = {epoch, BN64_STAGE_HISTOGRAM, 0, 0, 0, 0,
                                   BN64_RESULT_MAGIC};
    uint64_t sum = 0, segments = 0;
    uint32_t index = 0;
    int32_t active;
    if (!raw || !ids || !prefix) {
        result.failures = BN64_BAD_BINDING;
        return result;
    }
    active = raw[BN64_EXPERTS];
    const int active_valid = active >= 1 && active <= BN64_EXPERTS;
    if (!active_valid) result.failures |= BN64_BAD_ACTIVE;
    if (raw[BN64_EXPERTS + 1] != BN64_ROUTED_ROWS) result.failures |= BN64_BAD_TOTAL;
    for (int e = 0; e < BN64_EXPERTS; ++e) {
        int32_t source_rows = raw[e];
        uint64_t rows = 0;
        if (source_rows < 0 || source_rows > BN64_ROUTED_ROWS)
            result.failures |= BN64_BAD_ROWS;
        else
            rows = (uint32_t)source_rows;
        if (rows) {
            if (!active_valid || index >= (uint32_t)active)
                result.failures |= BN64_BAD_INDEX;
            else {
                if (ids[index] != e) result.failures |= BN64_BAD_ID;
                if ((int64_t)prefix[index] != (int64_t)sum)
                    result.failures |= BN64_BAD_PREFIX;
            }
            ++index;
        }
        sum += rows;
        if (sum > BN64_ROUTED_ROWS) result.failures |= BN64_BAD_SUM_LIMIT;
        segments += (rows + 63) / 64;
    }
    if (sum != BN64_ROUTED_ROWS) result.failures |= BN64_BAD_SUM;
    if (!active_valid || index != (uint32_t)active)
        result.failures |= BN64_BAD_ACTIVE_COUNT;
    if (active_valid && prefix[active] != BN64_ROUTED_ROWS)
        result.failures |= BN64_BAD_TERMINAL_PREFIX;
    if (segments > BN64_CAPACITY) result.failures |= BN64_BAD_CAPACITY;
    result.segments = (uint32_t)segments;
    if (!result.failures) {
        result.expected_gu = (uint32_t)(5 * segments);
        result.expected_dn = (uint32_t)(10 * segments);
    }
    return result;
}

static Bn64ValidationResult bn64_oracle_post_value(const int32_t *counts,
                                            int32_t expected_gu,
                                            int32_t expected_dn,
                                            const unsigned char *const guards[4],
                                            uint64_t epoch) {
    Bn64ValidationResult result = {epoch, BN64_STAGE_POST_ITEMS, 0, 0, 0, 0,
                                   BN64_RESULT_MAGIC};
    const uint32_t guard_bits[4] = {BN64_BAD_GU_LEAD, BN64_BAD_GU_TRAIL,
                                  BN64_BAD_DN_LEAD, BN64_BAD_DN_TRAIL};
    /* All accepted histogram outputs satisfy this invocation invariant.
     * This is checked before publishing reusable stage-two expectations. */
    if (expected_gu < 5 || expected_gu > 5 * BN64_CAPACITY || expected_gu % 5 ||
        expected_dn != 2 * (int64_t)expected_gu) {
        result.failures |= BN64_BAD_EXPECTED;
    } else {
        result.segments = (uint32_t)(expected_gu / 5);
        result.expected_gu = (uint32_t)expected_gu;
        result.expected_dn = (uint32_t)expected_dn;
    }
    if (!counts) result.failures |= BN64_BAD_BINDING;
    else {
        if (counts[0] != expected_gu) result.failures |= BN64_BAD_GU_COUNT;
        if (counts[1] != expected_dn) result.failures |= BN64_BAD_DN_COUNT;
    }
    for (int i = 0; i < 4; ++i) {
        if (!guards[i]) result.failures |= BN64_BAD_BINDING;
        else for (size_t j = 0; j < BN64_GUARD_BYTES; ++j)
            if (guards[i][j] != 0xa5) result.failures |= guard_bits[i];
    }
    return result;
}

static void bn64_oracle_histogram(const int32_t *raw, const int32_t *ids,
                                 const int32_t *prefix, uint64_t epoch,
                                 Bn64ValidationResult *out) {
    *out = bn64_oracle_histogram_value(raw, ids, prefix, epoch);
}

static void bn64_oracle_post(const int32_t *counts, int32_t expected_gu,
                            int32_t expected_dn,
                            const unsigned char *const guards[4], uint64_t epoch,
                            Bn64ValidationResult *out) {
    *out = bn64_oracle_post_value(counts, expected_gu, expected_dn, guards, epoch);
}

enum Bn64FixtureKind {
    F_UNIFORM, F_SPARSE_BOUNDARIES, F_SKEW_MAX, F_SINGLE_LAST, F_IGNORED_TAILS,
    F_ACTIVE_ZERO, F_ACTIVE_NEGATIVE, F_ACTIVE_OVER,
    F_TOTAL_LOW, F_TOTAL_HIGH, F_ROWS_NEGATIVE, F_ROWS_OVER, F_ROWS_MIN, F_ROWS_MAX,
    F_SUM_LOW, F_SUM_HIGH, F_ACTIVE_FEW, F_ACTIVE_MANY,
    F_ID_FIRST, F_ID_MIDDLE, F_ID_LAST, F_ID_DUPLICATE, F_ID_REVERSED,
    F_ID_NEGATIVE, F_ID_OVER, F_PREFIX_FIRST, F_PREFIX_MIDDLE,
    F_PREFIX_TERMINAL, F_PREFIX_NEGATIVE, F_PREFIX_MAX,
    F_SUM_AND_CAPACITY, F_GU_LOW, F_DN_HIGH, F_COUNTS_SWAPPED,
    F_COUNTS_NEGATIVE, F_COUNTS_MAX,
    F_GU_LEAD_FIRST, F_GU_LEAD_MIDDLE, F_GU_LEAD_LAST,
    F_GU_TRAIL_FIRST, F_GU_TRAIL_MIDDLE, F_GU_TRAIL_LAST,
    F_DN_LEAD_FIRST, F_DN_LEAD_MIDDLE, F_DN_LEAD_LAST,
    F_DN_TRAIL_FIRST, F_DN_TRAIL_MIDDLE, F_DN_TRAIL_LAST,
    F_ALL_GUARDS, F_ITEM_PAYLOAD_IGNORED, BN64_FIXTURE_COUNT
};

static const char *const bn64_fixture_names[BN64_FIXTURE_COUNT] = {
    "uniform-512x160", "sparse-tail-boundaries", "max-segments-skew",
    "single-expert-511", "ignored-id-prefix-tails",
    "active-zero", "active-negative", "active-over-512",
    "total-low", "total-high", "rows-negative", "rows-over-R",
    "rows-INT_MIN", "rows-INT_MAX", "sum-low", "sum-high",
    "too-few-active", "too-many-active", "wrong-first-ID", "wrong-middle-ID",
    "wrong-last-ID", "duplicate-ID", "reversed-IDs", "negative-ID", "ID-512",
    "wrong-first-prefix", "wrong-middle-prefix", "wrong-terminal-prefix",
    "negative-prefix", "prefix-INT_MAX", "sum-failure-and-over-capacity",
    "GU-count-low", "DN-count-high", "swapped-counts", "negative-count",
    "count-INT_MAX", "GU-lead-first", "GU-lead-middle", "GU-lead-last",
    "GU-trail-first", "GU-trail-middle", "GU-trail-last",
    "DN-lead-first", "DN-lead-middle", "DN-lead-last",
    "DN-trail-first", "DN-trail-middle", "DN-trail-last",
    "all-four-guards", "item-payload-is-ignored"
};

/* Construct compact IDs and prefixes independently from the validators.
 * Called only with bounded nonnegative fixture counts; its sum fits int32. */
static void bn64_fixture_compact(Bn64Fixture *fixture) {
    int32_t sum = 0, active = 0;
    for (int e = 0; e < BN64_EXPERTS; ++e) {
        if (fixture->raw[e]) {
            fixture->ids[active] = e;
            fixture->prefix[active++] = sum;
        }
        sum += fixture->raw[e];
    }
    fixture->prefix[active] = sum;
    fixture->raw[BN64_EXPERTS] = active;
    fixture->raw[BN64_EXPERTS + 1] = BN64_ROUTED_ROWS;
}

static int bn64_fixture_init(size_t which, Bn64Fixture *fixture) {
    static const int experts[7] = {0, 3, 9, 16, 255, 510, 511};
    static const int rows[7] = {63, 64, 65, 127, 128, 129, 81344};
    if (which >= BN64_FIXTURE_COUNT || !fixture) return 0;
    memset(fixture, 0, sizeof(*fixture));
    fixture->name = bn64_fixture_names[which];
    fixture->payload_byte = 0xa5;
    memset(fixture->guards, 0xa5, sizeof(fixture->guards));
    /* Sparse boundary fixture is the common adversarial-test seed. */
    for (int i = 0; i < 7; ++i) fixture->raw[experts[i]] = rows[i];
    bn64_fixture_compact(fixture);
    fixture->expected_segments = 1282;
    fixture->expected_histogram_pass = 1;
    fixture->expected_post_pass = 1;
    if (which == F_UNIFORM) {
        for (int e = 0; e < BN64_EXPERTS; ++e) fixture->raw[e] = 160;
        bn64_fixture_compact(fixture);
        fixture->expected_segments = 1536;
    } else if (which == F_SKEW_MAX) {
        for (int e = 0; e < BN64_EXPERTS; ++e) fixture->raw[e] = e < 248 ? 193 : 129;
        bn64_fixture_compact(fixture);
        fixture->expected_segments = 1784;
    } else if (which == F_SINGLE_LAST) {
        memset(fixture->raw, 0, sizeof(fixture->raw));
        fixture->raw[511] = BN64_ROUTED_ROWS;
        bn64_fixture_compact(fixture);
        fixture->expected_segments = 1280;
    } else if (which == F_IGNORED_TAILS) {
        for (int i = 7; i < BN64_EXPERTS; ++i) fixture->ids[i] = INT_MIN;
        for (int i = 8; i <= BN64_EXPERTS; ++i) fixture->prefix[i] = INT_MAX;
    }
    fixture->counts[0] = (int32_t)(5 * fixture->expected_segments);
    fixture->counts[1] = (int32_t)(10 * fixture->expected_segments);
    if (which >= F_ACTIVE_ZERO && which <= F_SUM_AND_CAPACITY) {
        fixture->expected_histogram_pass = 0;
        fixture->expected_post_pass = 0; /* Stage two must not be submitted. */
        fixture->expected_segments = 0;
    }
    switch ((enum Bn64FixtureKind)which) {
    case F_ACTIVE_ZERO: fixture->raw[512] = 0; break;
    case F_ACTIVE_NEGATIVE: fixture->raw[512] = -1; break;
    case F_ACTIVE_OVER: fixture->raw[512] = 513; break;
    case F_TOTAL_LOW: fixture->raw[513] = BN64_ROUTED_ROWS - 1; break;
    case F_TOTAL_HIGH: fixture->raw[513] = BN64_ROUTED_ROWS + 1; break;
    case F_ROWS_NEGATIVE: fixture->raw[0] = -1; break;
    case F_ROWS_OVER: fixture->raw[255] = BN64_ROUTED_ROWS + 1; break;
    case F_ROWS_MIN: fixture->raw[511] = INT_MIN; break;
    case F_ROWS_MAX: fixture->raw[511] = INT_MAX; break;
    case F_SUM_LOW: --fixture->raw[511]; bn64_fixture_compact(fixture); break;
    case F_SUM_HIGH: ++fixture->raw[511]; bn64_fixture_compact(fixture); break;
    case F_ACTIVE_FEW: fixture->raw[512] = 6; break;
    case F_ACTIVE_MANY: fixture->raw[512] = 8; break;
    case F_ID_FIRST: fixture->ids[0] = 1; break;
    case F_ID_MIDDLE: fixture->ids[3] = 17; break;
    case F_ID_LAST: fixture->ids[6] = 510; break;
    case F_ID_DUPLICATE: fixture->ids[3] = fixture->ids[2]; break;
    case F_ID_REVERSED: fixture->ids[0] = 511; fixture->ids[6] = 0; break;
    case F_ID_NEGATIVE: fixture->ids[3] = -1; break;
    case F_ID_OVER: fixture->ids[6] = 512; break;
    case F_PREFIX_FIRST: fixture->prefix[0] = 1; break;
    case F_PREFIX_MIDDLE: ++fixture->prefix[3]; break;
    case F_PREFIX_TERMINAL: --fixture->prefix[7]; break;
    case F_PREFIX_NEGATIVE: fixture->prefix[3] = -1; break;
    case F_PREFIX_MAX: fixture->prefix[3] = INT_MAX; break;
    case F_SUM_AND_CAPACITY:
        for (int e = 0; e < BN64_EXPERTS; ++e) fixture->raw[e] = 193;
        bn64_fixture_compact(fixture); /* sum98816, segments2048: both fail. */
        break;
    case F_GU_LOW: --fixture->counts[0]; fixture->expected_post_pass = 0; break;
    case F_DN_HIGH: ++fixture->counts[1]; fixture->expected_post_pass = 0; break;
    case F_COUNTS_SWAPPED: {
        int32_t old_gu = fixture->counts[0];
        fixture->counts[0] = fixture->counts[1]; fixture->counts[1] = old_gu;
        fixture->expected_post_pass = 0; break;
    }
    case F_COUNTS_NEGATIVE: fixture->counts[0] = -1; fixture->expected_post_pass = 0; break;
    case F_COUNTS_MAX: fixture->counts[1] = INT_MAX; fixture->expected_post_pass = 0; break;
    case F_ALL_GUARDS:
        for (int i = 0; i < 4; ++i) fixture->guards[i][2048] = 0xa4;
        fixture->expected_post_pass = 0; break;
    case F_ITEM_PAYLOAD_IGNORED: fixture->payload_byte = 0x17; break;
    default:
        if (which >= F_GU_LEAD_FIRST && which <= F_DN_TRAIL_LAST) {
            const size_t positions[3] = {0, BN64_GUARD_BYTES / 2, BN64_GUARD_BYTES - 1};
            size_t offset = which - F_GU_LEAD_FIRST;
            fixture->guards[offset / 3][positions[offset % 3]] = 0xa4;
            fixture->expected_post_pass = 0;
        }
        break;
    }
    return 1;
}

/* Root-owned CPU execution can validate the fixture assertions before GPU
 * execution. This function contains no timing or performance assertions. */
static int bn64_oracle_selftest(void) {
    Bn64Fixture fixture;
    for (size_t i = 0; i < BN64_FIXTURE_COUNT; ++i) {
        int32_t gu = 0, dn = 0;
        if (!bn64_fixture_init(i, &fixture)) return 1;
        int legacy = bn64_legacy_histogram(fixture.raw, fixture.ids, fixture.prefix, 1, &gu, &dn);
        Bn64ValidationResult histogram;
        bn64_oracle_histogram(fixture.raw, fixture.ids, fixture.prefix, 1, &histogram);
        if ((uint32_t)legacy != fixture.expected_histogram_pass ||
            (!histogram.failures) != legacy || (legacy &&
            (histogram.segments != fixture.expected_segments ||
             histogram.expected_gu != (uint32_t)gu || histogram.expected_dn != (uint32_t)dn))) {
            fprintf(stderr, "histogram fixture mismatch: %s\n", fixture.name); return 1;
        }
        if (legacy) {
            const unsigned char *guards[4] = {fixture.guards[0], fixture.guards[1],
                                               fixture.guards[2], fixture.guards[3]};
            int post = bn64_legacy_post(fixture.counts, gu, dn, guards);
            Bn64ValidationResult aggregate;
            bn64_oracle_post(fixture.counts, gu, dn, guards, 1, &aggregate);
            if ((uint32_t)post != fixture.expected_post_pass || (!aggregate.failures) != post) {
                fprintf(stderr, "post fixture mismatch: %s\n", fixture.name); return 1;
            }
        }
        if (i == F_SUM_AND_CAPACITY && !(histogram.failures & BN64_BAD_CAPACITY)) {
            fprintf(stderr, "combined sum/capacity fixture lacks capacity rejection\n"); return 1;
        }
    }
    return 0;
}

#ifndef BN64_ORACLE_LIBRARY
int main(void) {
    int result = bn64_oracle_selftest();
    if (!result) printf("BN64 oracle: %d fixed fixtures passed\n", BN64_FIXTURE_COUNT);
    return result;
}
#endif
