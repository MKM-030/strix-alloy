#pragma once

#include "seam_contract.h"
#include <span>

namespace halogen_nohit::capture {

inline constexpr std::uint64_t kContextCapacity = 262144;
inline constexpr std::size_t kRequestBytes = 0x1f8;
inline constexpr std::size_t kModelBytes = 0x902;
inline constexpr std::size_t kRecordBytes = 0x308;
inline constexpr std::size_t kOuterBytes = 0x180;

// Owned byte copies tagged with their observed native origins. Origin equality
// checks layout consistency only; it cannot establish provenance or lifetime.
struct ObjectCopy {
    std::uint64_t native_origin{};
    std::span<const std::uint8_t> bytes{};
};

struct NoHitCopies {
    ObjectCopy request{}, model{}, record{}, outer{};
    std::array<std::uint64_t, 16> gpr{};
    // An independently captured suffix of the actual vector, not a prompt-text
    // reconstruction. Full-prefix hashing/copy continuity is outside this helper.
    std::uint64_t suffix_native_origin{};
    std::span<const std::int32_t> suffix{};
    const TokenDefinitions* tokens{};
};

// Observation facts only. No ownership/epoch/authentication/qualification flag
// and no handoff method is available here; a native adapter supplies those later.
struct NoHitFacts {
    std::uint64_t prefix_length{}, window_origin{}, target_position{};
    std::uint32_t window_count{};
    std::array<std::int32_t, kMaxWindowTokens> window_ids{};
    std::int32_t current_id{}, slot{}, cached_opening_id{}, native_allowance{};
    bool positive_pld_policy{}, no_sampler{}, no_suppression{}, positive_width{};
    bool sufficient_context{}, no_constraints{}, opening_gate_eligible{};
};

enum class DecodeResult : std::uint8_t {
    Captured, MissingCopy, FrameMismatch, RecordMismatch, PrefillIncomplete,
    VectorInvalid, TokenInvalid, PhaseReentry, ArithmeticInvalid, AllowanceMismatch
};

// All spans must be complete immutable owned copies held for this call. Work is
// bounded to fixed fields and <=512 IDs regardless of complete prompt length.
// On failure, out is unchanged. No native pointer is dereferenced or modified.
DecodeResult decode_nohit(const NoHitCopies& copies, NoHitFacts& out) noexcept;

} // namespace halogen_nohit::capture
