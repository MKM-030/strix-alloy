#pragma once
#include "pending_owner.h"

namespace halogen0173::dflash::prefill {
enum class Site : std::uint32_t {
    PendingPublication, InitialFlagJoin, ChunkFlagJoin, ChunkForward,
    ChunkForwardReturned, RecordMaterialize, PendingDestructor,
    SuccessfulBirthA, SuccessfulBirthB, RequestDestructor, RecordDestructor
};
struct Frame { std::array<std::uint64_t,16> gpr{}; };
struct NativeProof {
    void* context{};
    // Exact loaded pins, ordinary greedy unconstrained text, one native slot,
    // current slot and cache generation must be proven for THIS holder.
    bool (*admit)(void*,std::uint64_t holder,std::uint64_t model,
                  std::uint64_t wire,std::int32_t slot,std::uint64_t& cache_generation) noexcept{};
    std::uint64_t selected_model{};
    bool default_stream_verified{};
};
class NativeAdapter final {
public:
    bool configure(bool enable,Owner* owner,NativeProof proof) noexcept;
    void on_site(Site,const Frame&) noexcept;
    // HC seam after both ordinary/profiled collapse calls. Borrowed native HC
    // pointer is passed directly to the bounded copy queue, never retained.
    void on_hc(const Frame&) noexcept;
    void source_loss() noexcept {if(owner_)owner_->source_loss();}
    void disable_new() noexcept {if(owner_)owner_->disable_new();}
private:
    Owner* owner_{};
    NativeProof proof_{};
    bool enabled_{};
    std::uint64_t births_{};
};
}
