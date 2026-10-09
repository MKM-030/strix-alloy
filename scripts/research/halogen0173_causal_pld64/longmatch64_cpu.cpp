#include "longmatch64.h"

// Freestanding test export only: no entry point, startup or native integration.
extern "C" __declspec(dllexport) int causal_pld64_predict(
    const causal_pld64::i32* suffix, causal_pld64::u32 n,
    const causal_pld64::i32* stock, const causal_pld64::u8* bitmap,
    causal_pld64::u32 bit_count, causal_pld64::i32* ids,
    causal_pld64::u32* metadata) noexcept {
    if (!ids || !metadata) return 1;
    causal_pld64::Result r;
    if (!causal_pld64::propose(suffix, n, stock, bitmap, bit_count, &r)) return 2;
    for (unsigned i = 0; i < 3; ++i) ids[i] = r.ids[i];
    metadata[0] = r.longer_match; metadata[1] = r.match_length;
    metadata[2] = r.occurrence_index; metadata[3] = r.checked_positions;
    return 0;
}
