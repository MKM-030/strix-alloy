#pragma once
#include "pending_owner.h"
namespace halogen0173::dflash::prefill {
enum class DecodeSource : std::uint8_t { Verify,Scalar };
struct DecodeStorage {void* features{};std::size_t bytes{};void* fence{};};
struct DecodeView {
    Binding binding{};
    std::uint64_t capture_sequence{},round{};
    DecodeSource source{};
    std::int32_t anchor{},next_current{};
    std::uint32_t verified_rows{},committed_rows{};
    std::array<std::int32_t,4> ids{}; // Only committed_rows are causal provider input.
    const void* bf16_concat{}; // Independent queue storage, never native HC memory.
    std::size_t row_bytes{kConcatRowBytes};
};
class DecodeCapture final {
public:
    static constexpr std::size_t kSlots=8;
    bool configure(bool,LeaseOps,CopyOps,const std::array<DecodeStorage,kSlots>&) noexcept;
    bool begin(const Binding&,std::uint64_t round,DecodeSource,std::int32_t anchor,
               const std::int32_t* ids,std::uint32_t rows,std::uint32_t transported_before) noexcept;
    bool capture_hc(std::uint64_t model,std::uint32_t layer,std::uint32_t rows,const void* source,void* stream) noexcept;
    bool forward_returned() noexcept;
    bool committed(std::uint32_t authoritative_count,std::int32_t native_position) noexcept;
    bool outcome(const Binding&,std::int32_t native_status,std::int32_t next_current,std::uint32_t transported_after) noexcept;
    bool acquire(DecodeView&) noexcept;
    bool release(std::uint64_t capture_sequence) noexcept;
    void source_loss() noexcept;
    void retire(std::uint64_t generation) noexcept;
    void disable_new() noexcept {enabled_.store(false,std::memory_order_release);}
    bool storage_reclaimable() noexcept;
private:
    struct Slot {
        DecodeStorage storage{};
        DecodeView view{};
        std::uint64_t loss{};
        std::uint32_t transported_before{},mask{};
        bool occupied{},valid{},queued{},recorded{},fence_failed{},complete{},returned{},committed{},done{},borrowed{};
    };
    bool enter(bool contention_loss=true) noexcept;
    void leave() noexcept;
    void drain_retirements() noexcept;
    void finish_admission() noexcept;
    void invalidate(Slot&) noexcept;
    bool fence_complete(Slot&) noexcept;
    void clear_front() noexcept;
    std::array<Slot,kSlots> slots_{};
    static constexpr std::uint64_t kRetired=std::uint64_t{1}<<63;
    std::array<std::atomic<std::uint64_t>,kSlots> slot_generation_{};
    std::atomic_flag busy_=ATOMIC_FLAG_INIT;
    std::atomic<bool> enabled_{false};
    std::atomic<std::uint64_t> losses_{0},generation_{0},admission_generation_{0};
    LeaseOps lease_{};CopyOps copy_{};
    std::size_t read_{},write_{},count_{},active_{kSlots};
    std::uint64_t sequence_{},last_round_{};
    std::uint64_t retired_generation_{};
    bool configured_{};
};
}
