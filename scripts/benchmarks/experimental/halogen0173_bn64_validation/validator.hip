/* Source-only fixed-shape native64 validation aggregation.
 * Compile for device only. This file has no host launches or initialization.
 * Define BN64_VALIDATION_ABI_ONLY to include the C-compatible ABI without HIP.
 * All device spans and the 32-byte output must be owned, readable, and live.
 * The two host decision waits are mandatory; this is not predicated compute. */
#ifndef BN64_VALIDATION_ABI_H
#define BN64_VALIDATION_ABI_H
#include <stdint.h>
#include <stddef.h>

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
    uint64_t epoch;          /* offset0: exact caller-owned transaction cookie */
    uint32_t stage;          /* offset8: 1 histogram, 2 post-items */
    uint32_t failures;       /* offset12: zero alone is not sufficient to accept */
    uint32_t segments;       /* offset16: diagnostic sanitized sum on hist failure */
    uint32_t expected_gu;    /* offset20: zero for a failed histogram */
    uint32_t expected_dn;    /* offset24: zero for a failed histogram */
    uint32_t magic;          /* offset28: BN64_RESULT_MAGIC */
} Bn64ValidationResult;

#if defined(__cplusplus)
static_assert(sizeof(Bn64ValidationResult) == 32, "validation result ABI");
static_assert(offsetof(Bn64ValidationResult, magic) == 28, "result magic offset");
#else
_Static_assert(sizeof(Bn64ValidationResult) == 32, "validation result ABI");
_Static_assert(offsetof(Bn64ValidationResult, magic) == 28, "result magic offset");
#endif
#endif

#ifndef BN64_VALIDATION_ABI_ONLY
#include <hip/hip_runtime.h>

__device__ static void bn64_publish(Bn64ValidationResult *out, uint64_t epoch,
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

__device__ static bool bn64_geometry_valid(void) {
    return gridDim.x == 1 && gridDim.y == 1 && gridDim.z == 1 &&
           blockDim.x == BN64_THREADS && blockDim.y == 1 && blockDim.z == 1;
}

/* Kernarg order: const int32_t* raw, const int32_t* ids,
 * const int32_t* prefix, uint64_t epoch, Bn64ValidationResult* out.
 * Fixed launch: grid(1,1,1), block(256,1,1), dynamic shared0, streamNULL.
 * Reads raw[514], ids[0..active-1], prefix[0..active], output[32]. */
extern "C" __global__ __launch_bounds__(BN64_THREADS)
void bn64_validate_histogram(const int32_t *raw, const int32_t *ids,
                             const int32_t *prefix, uint64_t epoch,
                             Bn64ValidationResult *out) {
    if (!bn64_geometry_valid()) {
        if (!blockIdx.x && !blockIdx.y && !blockIdx.z &&
            !threadIdx.x && !threadIdx.y && !threadIdx.z)
            bn64_publish(out, epoch, BN64_STAGE_HISTOGRAM, BN64_BAD_SHAPE, 0, 0, 0);
        return;
    }
    const unsigned tid = threadIdx.x;
    if (!raw || !ids || !prefix) {
        if (!tid) bn64_publish(out, epoch, BN64_STAGE_HISTOGRAM, BN64_BAD_BINDING, 0, 0, 0);
        return;
    }
    __shared__ uint64_t sums[BN64_EXPERTS];
    __shared__ uint32_t positives[BN64_EXPERTS];
    __shared__ uint64_t segment_reduction[BN64_THREADS];
    __shared__ uint32_t failure_reduction[BN64_THREADS];
    __shared__ int32_t active;
    __shared__ int32_t total;
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
        else
            rows = (uint32_t)source_rows;
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
    /* Inclusive parallel scans for row prefixes and compact active rank.
     * Every pre-write read completes before any thread overwrites a level. */
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
            if (!active_valid || index >= (uint32_t)active)
                failure |= BN64_BAD_INDEX;
            else {
                if (ids[index] != (int32_t)e) failure |= BN64_BAD_ID;
                uint64_t exclusive = sums[e] - local_rows[i];
                if ((int64_t)prefix[index] != (int64_t)exclusive)
                    failure |= BN64_BAD_PREFIX;
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
        bn64_publish(out, epoch, BN64_STAGE_HISTOGRAM, failure, (uint32_t)segments,
                     failure ? 0 : (uint32_t)(5 * segments),
                     failure ? 0 : (uint32_t)(10 * segments));
    }
}

/* Kernarg order: const int32_t* counts, int32_t expected_gu,
 * int32_t expected_dn, const uint8_t* gu_lead, const uint8_t* gu_trail,
 * const uint8_t* dn_lead, const uint8_t* dn_trail, uint64_t epoch,
 * Bn64ValidationResult* out.
 * Fixed launch: grid(1,1,1), block(256,1,1), dynamic shared0, streamNULL.
 * Each guard is exactly4096 readable bytes. No item payload is read. */
extern "C" __global__ __launch_bounds__(BN64_THREADS)
void bn64_validate_post(const int32_t *counts, int32_t expected_gu,
                        int32_t expected_dn, const unsigned char *gu_lead,
                        const unsigned char *gu_trail, const unsigned char *dn_lead,
                        const unsigned char *dn_trail, uint64_t epoch,
                        Bn64ValidationResult *out) {
    if (!bn64_geometry_valid()) {
        if (!blockIdx.x && !blockIdx.y && !blockIdx.z &&
            !threadIdx.x && !threadIdx.y && !threadIdx.z)
            bn64_publish(out, epoch, BN64_STAGE_POST_ITEMS, BN64_BAD_SHAPE, 0, 0, 0);
        return;
    }
    const unsigned tid = threadIdx.x;
    __shared__ uint32_t failure_reduction[BN64_THREADS];
    uint32_t failure = 0;
    const bool expected_valid = expected_gu >= 5 && expected_gu <= 5 * BN64_CAPACITY &&
        expected_gu % 5 == 0 && (int64_t)expected_dn == 2 * (int64_t)expected_gu;
    if (!tid) {
        if (!expected_valid) failure |= BN64_BAD_EXPECTED;
        if (!counts) failure |= BN64_BAD_BINDING;
        else {
            if (counts[0] != expected_gu) failure |= BN64_BAD_GU_COUNT;
            if (counts[1] != expected_dn) failure |= BN64_BAD_DN_COUNT;
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
    if (!tid) bn64_publish(out, epoch, BN64_STAGE_POST_ITEMS, failure_reduction[0],
                          expected_valid ? (uint32_t)(expected_gu / 5) : 0,
                          expected_valid ? (uint32_t)expected_gu : 0,
                          expected_valid ? (uint32_t)expected_dn : 0);
}
#endif
