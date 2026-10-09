#pragma once
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace halogen0173::dflash::prefill {
inline constexpr std::array<std::uint32_t, 5> kNativeLayers{4,16,24,36,44};
inline constexpr std::size_t kWidth=2560, kConcatWidth=5*kWidth;
inline constexpr std::size_t kRowBytes=kWidth*sizeof(std::uint16_t);
inline constexpr std::size_t kConcatRowBytes=kConcatWidth*sizeof(std::uint16_t);
enum class State : std::uint8_t { Idle, Pending, Materialized, Request, Retired };
enum class Poll : std::uint8_t { Pending, Complete, Failed };
struct Binding {
    std::array<std::uint8_t,16> session{};
    std::uint64_t ticket{}, lease_generation{}, cache_generation{};
    std::uint64_t holder{}, model{}, wire{}, request{}, birth{};
    std::int32_t slot{};
    std::uint32_t total{};
};
// Cold-supplied, lifetime-pinned functions. All relay calls must be bounded,
// allocation-free and nonblocking. Loss MUST preserve the retained quarantine.
struct LeaseOps {
    void* context{};
    bool (*arm)(void*,const Binding&,std::uint64_t&) noexcept{};
    bool (*valid)(void*,const Binding&) noexcept{};
    bool (*healthy)(void*,const Binding&) noexcept{};
    bool (*materialize)(void*,const Binding&) noexcept{};
    bool (*transfer)(void*,const Binding&,std::uint64_t,std::uint64_t) noexcept{};
    bool (*retire)(void*,const Binding&) noexcept{};
    void (*loss)(void*,std::uint64_t) noexcept{};
    bool (*abandon_materialized)(void*,const Binding&) noexcept{};
};
// Same native stream D2D copies into independent preallocated storage. Source
// is borrowed only during enqueue; queue ordering protects it before reuse.
struct CopyOps {
    void* context{};
    bool (*copy_2d)(void*,void*,std::size_t,const void*,std::size_t,
                    std::size_t,std::size_t,void*) noexcept{};
    bool (*record_fence)(void*,void*,void*) noexcept{};
    Poll (*query_fence)(void*,void*) noexcept{};
};
struct Storage {
    std::int32_t* ids{};
    std::size_t id_capacity{};
    void* features{};
    std::size_t feature_bytes{};
    void* fence{};
};
struct Admission {
    std::uint64_t holder{},model{},wire{},cache_generation{};
    std::int32_t slot{},current_slot{};
    std::uint32_t generation_mode{},slot_count{},total{};
    const std::int32_t* ids{};
    bool actual_cache_null{},ordinary_text{},pins_verified{};
};
struct FeatureView {
    Binding binding{};
    const std::int32_t* ids{};
    const void* bf16_concat{};
    std::uint32_t rows{};
    std::size_t row_bytes{kConcatRowBytes};
};
class Owner final {
public:
    Owner() noexcept=default;
    Owner(const Owner&)=delete;
    Owner& operator=(const Owner&)=delete;
    // Default off; explicit configure requires all cold resources and functions.
    bool configure(bool,const std::array<std::uint8_t,16>&,Storage,LeaseOps,CopyOps) noexcept;
    bool publish(const Admission&) noexcept;
    bool begin_chunk(std::uint64_t holder,std::uint64_t model,std::uint32_t processed,
                     std::uint32_t count,std::int32_t model_position,void* stream) noexcept;
    bool capture_hc(std::uint64_t model,std::uint32_t native_layer,std::uint32_t rows,
                    const void* native_bf16,void* stream) noexcept;
    bool end_chunk(std::uint64_t holder,std::uint32_t processed,std::int32_t model_position) noexcept;
    bool materialize(std::uint64_t holder,std::uint64_t wire,std::int32_t slot,
                     std::uint32_t processed) noexcept;
    void holder_destructor(std::uint64_t holder) noexcept;
    bool abandon_materialized(std::uint64_t wire,std::int32_t slot,std::uint32_t mode,
                              const std::int32_t* complete_ids,std::uint32_t count) noexcept;
    bool transfer(std::uint64_t request,std::uint64_t birth,std::uint64_t model,
                  std::uint64_t wire,std::int32_t slot,std::uint32_t mode,
                  const std::int32_t* complete_ids,std::uint32_t count) noexcept;
    void request_destructor(std::uint64_t request) noexcept;
    bool force_serial(std::uint64_t holder,std::uint64_t model,std::int32_t slot) noexcept;
    bool acquire_features(FeatureView&) noexcept;
    bool release_features(std::uint64_t ticket) noexcept;
    void source_loss() noexcept;
    void disable_new() noexcept { enabled_.store(false,std::memory_order_release); }
    bool storage_reclaimable() noexcept;
    State state() const noexcept { return state_.load(std::memory_order_acquire); }
    Binding binding() noexcept;
private:
    bool enter(bool contention_loss=true) noexcept;
    void leave() noexcept;
    bool pin_identity() noexcept;
    void unpin_identity() noexcept;
    void drain_retirements() noexcept;
    void retire_local(bool materialized=false) noexcept;
    void invalidate() noexcept;
    bool finish_fence() noexcept;
    std::atomic_flag busy_=ATOMIC_FLAG_INIT;
    std::atomic<bool> enabled_{false};
    std::atomic<State> state_{State::Idle};
    std::atomic<std::uint64_t> generation_{0}, losses_{0};
    std::atomic<std::uint32_t> identity_users_{0};
    std::atomic<bool> identity_writer_{false};
    std::atomic<std::uint64_t> holder_retirement_{0},pending_holder_retirement_{0},request_retirement_{0},materialized_retirement_{0};
    std::atomic<std::uint64_t> request_identity_{0},birth_identity_{0};
    std::uint64_t seen_loss_{}, next_ticket_{};
    Binding binding_{};
    Binding immutable_identity_{},retirement_binding_{};
    Storage storage_{};
    LeaseOps lease_{};
    CopyOps copy_{};
    std::array<std::uint8_t,16> session_{};
    std::uint32_t captured_{},chunk_start_{},chunk_rows_{},tap_mask_{};
    void* stream_{};
    bool configured_{},chunk_open_{},feature_valid_{},copy_queued_{},fence_recorded_{};
    bool fence_failed_{},fence_complete_{},borrowed_{};
    bool holder_live_{};
    bool retirement_waiting_{},retirement_materialized_{};
};
}
