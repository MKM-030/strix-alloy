#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <span>

namespace raw_id {
inline bool replay_append_eligible(bool append_enabled, bool reuse_permitted,
                                  std::size_t committed_length,
                                  std::span<const std::int32_t> proposal,
                                  std::span<const std::int32_t> replay) {
    constexpr std::size_t window_limit = 512;
    if (!append_enabled || !reuse_permitted || proposal.empty() || committed_length > window_limit)
        return false;
    const auto consumed = proposal.size() - 1;
    return replay.size() >= consumed && replay.size() <= window_limit - committed_length &&
           std::equal(proposal.begin(), proposal.begin() + consumed, replay.begin());
}
} // namespace raw_id
