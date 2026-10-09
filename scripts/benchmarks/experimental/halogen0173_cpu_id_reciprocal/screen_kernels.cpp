#include "screen_kernels.h"
#include <utility>

namespace ple_screen {
using ple_native_0172::bits;
using ple_native_0172::signed_bits;

[[clang::noinline]] bool admit(const Constants& constants) noexcept {
    for (std::size_t head=0;head<16;++head)
        if (constants.moduli[head]!=admitted_moduli[head]) return false;
    return true;
}

template<bool Literal,std::size_t Head>
inline void store_head(std::uint64_t hash2, std::uint64_t hash3,
                       const Constants& constants, std::int64_t* destination) noexcept {
    const auto numerator=signed_bits(Head<8 ? hash2 : hash3);
    // Signed % is exact truncation-toward-zero remainder. The literal path lets
    // clang lower it to integer multiply/shift; no abs or unsigned modulus.
    const auto remainder=Literal ? numerator%admitted_moduli[Head]
                                 : numerator%constants.moduli[Head];
    destination[Head]=signed_bits(bits(remainder)+bits(constants.offsets[Head]));
}

template<bool Literal,std::size_t... Heads>
inline void store_heads(std::uint64_t hash2, std::uint64_t hash3,
                        const Constants& constants,std::int64_t* destination,
                        std::index_sequence<Heads...>) noexcept {
    (store_head<Literal,Heads>(hash2,hash3,constants,destination),...);
}

template<bool Literal>
inline void full_window(const std::int32_t* tokens,std::size_t count,
                        std::array<std::int64_t,2> history,const Constants& constants,
                        std::int64_t* destination) noexcept {
    for (std::size_t token=0;token<count;++token) {
        const auto previous=token ? std::int64_t(tokens[token-1]) : history[1];
        auto previous2=token>=2 ? std::int64_t(tokens[token-2]) : history[token];
        if (previous==ple_native_0172::eos) previous2=previous;
        const auto current_product=bits(std::int64_t(tokens[token]))*bits(constants.multipliers[0]);
        const auto hash2=bits(previous)*bits(constants.multipliers[1])^current_product;
        const auto hash3=bits(previous2)*bits(constants.multipliers[2])^hash2;
        store_heads<Literal>(hash2,hash3,constants,destination+token*16,
                             std::make_index_sequence<16>{});
    }
}

[[clang::noinline]] bool dynamic_window(const std::int32_t* tokens,std::size_t count,
                                      std::array<std::int64_t,2> history,const Constants& constants,
                                      std::int64_t* destination) noexcept {
    // Harness validates supported positive divisors before entering this leaf.
    // Original native IDIV does not carry sixteen per-token exceptional checks.
    full_window<false>(tokens,count,history,constants,destination);
    return true;
}

[[clang::noinline]] bool literal_window(const std::int32_t* tokens,std::size_t count,
                                      std::array<std::int64_t,2> history,const Constants& constants,
                                      std::int64_t* destination) noexcept {
    // One actual 16-word model admission per full window is INSIDE candidate
    // timing. Mismatch returns before any ID write; integration must use stock.
    if (!admit(constants)) return false;
    full_window<true>(tokens,count,history,constants,destination);
    return true;
}

[[clang::noinline]] std::int64_t dynamic_remainder(std::int64_t numerator,std::int64_t divisor) noexcept {
    return numerator%divisor;
}
[[clang::noinline]] std::int64_t literal_remainder(std::size_t head,std::int64_t numerator) noexcept {
    switch (head) {
#define PLE_CASE(H) case H: return numerator%admitted_moduli[H]
        PLE_CASE(0); PLE_CASE(1); PLE_CASE(2); PLE_CASE(3);
        PLE_CASE(4); PLE_CASE(5); PLE_CASE(6); PLE_CASE(7);
        PLE_CASE(8); PLE_CASE(9); PLE_CASE(10); PLE_CASE(11);
        PLE_CASE(12); PLE_CASE(13); PLE_CASE(14); PLE_CASE(15);
#undef PLE_CASE
        default: return 0;
    }
}
}
