// Throwaway CPU arithmetic component screen. No engine/model/table/device access.
#pragma once
#include "archived_scalar_ids_0172.h"
#include <cstddef>

namespace ple_screen {
using ple_native_0172::Constants;
inline constexpr std::array<std::int64_t, 16> admitted_moduli{
    20000003,20000023,20000033,20000047,20000059,20000063,20000069,20000077,
    20000081,20000093,20000107,20000147,20000153,20000159,20000161,20000171};

// Separate translation unit, no LTO, noinline: preserve runtime IDIV in baseline
// and repeated observable output stores in the timed caller.
bool admit(const Constants& constants) noexcept;
bool dynamic_window(const std::int32_t* tokens, std::size_t count,
                    std::array<std::int64_t,2> history, const Constants& constants,
                    std::int64_t* destination) noexcept;
bool literal_window(const std::int32_t* tokens, std::size_t count,
                    std::array<std::int64_t,2> history, const Constants& constants,
                    std::int64_t* destination) noexcept;
std::int64_t dynamic_remainder(std::int64_t numerator, std::int64_t divisor) noexcept;
std::int64_t literal_remainder(std::size_t head, std::int64_t numerator) noexcept;
}
