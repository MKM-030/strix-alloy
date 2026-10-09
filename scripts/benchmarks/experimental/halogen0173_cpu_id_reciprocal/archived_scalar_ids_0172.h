// Private source transposition of retained worker 0x1865860..0x1865aa4.
// Constants and tokens are borrowed from the same engine-owned native context.
// No device arithmetic, payload cache, token remapping or carry mutation.
#pragma once
#include <array>
#include <bit>
#include <cstdint>
#include <limits>
#include <span>
namespace ple_native_0172 {
constexpr std::int64_t eos=0x3c8ec;
struct Constants {
    std::array<std::int64_t, 3> multipliers{};
    std::array<std::int64_t, 16> moduli{}, offsets{};
};
inline std::int64_t signed_bits(std::uint64_t value) noexcept { return std::bit_cast<std::int64_t>(value); }
inline std::uint64_t bits(std::int64_t value) noexcept { return std::bit_cast<std::uint64_t>(value); }
inline bool valid_divisors(const Constants& constants) noexcept {
    for (const auto modulus:constants.moduli) if (!modulus) return false;
    return true;
}
inline bool scalar_ids(std::span<const std::int32_t> tokens, std::array<std::int64_t, 2> history,
                       const Constants& constants, std::size_t token,
                       std::span<std::int64_t, 16> destination) noexcept {
    if (token>=tokens.size()) return false;
    // 0x1865860..0x1865888; >=2 tail at 0x1865d50. Sign-extend int32.
    const auto previous=token ? std::int64_t(tokens[token-1]) : history[1];
    auto previous2=token>=2 ? std::int64_t(tokens[token-2]) : history[token];
    // 0x18658b0..0x18658b7: the preceding EOS replaces the older word.
    if (previous==eos) previous2=previous;
    const auto current_product=bits(std::int64_t(tokens[token]))*bits(constants.multipliers[0]);
    const auto hash2=bits(previous)*bits(constants.multipliers[1])^current_product;
    const auto hash3=bits(previous2)*bits(constants.multipliers[2])^hash2;
    for (std::size_t head=0; head<16; ++head) {
        const auto hash=signed_bits(head<8 ? hash2 : hash3);
        const auto modulus=constants.moduli[head];
        if (!modulus || (hash==std::numeric_limits<std::int64_t>::min() && modulus==-1)) return false;
        // C++ signed remainder truncates toward zero, matching CQO/IDIV.
        // ADD wraps in x86-64; use unsigned addition to avoid signed C++ UB.
        destination[head]=signed_bits(bits(hash%modulus)+bits(constants.offsets[head]));
    }
    return true;
}
}
