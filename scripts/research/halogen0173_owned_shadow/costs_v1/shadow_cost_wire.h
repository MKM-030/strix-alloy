#pragma once
#include "shadow_wire.h"

namespace halogen0173::shadow {
enum CostFlag : std::uint32_t {
    CostClockValid=1u<<0, CostClockReadFailed=1u<<1,
    CostClockInvalidSample=1u<<2, CostClockReversed=1u<<3
};
struct CostStamp {
    std::uint64_t raw_ns{};
    std::uint32_t flags{};
    std::int32_t error{};
};
// Independent little-endian sidecar. The existing Header/Event wire stays v1.
#pragma pack(push,1)
struct CostHeader {
    std::array<char,8> magic{'H','0','1','7','3','S','C','1'};
    std::uint32_t version=1, record_bytes=96;
    std::array<char,64> runtime_sha256{};
    std::array<std::uint8_t,16> session_nonce{};
    // Private schema IDs: 1 = Linux CLOCK_MONOTONIC_RAW, 1 = nanoseconds.
    std::uint32_t clock=1, units=1, flags=0, reserved=0;
    std::array<std::uint8_t,16> tail_reserved{};
};
struct CostEvent {
    Kind kind{};
    std::uint32_t flags{};
    std::uint64_t sequence{}, owner_birth{}, slot_cookie{}, slot_epoch{}, round{}, wire_request_id{};
    std::uint64_t raw_ns{}, dropped_cumulative{};
    Source source{};
    std::uint32_t native_flags{};
    std::int32_t error{};
    std::uint32_t reserved{};
    std::uint64_t tail_reserved{};
};
#pragma pack(pop)
static_assert(sizeof(CostHeader)==128 && sizeof(CostEvent)==96);
static_assert(offsetof(CostEvent,sequence)==8 && offsetof(CostEvent,raw_ns)==56);
static_assert(offsetof(CostEvent,source)==72 && offsetof(CostEvent,error)==80);
} // namespace halogen0173::shadow

// Separate clock boundary lets CPU fixtures inject failures with GNU --wrap.
// Production always links the real implementation; no hot-path test switch.
extern "C" halogen0173::shadow::CostStamp hgn_shadow_cost_stamp() noexcept;
