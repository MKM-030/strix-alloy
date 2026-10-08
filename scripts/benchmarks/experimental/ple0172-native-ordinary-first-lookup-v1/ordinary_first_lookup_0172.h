// Source-only synchronous bridge for the pinned ordinary PLE lookup frame.
// Root owns binary attachment, object lifetime, failure routing and H2D admission.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#define PLE0172_NOEXCEPT noexcept
#else
#define PLE0172_NOEXCEPT
#endif

enum Ple0172OrdinaryResult {
    PLE0172_ORDINARY_STOCK = 0,    // No output byte written; replay stock instructions.
    PLE0172_ORDINARY_COMPLETE = 1, // All rows complete; owner may take original H2D.
    PLE0172_ORDINARY_ABORT = 2     // Never take H2D or restart stock gather.
};
enum Ple0172OrdinaryQualification {
    PLE0172_ENGINE_AND_FRAME_PINNED = 1u << 0,
    PLE0172_GPU_IDS_DOWNLOAD_COMPLETE = 1u << 1,
    PLE0172_NATIVE_MODEL_AND_FRAME_HELD = 1u << 2,
    PLE0172_SELECTED_LEGACY_METADATA_PROVEN = 1u << 3,
    PLE0172_MAPPING_HELD_THROUGH_COPY = 1u << 4,
    PLE0172_RAW_HELD_THROUGH_NATIVE_H2D = 1u << 5,
    PLE0172_NATIVE_CALLBACK_ABI_PROVEN = 1u << 6,
    PLE0172_STOP_BRIDGE_PROVEN = 1u << 7,
    PLE0172_ALL_QUALIFIED = (1u << 8) - 1
};
enum Ple0172OrdinaryMapperSelection {
    PLE0172_MAPPER_UNKNOWN = 0,
    PLE0172_MAPPER_DIRECT = 1
};
// Every pointer is borrowed from the exact current native owner. The owner keeps
// this contract, model (>=0x7c8 bytes), frame (>=0x218 bytes), IDs, mapper (>=16
// bytes), mapping and raw output immutable/live during this synchronous call.
// Callback invocations cannot reenter lookup or retire/change those objects.
// Raw/H2D qualification is for this ordinary frame and its existing downstream
// H2D only; it does not assert a universal allocation/free/error lifetime proof.
// Metadata is from the actual selected native query, not model-name inference.
typedef struct Ple0172OrdinaryContract {
    uint32_t abi_version;          // 1
    uint32_t struct_bytes;         // sizeof(Ple0172OrdinaryContract)
    uint32_t enable_page_order;    // 1, additionally exact environment value "1"
    uint32_t qualification_mask;   // PLE0172_ALL_QUALIFIED
    const void* native_model;      // Identity must match first ABI argument.
    const void* selected_mapper;
    const void* metadata_table;
    uint64_t metadata_rows;
    uint64_t metadata_extent;      // align_up(rows*160,64)+4 for dtype10.
    const void* mapping_base;
    uint64_t mapping_bytes;
    int32_t metadata_dtype;        // 10
    uint32_t mapper_selection;     // DIRECT only; default/override stays stock.
    void* stop_cookie;
    int (*stop_requested)(void* cookie) PLE0172_NOEXCEPT; // nonzero aborts.
} Ple0172OrdinaryContract;

// At RVA0x17ec18c: model=r12, frame_rsp=the unmodified native rsp,
// callback_enabled=the original r15b. No hook is installed by this library.
// Default-off: null/unqualified contract or unset/nonexact environment returns
// STOCK without native frame/model reads or output writes.
int ple0172_ordinary_first_lookup(void* native_model, const void* native_frame_rsp,
    const Ple0172OrdinaryContract* contract, uint32_t native_callback_enabled) PLE0172_NOEXCEPT;

#ifdef __cplusplus
}
#endif
#undef PLE0172_NOEXCEPT
