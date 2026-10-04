#pragma once
#include <stdint.h>

#if defined(_WIN32) && defined(HALOGEN_DD_OWNED_FC_BUILD)
#define HALOGEN_DD_OWNED_FC_API __declspec(dllexport)
#else
#define HALOGEN_DD_OWNED_FC_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Standalone original-geometry FC admission, not a model/acceptance benchmark. */
typedef struct HalogenDdOwnedFcReceipt {
    uint32_t schema, size, stage, fc_index;
    uint32_t calls_completed, output_valid, logical_k, logical_n;
    uint32_t kernel_k, kernel_n;
    uint64_t packed_bytes, input_bo_bytes, output_bo_bytes;
    int64_t qpc_frequency, qpc_start, qpc_end;
} HalogenDdOwnedFcReceipt;

/* fc_index 0 = FC1 (2560,1280); 1 = FC2 (640,2560). */
HALOGEN_DD_OWNED_FC_API int halogen_dd_owned_fc_create(uint32_t fc_index, const uint8_t *packed,
    uint64_t packed_bytes, void **handle, HalogenDdOwnedFcReceipt *receipt,
    char *error, uint32_t error_capacity);
HALOGEN_DD_OWNED_FC_API int halogen_dd_owned_fc_run(void *handle, const uint16_t *input,
    uint32_t input_elements, uint16_t *output, uint32_t output_elements,
    HalogenDdOwnedFcReceipt *receipt, char *error, uint32_t error_capacity);
HALOGEN_DD_OWNED_FC_API void halogen_dd_owned_fc_destroy(void *handle);

#ifdef __cplusplus
}
#endif
