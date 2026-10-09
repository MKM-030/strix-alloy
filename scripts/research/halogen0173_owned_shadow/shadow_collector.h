#pragma once
#include "shadow_wire.h"
#include <atomic>

namespace halogen0173::shadow {
enum class Site : std::uint32_t {
    SuccessfulBirthA, SuccessfulBirthB, BeforeNeuralDepth, PldCopiedHit,
    CommonOutcome, RequestDestructor, SlotBind, CurrentSlotReset, SlotRelease
};
// Supplied by a state-preserving native relay. RSP is the ORIGINAL native RSP.
// Callback borrows this image and native objects only until on_site returns.
struct Frame {
    std::array<std::uint64_t,16> gpr{}; // RAX,RBX,RCX,RDX,RSI,RDI,RBP,RSP,R8..R15
};
class Collector {
public:
    static constexpr std::size_t kOwners=128, kSlots=128, kRing=4096;
    // Default construction does not inspect native memory or publish events.
    Collector() noexcept = default;
    Collector(const Collector&)=delete;
    Collector& operator=(const Collector&)=delete;
    // Only a caller that has installed all pinned callbacks may explicitly enable.
    // Called before serving starts. Nonzero session is externally supplied.
    bool configure(bool enable, const std::array<std::uint8_t,16>& session) noexcept;
    Header header() const noexcept;
    void on_site(Site site, const Frame& frame) noexcept;
    // Copies only owned records. No native pointers or frame references escape.
    bool drain(Event& event) noexcept;
    void disable() noexcept { enabled_.store(false,std::memory_order_release); }
    // Called by the cold writer AFTER disable and complete drain, never a relay.
    bool close_counts(std::uint64_t& dropped,std::uint64_t& live,std::uint64_t& pending) noexcept;
    // Linux/GNU relay only: startup asserts these atomics' byte sizes/lock freedom.
    // Immutable island config refers to adapter-owned state, never native state.
    void* loss_counter_address() noexcept { return &dropped_; }
    void* enabled_address() noexcept { return &enabled_; }
private:
    struct Owner {
        std::uint64_t request{}, model{}, birth{}, wire{}, cookie{}, epoch{}, round{};
        std::int32_t slot{};
        bool live{}, pending{};
        Event before{};
    };
    struct Slot {
        std::uint64_t model{}, cookie{}, epoch{};
        std::int32_t number{};
        bool used{};
    };
    bool enter() noexcept;
    void leave() noexcept;
    void lose() noexcept;
    void reconcile_loss() noexcept;
    bool publish(Event event) noexcept;
    Owner* find(std::uint64_t request) noexcept;
    Slot* slot(std::uint64_t model, std::int32_t number, bool create) noexcept;
    void invalidate(std::uint64_t model, std::int32_t number) noexcept;
    Event identity(const Owner& owner, Kind kind) const noexcept;
    bool snapshot(Event& event, std::uint64_t request, std::uint64_t record,
                  Source source, std::uint64_t offer, std::uint64_t offer_count) noexcept;
    std::atomic<bool> enabled_{false};
    std::array<std::uint8_t,16> session_{};
    std::atomic_flag busy_=ATOMIC_FLAG_INIT;
    std::atomic<std::uint64_t> dropped_{0};
    std::uint64_t loss_seen_{}, sequence_{}, births_{}, cookies_{};
    bool gap_pending_{};
    std::array<Owner,kOwners> owners_{};
    std::array<Slot,kSlots> slots_{};
    std::array<Event,kRing> ring_{};
    std::size_t read_{}, write_{}, count_{};
};
} // namespace halogen0173::shadow
