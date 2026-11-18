#ifndef HALOGEN_PREFLIGHT_PLAN_H
#define HALOGEN_PREFLIGHT_PLAN_H
#include <stddef.h>
#include <stdint.h>

/* Offsets are half-open intervals within the mapping. Success commits only this
 * phase's host demand. Failure leaves the output untouched and is terminal for
 * this adapter instance. Available only with HALOGEN_PREFLIGHT_V1=1. */
struct halogen_preflight_range_v1 { uint64_t begin, end; };
int halogen_hybrid_preflight_v1(
    uintptr_t mapping_base, size_t mapping_bytes,
    const struct halogen_preflight_range_v1 *ranges, size_t range_count,
    size_t aggregate_bytes, size_t *host_required_bytes);
#endif
