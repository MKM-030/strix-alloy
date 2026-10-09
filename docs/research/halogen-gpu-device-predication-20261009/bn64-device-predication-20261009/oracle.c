/* Independent CPU predicates plus preparation/selection protocol fixtures.
 * No HIP, native engine execution, timing, or model data. Root owns execution.
 * Define BN64_PREDICATION_ORACLE_LIBRARY before including from component-host.c. */
#define BN64_PREDICATION_ABI_ONLY
#include "predication.hip"
#define BN64_ORACLE_LIBRARY
#include "../bn64-device-validation-20261009/oracle.c"

#ifdef __cplusplus
extern "C" {
#endif

static void bn64p_oracle_defaults(const Bn64Prepare64Args *a) {
    memset(a->private_raw, 0, (BN64_EXPERTS + 2) * sizeof(int32_t));
    a->private_raw[BN64_EXPERTS + 1] = BN64_ROUTED_ROWS;
    memset(a->private_ids, 0, BN64_EXPERTS * sizeof(int32_t));
    memset(a->private_prefix, 0, (BN64_EXPERTS + 1) * sizeof(int32_t));
    a->raw64_counts[0] = a->raw64_counts[1] = 0;
    a->selected128_counts[0] = a->native128_counts[0];
    a->selected128_counts[1] = a->native128_counts[1];
    a->selected64_counts[0] = a->selected64_counts[1] = 0;
    {
        Bn64ValidationResult poison = {a->epoch, BN64_STAGE_POISON,
                                       BN64_POST_UNWRITTEN, 0, 0, 0, 0};
        *a->post_status = poison;
    }
}

void bn64p_oracle_prepare(const Bn64Prepare64Args *a, int geometry_valid) {
    Bn64ValidationResult result;
    int32_t gu = 0, dn = 0;
    int legacy_pass = 0;
    bn64p_oracle_defaults(a);
    if (geometry_valid) {
        /* Archived serial diagnostics and independently short-circuiting
         * legacy predicate remain authoritative for the histogram. */
        result = bn64_oracle_histogram_value(a->raw, a->ids, a->prefix, a->epoch);
        legacy_pass = bn64_legacy_histogram(a->raw, a->ids, a->prefix, 1, &gu, &dn);
    } else {
        Bn64ValidationResult shape = {a->epoch, BN64_STAGE_HISTOGRAM,
                                     BN64_BAD_SHAPE, 0, 0, 0, BN64_RESULT_MAGIC};
        result = shape;
    }
    if (*a->sticky_failure) result.failures |= BN64_BAD_STICKY;
    if (result.failures || !legacy_pass) {
        /* legacy_pass can only differ from diagnostics if the archived oracle
         * itself is inconsistent; selftest checks their agreement. */
        *a->sticky_failure |= 1u;
        result.expected_gu = result.expected_dn = 0;
    } else {
        size_t active = (size_t)a->raw[BN64_EXPERTS];
        memcpy(a->private_raw, a->raw, (BN64_EXPERTS + 2) * sizeof(int32_t));
        memcpy(a->private_ids, a->ids, active * sizeof(int32_t));
        memcpy(a->private_prefix, a->prefix, (active + 1) * sizeof(int32_t));
    }
    *a->state = result;
}

void bn64p_oracle_post(const Bn64PostSelectArgs *a, int geometry_valid) {
    Bn64ValidationResult input = *a->state;
    Bn64ValidationResult result = {a->epoch, BN64_STAGE_POST_ITEMS, 0,
                                   0, 0, 0, BN64_RESULT_MAGIC};
    const unsigned char *guards[4] = {a->gu_lead, a->gu_trail,
                                     a->dn_lead, a->dn_trail};
    const uint64_t gu = UINT64_C(5) * input.segments;
    const uint64_t dn = UINT64_C(10) * input.segments;
    const int coherent = input.segments >= 1 && input.segments <= BN64_CAPACITY &&
        input.expected_gu == gu && input.expected_dn == dn;
    a->selected128_counts[0] = a->native128_counts[0];
    a->selected128_counts[1] = a->native128_counts[1];
    a->selected64_counts[0] = a->selected64_counts[1] = 0;
    if (!geometry_valid) result.failures = BN64_BAD_SHAPE;
    else {
        /* Reuse the independent archived full-guard diagnostic scan. Counts
         * below are compared to mathematical 64-bit products, including
         * corrupt segment fields whose products do not fit uint32/int32. */
        Bn64ValidationResult legacy = bn64_oracle_post_value(a->raw64_counts,
                                                            0, 0, guards, a->epoch);
        result.failures = legacy.failures & ~(BN64_BAD_EXPECTED |
                                              BN64_BAD_GU_COUNT | BN64_BAD_DN_COUNT);
        if (!coherent) result.failures |= BN64_BAD_EXPECTED;
        if (a->raw64_counts) {
            if ((int64_t)a->raw64_counts[0] != (int64_t)gu)
                result.failures |= BN64_BAD_GU_COUNT;
            if ((int64_t)a->raw64_counts[1] != (int64_t)dn)
                result.failures |= BN64_BAD_DN_COUNT;
        }
        if (input.epoch != a->epoch) result.failures |= BN64_BAD_EPOCH;
        if (input.stage != BN64_STAGE_HISTOGRAM) result.failures |= BN64_BAD_STAGE;
        if (input.magic != BN64_RESULT_MAGIC) result.failures |= BN64_BAD_MAGIC;
        if (input.failures)
            result.failures |= input.failures | BN64_BAD_FIRST_STAGE;
        if (coherent) {
            result.segments = input.segments;
            result.expected_gu = (uint32_t)gu;
            result.expected_dn = (uint32_t)dn;
        }
        if (!result.failures && !*a->sticky_failure &&
            !bn64_legacy_post(a->raw64_counts, (int32_t)gu, (int32_t)dn, guards))
            result.failures |= BN64_BAD_FIRST_STAGE; /* unreachable legacy disagreement */
    }
    if (*a->sticky_failure) result.failures |= BN64_BAD_STICKY;
    if (result.failures) *a->sticky_failure |= 1u;
    else {
        a->selected128_counts[0] = a->selected128_counts[1] = 0;
        a->selected64_counts[0] = a->raw64_counts[0];
        a->selected64_counts[1] = a->raw64_counts[1];
    }
    /* Correct-shape decisions consume even rejection; shape rejection leaves
     * the entire first-stage record untouched. */
    if (geometry_valid) a->state->stage = BN64_STAGE_CONSUMED;
    *a->post_status = result;
}

typedef struct Bn64PTestMemory {
    int32_t private_raw[BN64_EXPERTS + 2];
    int32_t private_ids[BN64_EXPERTS];
    int32_t private_prefix[BN64_EXPERTS + 1];
    int32_t native128_counts[2], raw64_counts[2];
    int32_t selected128_counts[2], selected64_counts[2];
    Bn64ValidationResult state, post_status;
    uint32_t sticky_failure;
} Bn64PTestMemory;

/* This is the ONLY selftest reset of sticky: a new owned-allocation model. */
static void bn64p_test_new_allocation(Bn64PTestMemory *m) {
    memset(m, 0xcc, sizeof(*m));
    m->sticky_failure = 0;
    m->native128_counts[0] = 71;
    m->native128_counts[1] = 142;
}
static Bn64Prepare64Args bn64p_test_prepare_args(Bn64Fixture *f, Bn64PTestMemory *m,
                                                uint64_t epoch) {
    Bn64Prepare64Args a = {f->raw, f->ids, f->prefix, m->native128_counts, epoch,
        m->private_raw, m->private_ids, m->private_prefix, m->raw64_counts,
        m->selected128_counts, m->selected64_counts, &m->state,
        &m->post_status, &m->sticky_failure};
    return a;
}
static Bn64PostSelectArgs bn64p_test_post_args(Bn64Fixture *f, Bn64PTestMemory *m,
                                             uint64_t epoch) {
    Bn64PostSelectArgs a = {&m->state, epoch, m->raw64_counts, m->native128_counts,
        f->guards[0], f->guards[1], f->guards[2], f->guards[3],
        m->selected128_counts, m->selected64_counts, &m->post_status,
        &m->sticky_failure};
    return a;
}
static int bn64p_test_check(int pass, const char *name, const char *detail) {
    if (pass) return 0;
    fprintf(stderr, "predication fixture mismatch: %s (%s)\n", name, detail);
    return 1;
}
static int bn64p_test_private(const Bn64Fixture *f, const Bn64PTestMemory *m,
                              int accepted) {
    for (int i = 0; i < BN64_EXPERTS + 2; ++i) {
        int32_t expected = accepted ? f->raw[i] :
            (i == BN64_EXPERTS + 1 ? BN64_ROUTED_ROWS : 0);
        if (m->private_raw[i] != expected) return 0;
    }
    for (int i = 0; i < BN64_EXPERTS; ++i)
        if (m->private_ids[i] != (accepted && i < f->raw[BN64_EXPERTS] ? f->ids[i] : 0))
            return 0;
    for (int i = 0; i <= BN64_EXPERTS; ++i)
        if (m->private_prefix[i] != (accepted && i <= f->raw[BN64_EXPERTS] ? f->prefix[i] : 0))
            return 0;
    return 1;
}
static int bn64p_test_selection(const Bn64PTestMemory *m, int accepted) {
    for (int i = 0; i < 2; ++i)
        if (m->selected128_counts[i] != (accepted ? 0 : m->native128_counts[i]) ||
            m->selected64_counts[i] != (accepted ? m->raw64_counts[i] : 0)) return 0;
    return 1;
}
static int bn64p_test_post_record(const Bn64PTestMemory *m,
                                 const Bn64ValidationResult *before,
                                 uint64_t epoch, uint32_t failures, int coherent,
                                 int consume) {
    Bn64ValidationResult expected = {epoch, BN64_STAGE_POST_ITEMS, failures,
        coherent ? before->segments : 0,
        coherent ? (uint32_t)(UINT64_C(5) * before->segments) : 0,
        coherent ? (uint32_t)(UINT64_C(10) * before->segments) : 0, BN64_RESULT_MAGIC};
    Bn64ValidationResult consumed = *before;
    if (consume) consumed.stage = BN64_STAGE_CONSUMED;
    return !memcmp(&m->post_status, &expected, sizeof(expected)) &&
           !memcmp(&m->state, &consumed, sizeof(consumed)) &&
           bn64p_test_selection(m, failures == 0);
}

int bn64p_oracle_selftest(void) {
    Bn64Fixture f;
    Bn64PTestMemory m;
    if (bn64_oracle_selftest()) return 1;
    /* Reuse all archived focused histogram/count/guard fixtures. */
    for (size_t i = 0; i < BN64_FIXTURE_COUNT; ++i) {
        Bn64ValidationResult expected, poison;
        Bn64Prepare64Args prepare;
        if (!bn64_fixture_init(i, &f)) return 1;
        bn64p_test_new_allocation(&m);
        prepare = bn64p_test_prepare_args(&f, &m, UINT64_C(0xfedcba9876543210));
        expected = bn64_oracle_histogram_value(f.raw, f.ids, f.prefix, prepare.epoch);
        poison.epoch = prepare.epoch; poison.stage = BN64_STAGE_POISON;
        poison.failures = BN64_POST_UNWRITTEN;
        poison.segments = poison.expected_gu = poison.expected_dn = poison.magic = 0;
        bn64p_oracle_prepare(&prepare, 1);
        if (bn64p_test_check(!memcmp(&m.state, &expected, sizeof(expected)) &&
             !memcmp(&m.post_status, &poison, sizeof(poison)) &&
             bn64p_test_private(&f, &m, !expected.failures) &&
             bn64p_test_selection(&m, 0) && !m.raw64_counts[0] && !m.raw64_counts[1] &&
             m.sticky_failure == (expected.failures ? 1u : 0u), f.name, "prepare outputs")) return 1;
        if (!expected.failures) {
            Bn64PostSelectArgs post = bn64p_test_post_args(&f, &m, prepare.epoch);
            const unsigned char *guards[4] = {f.guards[0], f.guards[1], f.guards[2], f.guards[3]};
            Bn64ValidationResult before = m.state;
            Bn64ValidationResult legacy = bn64_oracle_post_value(f.counts,
                (int32_t)before.expected_gu, (int32_t)before.expected_dn, guards, post.epoch);
            /* CPU model only: original native64 execution is root-owned. */
            memcpy(m.raw64_counts, f.counts, sizeof(m.raw64_counts));
            bn64p_oracle_post(&post, 1);
            if (bn64p_test_check(bn64p_test_post_record(&m, &before, post.epoch,
                legacy.failures, 1, 1) && m.sticky_failure == (legacy.failures ? 1u : 0u),
                f.name, "post record/selection/consumption")) return 1;
        }
    }
    /* Reuse without per-transaction host poison; terminal prefix/tails included. */
    bn64_fixture_init(F_IGNORED_TAILS, &f);
    bn64p_test_new_allocation(&m);
    for (uint64_t epoch = 1; epoch <= 2; ++epoch) {
        Bn64Prepare64Args prepare = bn64p_test_prepare_args(&f, &m, epoch);
        Bn64PostSelectArgs post = bn64p_test_post_args(&f, &m, epoch);
        Bn64ValidationResult before;
        bn64p_oracle_prepare(&prepare, 1);
        if (bn64p_test_check(!m.state.failures && bn64p_test_private(&f, &m, 1),
                            "valid-reuse", "private inputs")) return 1;
        memcpy(m.raw64_counts, f.counts, sizeof(m.raw64_counts));
        before = m.state;
        bn64p_oracle_post(&post, 1);
        if (bn64p_test_check(bn64p_test_post_record(&m, &before, epoch, 0, 1, 1) &&
                            !m.sticky_failure, "valid-reuse", "fresh accepted post")) return 1;
    }
    {
        Bn64ValidationResult before = m.state;
        Bn64PostSelectArgs post = bn64p_test_post_args(&f, &m, 2);
        bn64p_oracle_post(&post, 1);
        if (bn64p_test_check(bn64p_test_post_record(&m, &before, 2, BN64_BAD_STAGE, 1, 1) &&
                            m.sticky_failure == 1, "duplicate-post", "stage consumed")) return 1;
    }
    /* Individually isolate freshness, expected-value coherence and overflow. */
    for (int which = 0; which < 10; ++which) {
        Bn64Prepare64Args prepare;
        Bn64PostSelectArgs post;
        Bn64ValidationResult before;
        uint32_t mask = 0;
        int coherent = 1;
        bn64_fixture_init(F_SPARSE_BOUNDARIES, &f);
        bn64p_test_new_allocation(&m);
        prepare = bn64p_test_prepare_args(&f, &m, 17);
        post = bn64p_test_post_args(&f, &m, 17);
        bn64p_oracle_prepare(&prepare, 1);
        memcpy(m.raw64_counts, f.counts, sizeof(m.raw64_counts));
        switch (which) {
        case 0: m.state.epoch = 16; mask = BN64_BAD_EPOCH; break;
        case 1: m.state.stage = BN64_STAGE_POISON; mask = BN64_BAD_STAGE; break;
        case 2: m.state.stage = BN64_STAGE_POST_ITEMS; mask = BN64_BAD_STAGE; break;
        case 3: m.state.magic = 0; mask = BN64_BAD_MAGIC; break;
        case 4: m.state.failures = BN64_BAD_PREFIX;
                mask = BN64_BAD_PREFIX | BN64_BAD_FIRST_STAGE; break;
        case 5: ++m.state.expected_gu; mask = BN64_BAD_EXPECTED; coherent = 0; break;
        case 6: ++m.state.expected_dn; mask = BN64_BAD_EXPECTED; coherent = 0; break;
        case 7: m.state.segments = m.state.expected_gu = m.state.expected_dn = 0;
                mask = BN64_BAD_EXPECTED | BN64_BAD_GU_COUNT | BN64_BAD_DN_COUNT;
                coherent = 0; break;
        case 8: m.state.segments = UINT32_MAX;
                mask = BN64_BAD_EXPECTED | BN64_BAD_GU_COUNT | BN64_BAD_DN_COUNT;
                coherent = 0; break;
        case 9: m.sticky_failure = UINT32_C(0x80000000); mask = BN64_BAD_STICKY; break;
        }
        before = m.state;
        bn64p_oracle_post(&post, 1);
        if (bn64p_test_check(bn64p_test_post_record(&m, &before, 17, mask, coherent, 1) &&
                             m.sticky_failure != 0, "post-protocol", "exact failure mask")) return 1;
    }
    /* Freshness/sticky failures must not short-circuit either count or any guard. */
    {
        Bn64Prepare64Args prepare;
        Bn64PostSelectArgs post;
        Bn64ValidationResult before;
        uint32_t mask = BN64_BAD_EPOCH | BN64_BAD_STICKY | BN64_BAD_GU_COUNT |
            BN64_BAD_DN_COUNT | BN64_BAD_GU_LEAD | BN64_BAD_GU_TRAIL |
            BN64_BAD_DN_LEAD | BN64_BAD_DN_TRAIL;
        bn64_fixture_init(F_ALL_GUARDS, &f);
        bn64p_test_new_allocation(&m);
        prepare = bn64p_test_prepare_args(&f, &m, 3);
        post = bn64p_test_post_args(&f, &m, 4);
        bn64p_oracle_prepare(&prepare, 1);
        m.raw64_counts[0] = -1; m.raw64_counts[1] = INT_MAX;
        m.sticky_failure = 1;
        before = m.state;
        bn64p_oracle_post(&post, 1);
        if (bn64p_test_check(bn64p_test_post_record(&m, &before, 4, mask, 1, 1),
                            "combined-post-rejection", "all checks retained")) return 1;
    }
    /* Failure is sticky across later valid input; recovery needs new allocation. */
    {
        Bn64Prepare64Args prepare;
        Bn64PostSelectArgs post;
        Bn64ValidationResult before;
        bn64_fixture_init(F_TOTAL_LOW, &f);
        bn64p_test_new_allocation(&m);
        prepare = bn64p_test_prepare_args(&f, &m, 5);
        bn64p_oracle_prepare(&prepare, 1);
        before = m.state;
        post = bn64p_test_post_args(&f, &m, 5);
        bn64p_oracle_post(&post, 1);
        if (bn64p_test_check(bn64p_test_post_record(&m, &before, 5,
            BN64_BAD_TOTAL | BN64_BAD_FIRST_STAGE | BN64_BAD_STICKY |
            BN64_BAD_EXPECTED | BN64_BAD_GU_COUNT | BN64_BAD_DN_COUNT, 0, 1),
            "histogram-post-rejection", "safe empty counts fallback")) return 1;
        bn64_fixture_init(F_SPARSE_BOUNDARIES, &f);
        prepare = bn64p_test_prepare_args(&f, &m, 6);
        bn64p_oracle_prepare(&prepare, 1);
        if (bn64p_test_check(m.state.failures == BN64_BAD_STICKY &&
            !m.state.expected_gu && !m.state.expected_dn && m.sticky_failure == 1 &&
            bn64p_test_private(&f, &m, 0), "sticky-valid-input", "safe empty persistence")) return 1;
        /* Invalid histogram predicates still run while sticky is already set. */
        f.raw[513] = BN64_ROUTED_ROWS - 1;
        bn64p_oracle_prepare(&prepare, 1);
        if (bn64p_test_check(m.state.failures == (BN64_BAD_TOTAL | BN64_BAD_STICKY),
            "sticky-invalid-input", "histogram still checked")) return 1;
        bn64_fixture_init(F_SPARSE_BOUNDARIES, &f);
        bn64p_test_new_allocation(&m);
        prepare = bn64p_test_prepare_args(&f, &m, 7);
        bn64p_oracle_prepare(&prepare, 1);
        if (bn64p_test_check(!m.state.failures && !m.sticky_failure &&
            bn64p_test_private(&f, &m, 1), "fresh-allocation-recovery", "accepted")) return 1;
    }
    /* Binding and wrong geometry are isolated custom-kernel tests only. */
    for (int which = 0; which < 4; ++which) {
        Bn64Prepare64Args prepare;
        bn64_fixture_init(F_SPARSE_BOUNDARIES, &f);
        bn64p_test_new_allocation(&m);
        prepare = bn64p_test_prepare_args(&f, &m, 8);
        if (which == 0) prepare.raw = NULL;
        if (which == 1) prepare.ids = NULL;
        if (which == 2) prepare.prefix = NULL;
        bn64p_oracle_prepare(&prepare, which != 3);
        if (bn64p_test_check(m.state.failures == (which == 3 ? BN64_BAD_SHAPE : BN64_BAD_BINDING) &&
             m.sticky_failure == 1 && bn64p_test_private(&f, &m, 0),
             "isolated-prepare-binding-shape", "safe empty")) return 1;
    }
    for (int which = 0; which < 6; ++which) {
        Bn64Prepare64Args prepare;
        Bn64PostSelectArgs post;
        Bn64ValidationResult before;
        bn64_fixture_init(F_SPARSE_BOUNDARIES, &f);
        bn64p_test_new_allocation(&m);
        prepare = bn64p_test_prepare_args(&f, &m, 9);
        post = bn64p_test_post_args(&f, &m, 9);
        bn64p_oracle_prepare(&prepare, 1);
        memcpy(m.raw64_counts, f.counts, sizeof(m.raw64_counts));
        if (which == 0) post.raw64_counts = NULL;
        if (which == 1) post.gu_lead = NULL;
        if (which == 2) post.gu_trail = NULL;
        if (which == 3) post.dn_lead = NULL;
        if (which == 4) post.dn_trail = NULL;
        before = m.state;
        bn64p_oracle_post(&post, which != 5);
        if (bn64p_test_check(bn64p_test_post_record(&m, &before, 9,
            which == 5 ? BN64_BAD_SHAPE : BN64_BAD_BINDING, which != 5, which != 5) &&
            m.sticky_failure == 1, "isolated-post-binding-shape", "fallback/consumption")) return 1;
    }
    return 0;
}

#ifdef __cplusplus
}
#endif
#ifndef BN64_PREDICATION_ORACLE_LIBRARY
int main(void) {
    int result = bn64p_oracle_selftest();
    if (!result) printf("BN64 predication oracle: %d legacy fixtures and protocol fixtures passed\n",
                        BN64_FIXTURE_COUNT);
    return result;
}
#endif
