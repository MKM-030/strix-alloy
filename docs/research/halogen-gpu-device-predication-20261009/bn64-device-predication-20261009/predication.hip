/* Source-only, default-off native64 preparation and device count selection.
 * Define BN64_PREDICATION_ABI_ONLY for the C-compatible x64 launch ABI.
 * Native items/projection/fold kernels and their arithmetic are unchanged. */
#ifndef BN64_PREDICATION_ABI_H
#define BN64_PREDICATION_ABI_H
#include <stdint.h>
#include <stddef.h>

/* Share the archived validator's public types when both headers are included. */
#ifndef BN64_VALIDATION_ABI_H
#define BN64_VALIDATION_ABI_H
enum {
    BN64_EXPERTS = 512, BN64_ROUTED_ROWS = 81920, BN64_CAPACITY = 1792,
    BN64_GUARD_BYTES = 4096, BN64_THREADS = 256,
    BN64_GU_ITEMS_BYTES = 143360, BN64_DN_ITEMS_BYTES = 286720,
    BN64_STAGE_HISTOGRAM = 1, BN64_STAGE_POST_ITEMS = 2
};
#define BN64_RESULT_MAGIC UINT32_C(0x42363456)
enum Bn64ValidationFailure {
    BN64_BAD_BINDING         = UINT32_C(1) << 0,
    BN64_BAD_ACTIVE          = UINT32_C(1) << 1,
    BN64_BAD_TOTAL           = UINT32_C(1) << 2,
    BN64_BAD_ROWS            = UINT32_C(1) << 3,
    BN64_BAD_INDEX           = UINT32_C(1) << 4,
    BN64_BAD_ID              = UINT32_C(1) << 5,
    BN64_BAD_PREFIX          = UINT32_C(1) << 6,
    BN64_BAD_SUM_LIMIT       = UINT32_C(1) << 7,
    BN64_BAD_SUM             = UINT32_C(1) << 8,
    BN64_BAD_ACTIVE_COUNT    = UINT32_C(1) << 9,
    BN64_BAD_TERMINAL_PREFIX = UINT32_C(1) << 10,
    BN64_BAD_CAPACITY        = UINT32_C(1) << 11,
    BN64_BAD_GU_COUNT        = UINT32_C(1) << 12,
    BN64_BAD_DN_COUNT        = UINT32_C(1) << 13,
    BN64_BAD_GU_LEAD         = UINT32_C(1) << 14,
    BN64_BAD_GU_TRAIL        = UINT32_C(1) << 15,
    BN64_BAD_DN_LEAD         = UINT32_C(1) << 16,
    BN64_BAD_DN_TRAIL        = UINT32_C(1) << 17,
    BN64_BAD_EXPECTED        = UINT32_C(1) << 18,
    BN64_BAD_SHAPE           = UINT32_C(1) << 19
};
typedef struct Bn64ValidationResult {
    uint64_t epoch;
    uint32_t stage, failures, segments, expected_gu, expected_dn, magic;
} Bn64ValidationResult;
#endif
enum {
    BN64_STAGE_POISON = 0, BN64_STAGE_CONSUMED = 3,
    BN64_BAD_STICKY      = UINT32_C(1) << 20,
    BN64_BAD_EPOCH       = UINT32_C(1) << 21,
    BN64_BAD_STAGE       = UINT32_C(1) << 22,
    BN64_BAD_MAGIC       = UINT32_C(1) << 23,
    BN64_BAD_FIRST_STAGE = UINT32_C(1) << 24,
    BN64_POST_UNWRITTEN  = UINT32_C(1) << 25
};

typedef struct Bn64Prepare64Args {
    const int32_t *raw;
    const int32_t *ids;
    const int32_t *prefix;
    const int32_t *native128_counts;
    uint64_t epoch;
    int32_t *private_raw;
    int32_t *private_ids;
    int32_t *private_prefix;
    int32_t *raw64_counts;
    int32_t *selected128_counts;
    int32_t *selected64_counts;
    Bn64ValidationResult *state;
    Bn64ValidationResult *post_status;
    uint32_t *sticky_failure;
} Bn64Prepare64Args;

typedef struct Bn64PostSelectArgs {
    Bn64ValidationResult *state;
    uint64_t epoch;
    const int32_t *raw64_counts;
    const int32_t *native128_counts;
    const unsigned char *gu_lead;
    const unsigned char *gu_trail;
    const unsigned char *dn_lead;
    const unsigned char *dn_trail;
    int32_t *selected128_counts;
    int32_t *selected64_counts;
    Bn64ValidationResult *post_status;
    uint32_t *sticky_failure;
} Bn64PostSelectArgs;

#if defined(__cplusplus)
#define BN64P_ASSERT(x, message) static_assert((x), message)
#else
#define BN64P_ASSERT(x, message) _Static_assert((x), message)
#endif
BN64P_ASSERT(sizeof(void *) == 8, "predication launch ABI requires x64");
BN64P_ASSERT(sizeof(Bn64ValidationResult) == 32, "validation result ABI");
#define BN64P_OFFSET(type, field, value) BN64P_ASSERT(offsetof(type, field) == value, #field " offset")
BN64P_OFFSET(Bn64ValidationResult, epoch, 0);
BN64P_OFFSET(Bn64ValidationResult, stage, 8);
BN64P_OFFSET(Bn64ValidationResult, failures, 12);
BN64P_OFFSET(Bn64ValidationResult, segments, 16);
BN64P_OFFSET(Bn64ValidationResult, expected_gu, 20);
BN64P_OFFSET(Bn64ValidationResult, expected_dn, 24);
BN64P_OFFSET(Bn64ValidationResult, magic, 28);
BN64P_ASSERT(sizeof(Bn64Prepare64Args) == 112, "prepare kernarg ABI");
BN64P_OFFSET(Bn64Prepare64Args, raw, 0);
BN64P_OFFSET(Bn64Prepare64Args, ids, 8);
BN64P_OFFSET(Bn64Prepare64Args, prefix, 16);
BN64P_OFFSET(Bn64Prepare64Args, native128_counts, 24);
BN64P_OFFSET(Bn64Prepare64Args, epoch, 32);
BN64P_OFFSET(Bn64Prepare64Args, private_raw, 40);
BN64P_OFFSET(Bn64Prepare64Args, private_ids, 48);
BN64P_OFFSET(Bn64Prepare64Args, private_prefix, 56);
BN64P_OFFSET(Bn64Prepare64Args, raw64_counts, 64);
BN64P_OFFSET(Bn64Prepare64Args, selected128_counts, 72);
BN64P_OFFSET(Bn64Prepare64Args, selected64_counts, 80);
BN64P_OFFSET(Bn64Prepare64Args, state, 88);
BN64P_OFFSET(Bn64Prepare64Args, post_status, 96);
BN64P_OFFSET(Bn64Prepare64Args, sticky_failure, 104);
BN64P_ASSERT(sizeof(Bn64PostSelectArgs) == 96, "post kernarg ABI");
BN64P_OFFSET(Bn64PostSelectArgs, state, 0);
BN64P_OFFSET(Bn64PostSelectArgs, epoch, 8);
BN64P_OFFSET(Bn64PostSelectArgs, raw64_counts, 16);
BN64P_OFFSET(Bn64PostSelectArgs, native128_counts, 24);
BN64P_OFFSET(Bn64PostSelectArgs, gu_lead, 32);
BN64P_OFFSET(Bn64PostSelectArgs, gu_trail, 40);
BN64P_OFFSET(Bn64PostSelectArgs, dn_lead, 48);
BN64P_OFFSET(Bn64PostSelectArgs, dn_trail, 56);
BN64P_OFFSET(Bn64PostSelectArgs, selected128_counts, 64);
BN64P_OFFSET(Bn64PostSelectArgs, selected64_counts, 72);
BN64P_OFFSET(Bn64PostSelectArgs, post_status, 80);
BN64P_OFFSET(Bn64PostSelectArgs, sticky_failure, 88);
#undef BN64P_OFFSET
#undef BN64P_ASSERT
#endif

#if !defined(BN64_PREDICATION_ABI_ONLY) && !defined(BN64_VALIDATION_ABI_ONLY)
#include <hip/hip_runtime.h>

__device__ static bool bn64p_geometry_valid(void) {
    return gridDim.x == 1 && gridDim.y == 1 && gridDim.z == 1 &&
        blockDim.x == BN64_THREADS && blockDim.y == 1 && blockDim.z == 1;
}
__device__ static bool bn64p_origin(void) {
    return !blockIdx.x && !blockIdx.y && !blockIdx.z &&
        !threadIdx.x && !threadIdx.y && !threadIdx.z;
}
__device__ static void bn64p_publish(Bn64ValidationResult *out, uint64_t epoch,
                                    uint32_t stage, uint32_t failures,
                                    uint32_t segments, uint32_t gu, uint32_t dn) {
    out->epoch = epoch;
    out->stage = stage;
    out->failures = failures;
    out->segments = segments;
    out->expected_gu = gu;
    out->expected_dn = dn;
    out->magic = BN64_RESULT_MAGIC;
}
__device__ static void bn64p_poison_post(Bn64ValidationResult *out, uint64_t epoch) {
    out->epoch = epoch;
    out->stage = BN64_STAGE_POISON;
    out->failures = BN64_POST_UNWRITTEN;
    out->segments = out->expected_gu = out->expected_dn = out->magic = 0;
}
__device__ static void bn64p_default_counts(const int32_t *native128_counts,
                                           int32_t *selected128_counts,
                                           int32_t *selected64_counts) {
    selected128_counts[0] = native128_counts[0];
    selected128_counts[1] = native128_counts[1];
    selected64_counts[0] = selected64_counts[1] = 0;
}

/* Positional kernarg layout is exactly Bn64Prepare64Args, 14 args / 112 bytes.
 * Required launch grid(1,1,1), block(256,1,1), shared0, NULL stream.
 * All mutable/count/status pointers are host-owned, valid and nonaliasing.
 * Only original histogram input nulls have an isolated binding-reject path. */
extern "C" __global__ __launch_bounds__(BN64_THREADS)
void bn64_validate_histogram_prepare64(const int32_t *raw, const int32_t *ids,
    const int32_t *prefix, const int32_t *native128_counts, uint64_t epoch,
    int32_t *private_raw, int32_t *private_ids, int32_t *private_prefix,
    int32_t *raw64_counts, int32_t *selected128_counts, int32_t *selected64_counts,
    Bn64ValidationResult *state, Bn64ValidationResult *post_status,
    uint32_t *sticky_failure) {
    if (!bn64p_geometry_valid()) {
        /* Defensive serial origin fallback uses no block barriers. A launch
         * that never executes cannot publish or consume anything. */
        if (bn64p_origin()) {
            for (unsigned i = 0; i < BN64_EXPERTS + 2; ++i) private_raw[i] = 0;
            private_raw[BN64_EXPERTS + 1] = BN64_ROUTED_ROWS;
            for (unsigned i = 0; i < BN64_EXPERTS; ++i) private_ids[i] = 0;
            for (unsigned i = 0; i <= BN64_EXPERTS; ++i) private_prefix[i] = 0;
            raw64_counts[0] = raw64_counts[1] = 0;
            bn64p_default_counts(native128_counts, selected128_counts, selected64_counts);
            bn64p_poison_post(post_status, epoch);
            uint32_t failures = BN64_BAD_SHAPE;
            if (*sticky_failure) failures |= BN64_BAD_STICKY;
            atomicOr(sticky_failure, 1u);
            bn64p_publish(state, epoch, BN64_STAGE_HISTOGRAM, failures, 0, 0, 0);
        }
        return;
    }
    const unsigned tid = threadIdx.x;
    for (unsigned i = tid; i < BN64_EXPERTS + 2; i += BN64_THREADS) private_raw[i] = 0;
    for (unsigned i = tid; i < BN64_EXPERTS; i += BN64_THREADS) private_ids[i] = 0;
    for (unsigned i = tid; i <= BN64_EXPERTS; i += BN64_THREADS) private_prefix[i] = 0;
    if (!tid) {
        raw64_counts[0] = raw64_counts[1] = 0;
        bn64p_default_counts(native128_counts, selected128_counts, selected64_counts);
        bn64p_poison_post(post_status, epoch);
    }
    __syncthreads();
    /* The native empty item path still needs the unchanged routed-row total. */
    if (!tid) private_raw[BN64_EXPERTS + 1] = BN64_ROUTED_ROWS;
    __syncthreads();
    if (!raw || !ids || !prefix) {
        if (!tid) {
            uint32_t failures = BN64_BAD_BINDING;
            if (*sticky_failure) failures |= BN64_BAD_STICKY;
            atomicOr(sticky_failure, 1u);
            bn64p_publish(state, epoch, BN64_STAGE_HISTOGRAM, failures, 0, 0, 0);
        }
        return;
    }
    __shared__ uint64_t sums[BN64_EXPERTS];
    __shared__ uint32_t positives[BN64_EXPERTS];
    __shared__ uint64_t segment_reduction[BN64_THREADS];
    __shared__ uint32_t failure_reduction[BN64_THREADS];
    __shared__ int32_t active;
    __shared__ int32_t total;
    __shared__ uint32_t aggregate_failures;
    __shared__ uint32_t aggregate_segments;
    uint32_t failure = 0;
    uint64_t local_rows[2];
    uint64_t segments = 0;
    if (!tid) {
        active = raw[BN64_EXPERTS];
        total = raw[BN64_EXPERTS + 1];
    }
    for (unsigned i = 0; i < 2; ++i) {
        unsigned e = tid + i * BN64_THREADS;
        int32_t source_rows = raw[e];
        uint64_t rows = 0;
        if (source_rows < 0 || source_rows > BN64_ROUTED_ROWS)
            failure |= BN64_BAD_ROWS;
        else rows = (uint32_t)source_rows;
        local_rows[i] = rows;
        sums[e] = rows;
        positives[e] = rows != 0;
        segments += (rows + 63) / 64;
    }
    __syncthreads();
    const bool active_valid = active >= 1 && active <= BN64_EXPERTS;
    if (!tid) {
        if (!active_valid) failure |= BN64_BAD_ACTIVE;
        if (total != BN64_ROUTED_ROWS) failure |= BN64_BAD_TOTAL;
    }
    /* Archived inclusive row/compact-rank scans. Pre-write reads finish
     * before any thread overwrites each level. Sticky does not skip them. */
    for (unsigned offset = 1; offset < BN64_EXPERTS; offset <<= 1) {
        const unsigned e0 = tid, e1 = tid + BN64_THREADS;
        uint64_t s0 = sums[e0], s1 = sums[e1];
        uint32_t a0 = positives[e0], a1 = positives[e1];
        if (e0 >= offset) { s0 += sums[e0 - offset]; a0 += positives[e0 - offset]; }
        if (e1 >= offset) { s1 += sums[e1 - offset]; a1 += positives[e1 - offset]; }
        __syncthreads();
        sums[e0] = s0; sums[e1] = s1;
        positives[e0] = a0; positives[e1] = a1;
        __syncthreads();
    }
    for (unsigned i = 0; i < 2; ++i) {
        unsigned e = tid + i * BN64_THREADS;
        if (sums[e] > BN64_ROUTED_ROWS) failure |= BN64_BAD_SUM_LIMIT;
        if (local_rows[i]) {
            uint32_t index = positives[e] - 1;
            if (!active_valid || index >= (uint32_t)active) failure |= BN64_BAD_INDEX;
            else {
                if (ids[index] != (int32_t)e) failure |= BN64_BAD_ID;
                uint64_t exclusive = sums[e] - local_rows[i];
                if ((int64_t)prefix[index] != (int64_t)exclusive) failure |= BN64_BAD_PREFIX;
            }
        }
    }
    failure_reduction[tid] = failure;
    segment_reduction[tid] = segments;
    __syncthreads();
    for (unsigned stride = BN64_THREADS / 2; stride; stride >>= 1) {
        if (tid < stride) {
            failure_reduction[tid] |= failure_reduction[tid + stride];
            segment_reduction[tid] += segment_reduction[tid + stride];
        }
        __syncthreads();
    }
    if (!tid) {
        failure = failure_reduction[0];
        segments = segment_reduction[0];
        if (sums[BN64_EXPERTS - 1] != BN64_ROUTED_ROWS) failure |= BN64_BAD_SUM;
        if (!active_valid || positives[BN64_EXPERTS - 1] != (uint32_t)active)
            failure |= BN64_BAD_ACTIVE_COUNT;
        if (active_valid && prefix[active] != BN64_ROUTED_ROWS)
            failure |= BN64_BAD_TERMINAL_PREFIX;
        if (segments > BN64_CAPACITY) failure |= BN64_BAD_CAPACITY;
        if (*sticky_failure) failure |= BN64_BAD_STICKY;
        if (failure) atomicOr(sticky_failure, 1u);
        aggregate_failures = failure;
        aggregate_segments = (uint32_t)segments;
    }
    __syncthreads();
    if (!aggregate_failures) {
        for (unsigned i = tid; i < BN64_EXPERTS + 2; i += BN64_THREADS)
            private_raw[i] = raw[i];
        for (unsigned i = tid; i < (unsigned)active; i += BN64_THREADS)
            private_ids[i] = ids[i];
        /* Includes prefix[active], even active==512. Unused tails stay zero. */
        for (unsigned i = tid; i <= (unsigned)active; i += BN64_THREADS)
            private_prefix[i] = prefix[i];
    }
    __syncthreads();
    /* Publish only after all preparation writes complete. Stream order gives
     * the following unchanged items64 kernel its initialized private inputs. */
    if (!tid) bn64p_publish(state, epoch, BN64_STAGE_HISTOGRAM,
        aggregate_failures, aggregate_segments,
        aggregate_failures ? 0 : 5 * aggregate_segments,
        aggregate_failures ? 0 : 10 * aggregate_segments);
}

/* Positional kernarg layout is exactly Bn64PostSelectArgs, 12 args / 96 bytes.
 * Reads all four complete 4096-byte guards even for stale/sticky/failed state.
 * Required launch grid(1,1,1), block(256,1,1), shared0, NULL stream. */
extern "C" __global__ __launch_bounds__(BN64_THREADS)
void bn64_validate_post_select(Bn64ValidationResult *state, uint64_t epoch,
    const int32_t *raw64_counts, const int32_t *native128_counts,
    const unsigned char *gu_lead, const unsigned char *gu_trail,
    const unsigned char *dn_lead, const unsigned char *dn_trail,
    int32_t *selected128_counts, int32_t *selected64_counts,
    Bn64ValidationResult *post_status, uint32_t *sticky_failure) {
    if (!bn64p_geometry_valid()) {
        if (bn64p_origin()) {
            bn64p_default_counts(native128_counts, selected128_counts, selected64_counts);
            uint32_t failures = BN64_BAD_SHAPE;
            if (*sticky_failure) failures |= BN64_BAD_STICKY;
            atomicOr(sticky_failure, 1u);
            bn64p_publish(post_status, epoch, BN64_STAGE_POST_ITEMS, failures, 0, 0, 0);
        }
        return;
    }
    const unsigned tid = threadIdx.x;
    __shared__ Bn64ValidationResult input;
    __shared__ uint32_t failure_reduction[BN64_THREADS];
    if (!tid) {
        input = *state;
        bn64p_default_counts(native128_counts, selected128_counts, selected64_counts);
    }
    __syncthreads();
    const uint64_t expected_gu = UINT64_C(5) * input.segments;
    const uint64_t expected_dn = UINT64_C(10) * input.segments;
    const bool coherent_expected = input.segments >= 1 && input.segments <= BN64_CAPACITY &&
        input.expected_gu == expected_gu && input.expected_dn == expected_dn;
    uint32_t failure = 0;
    if (!tid) {
        if (*sticky_failure) failure |= BN64_BAD_STICKY;
        if (input.epoch != epoch) failure |= BN64_BAD_EPOCH;
        if (input.stage != BN64_STAGE_HISTOGRAM) failure |= BN64_BAD_STAGE;
        if (input.magic != BN64_RESULT_MAGIC) failure |= BN64_BAD_MAGIC;
        if (input.failures) failure |= input.failures | BN64_BAD_FIRST_STAGE;
        if (!coherent_expected) failure |= BN64_BAD_EXPECTED;
        if (!raw64_counts) failure |= BN64_BAD_BINDING;
        else {
            /* Maximum corrupt uint32 segment products still fit int64. */
            if ((int64_t)raw64_counts[0] != (int64_t)expected_gu) failure |= BN64_BAD_GU_COUNT;
            if ((int64_t)raw64_counts[1] != (int64_t)expected_dn) failure |= BN64_BAD_DN_COUNT;
        }
    }
    const unsigned char *guards[4] = {gu_lead, gu_trail, dn_lead, dn_trail};
    const uint32_t bits[4] = {BN64_BAD_GU_LEAD, BN64_BAD_GU_TRAIL,
                              BN64_BAD_DN_LEAD, BN64_BAD_DN_TRAIL};
    for (unsigned g = 0; g < 4; ++g) {
        if (!guards[g]) failure |= BN64_BAD_BINDING;
        else for (unsigned j = tid; j < BN64_GUARD_BYTES; j += BN64_THREADS)
            if (guards[g][j] != 0xa5) failure |= bits[g];
    }
    failure_reduction[tid] = failure;
    __syncthreads();
    for (unsigned stride = BN64_THREADS / 2; stride; stride >>= 1) {
        if (tid < stride) failure_reduction[tid] |= failure_reduction[tid + stride];
        __syncthreads();
    }
    if (!tid) {
        failure = failure_reduction[0];
        if (failure) atomicOr(sticky_failure, 1u);
        else {
            selected128_counts[0] = selected128_counts[1] = 0;
            selected64_counts[0] = raw64_counts[0];
            selected64_counts[1] = raw64_counts[1];
        }
        /* Every decision consumes the first-stage record. Preserve its other
         * fields, including failure diagnostics, for the retirement audit. */
        state->stage = BN64_STAGE_CONSUMED;
        bn64p_publish(post_status, epoch, BN64_STAGE_POST_ITEMS, failure,
            coherent_expected ? input.segments : 0,
            coherent_expected ? (uint32_t)expected_gu : 0,
            coherent_expected ? (uint32_t)expected_dn : 0);
    }
}
#endif
