#pragma once

// Pure CPU function. Inputs are copied committed IDs and immutable token metadata.
// No native callback, model, owner, lifetime, device, allocation, wait or OS code.
namespace causal_pld64 {
using i32 = __INT32_TYPE__;
using u32 = __UINT32_TYPE__;
using u8 = __UINT8_TYPE__;

struct Result {
    i32 ids[3];
    u32 longer_match;
    u32 match_length;
    u32 occurrence_index;
    u32 checked_positions;
};

inline bool allowed(i32 id, const u8* bitmap, u32 bit_count) noexcept {
    return id >= 0 && u32(id) < bit_count
        && (bitmap[u32(id) / 8] & u8(1u << (u32(id) % 8)));
}

// Exactly the frozen Python policy: actual stock width is always three.
// Caller owns valid arrays for the duration of this ordinary synchronous call.
// Invalid geometry returns false without touching output. There is no fallback
// mechanism beyond returning unchanged stock IDs for a valid nonmatching input.
inline bool propose(const i32* suffix, u32 n, const i32* stock,
                    const u8* bitmap, u32 bit_count, Result* output) noexcept {
    if (!suffix || !stock || !bitmap || !output || n > 64 || !bit_count)
        return false;
    Result r;
    r.ids[0] = stock[0]; r.ids[1] = stock[1]; r.ids[2] = stock[2];
    r.longer_match = 0; r.match_length = 0; r.occurrence_index = 0;
    r.checked_positions = 0;
    u32 best_match = 0, best_index = 0;
    if (n >= 6) {
        for (u32 j = 3; j <= n - 3; ++j) {
            ++r.checked_positions;
            if (suffix[j-3] != suffix[n-3] || suffix[j-2] != suffix[n-2]
                || suffix[j-1] != suffix[n-1] || suffix[j] != stock[0])
                continue;
            if (!allowed(suffix[j], bitmap, bit_count)
                || !allowed(suffix[j+1], bitmap, bit_count)
                || !allowed(suffix[j+2], bitmap, bit_count))
                continue;
            u32 match = 3;
            while (match < j && suffix[j-1-match] == suffix[n-1-match])
                ++match;
            if (match > best_match || (match == best_match && j > best_index)) {
                best_match = match;
                best_index = j;
            }
        }
    }
    if (best_match > 3) {
        r.longer_match = 1; r.match_length = best_match;
        r.occurrence_index = best_index;
        // Matching above guarantees this copied opening equals stock[0].
        r.ids[1] = suffix[best_index+1]; r.ids[2] = suffix[best_index+2];
    }
    *output = r;
    return true;
}
} // namespace causal_pld64
