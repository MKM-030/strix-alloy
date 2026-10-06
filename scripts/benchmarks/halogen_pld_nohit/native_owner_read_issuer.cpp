#include "native_owner_read_issuer.h"

#include <algorithm>
#include <bit>
#include <cstring>
#include <limits>

namespace halogen_nohit::owner_capture {
namespace {
constexpr std::uint64_t kCallerReturn = 0x171ba1f;
constexpr std::uint64_t kProgressManager = 0x1736da0;
constexpr std::uint64_t kProgressCallable = 0x1736aa0;
constexpr std::uint64_t kAggregateOffset = 0x2800;
constexpr std::uint64_t kModelOffset = 0x2d58;
constexpr std::uint64_t kConnectionOffset = 0x2968;
constexpr std::uint64_t kRequiredStackAbove = kModelOffset + capture::kModelBytes;
static_assert(sizeof(std::uintptr_t) == sizeof(std::uint64_t));
static_assert(std::endian::native == std::endian::little);

bool extent(std::uint64_t address, std::uint64_t bytes) noexcept {
    return address != 0 && bytes != 0 &&
        address <= std::numeric_limits<std::uint64_t>::max() - bytes;
}
std::span<const std::uint8_t> native_bytes(std::uint64_t address,
                                        std::size_t bytes) noexcept {
    return {reinterpret_cast<const std::uint8_t*>(
                static_cast<std::uintptr_t>(address)), bytes};
}
// Direct native reads occur only after the entry capability establishes the
// containing object's native ownership. Numeric/equality checks do not supply
// mapping/lifetime evidence and no copied pointer is treated as authority.
std::uint64_t u64(std::uint64_t address) noexcept {
    std::uint64_t value = 0;
    std::memcpy(&value, reinterpret_cast<const void*>(
                    static_cast<std::uintptr_t>(address)), sizeof value);
    return value;
}
std::int32_t i32(std::uint64_t address) noexcept {
    std::int32_t value = 0;
    std::memcpy(&value, reinterpret_cast<const void*>(
                    static_cast<std::uintptr_t>(address)), sizeof value);
    return value;
}
std::uint8_t byte(std::uint64_t address) noexcept {
    return *reinterpret_cast<const std::uint8_t*>(
        static_cast<std::uintptr_t>(address));
}
ReadIntervalBinding next_binding(std::uint64_t issuer_namespace,
                                std::uint64_t sequence) noexcept {
    ReadIntervalBinding result{};
    // Owner-issued namespace + monotonic call number, never an address hash.
    for (std::size_t i = 0; i < 8; ++i) {
        result.interval_id[i] = static_cast<std::uint8_t>(issuer_namespace >> (8 * i));
        result.interval_id[8 + i] = static_cast<std::uint8_t>(sequence >> (8 * i));
    }
    result.invocation_sequence = sequence;
    return result;
}
struct ReadingScope {
    bool& active;
    explicit ReadingScope(bool& value) noexcept : active(value) { active = true; }
    ~ReadingScope() { active = false; }
};
}

ReadIssuerObservation NativeReadBoundary::observe_nohit(
    const PausedNativeOwnerEntry* entry) noexcept {
    ReadIssuerObservation result{};
    if (!enabled_) { return result; }
    if (entry == nullptr) {
        result.status = ReadIssuerStatus::UpstreamConnectionUnavailable;
        return result;
    }
#if !defined(__linux__) || !defined(__x86_64__)
    result.status = ReadIssuerStatus::UnsupportedPlatform;
    return result;
#endif
    if (reading_ || sequence_ == std::numeric_limits<std::uint64_t>::max()) {
        result.status = ReadIssuerStatus::ReentrantOrExhausted;
        return result;
    }
    ReadingScope scope{reading_};
    const auto& registers = entry->registers_;
    const auto outer = registers.gpr[Rsp];
    const auto image = entry->image_base_;
    if (entry->namespace_ == 0 || image == 0 ||
        !extent(image, kProgressManager + 1) ||
        entry->tokens_.id_limit == 0 || entry->tokens_.id_limit > kMaxTokenIds ||
        (entry->disk_absence_ != DiskAbsenceObservation::PreallocationExit173c3e9 &&
         entry->disk_absence_ != DiskAbsenceObservation::JoinedFailedInitialization173c3ab) ||
        (namespace_ != 0 && namespace_ != entry->namespace_) ||
        entry->stack_low_ >= entry->stack_high_ ||
        !extent(outer, kRequiredStackAbove) || outer < entry->stack_low_ ||
        outer + kRequiredStackAbove > entry->stack_high_) {
        result.status = ReadIssuerStatus::EntryBindingMismatch;
        return result;
    }
    if (namespace_ == 0) { namespace_ = entry->namespace_; }
    const auto binding = next_binding(namespace_, ++sequence_);
    const auto aggregate = outer + kAggregateOffset;
    const auto model = outer + kModelOffset;
    // These initial reads touch only the actual registered paused main/handler
    // stack. The saved caller return binds completed construction and main hold.
    if (u64(outer + 0x2678) != image + kCallerReturn ||
        u64(outer) != aggregate || u64(aggregate) != model ||
        u64(outer + 0x70) != outer + kConnectionOffset ||
        model != entry->startup_model_) {
        result.status = ReadIssuerStatus::CallerFrameMismatch;
        return result;
    }
    const auto cache = u64(aggregate + 8);
    // main RSP=outer+2680; C is also retained in main RSP+38. Startup observed
    // this exact C before its absence return, so its heap storage is held here.
    if (cache != entry->startup_cache_ || cache != u64(outer + 0x26b8) ||
        !extent(cache, 0x158) || cache % 8 != 0) {
        result.status = ReadIssuerStatus::CallerFrameMismatch;
        return result;
    }
    const auto record = registers.gpr[R15];
    const auto request = registers.gpr[Rbp];
    const auto queue_begin = u64(outer + 0x170);
    const auto queue_end = u64(outer + 0x178);
    const auto queue_capacity = u64(outer + 0x180);
    if (!extent(record, capture::kRecordBytes) || record % 8 != 0 ||
        queue_begin != record || queue_end != record + capture::kRecordBytes ||
        queue_capacity < queue_end || u64(outer + 8) != record) {
        result.status = ReadIssuerStatus::QueueOwnerMismatch;
        return result;
    }
    // One actual owned queue record now holds its request. No other owner thread
    // can release it under this paused entry; a retirement flag is never a hold.
    if (!extent(request, capture::kRequestBytes) || request % 8 != 0 ||
        u64(record + 0x10) != request || u64(request + 0xd8) != model ||
        i32(record + 8) != i32(model + 0xa0)) {
        result.status = ReadIssuerStatus::QueueOwnerMismatch;
        return result;
    }
    const auto prefill_begin = u64(record + 0x140);
    const auto prefill_end = u64(record + 0x148);
    if (prefill_end < prefill_begin || (prefill_end - prefill_begin) % 4 != 0 ||
        (prefill_end - prefill_begin) / 4 > capture::kContextCapacity ||
        u64(record + 0x158) < (prefill_end - prefill_begin) / 4 ||
        byte(request + 0x1e4) != 0 || u64(request + 0x150) != 0 ||
        u64(request + 0x1e8) != 0 || i32(request + 0x1d0) != 0 ||
        i32(request + 0x1dc) != 0 || byte(model + 0x1c3) != 0 ||
        u64(cache + 0x60) != model || u64(cache + 0xe0) != 0 ||
        u64(aggregate + 0x130) != 0 ||
        u64(model + 0x238) != aggregate || u64(model + 0x240) != 0 ||
        u64(model + 0x248) != image + kProgressManager ||
        u64(model + 0x250) != image + kProgressCallable) {
        result.status = ReadIssuerStatus::NativeScopeDeclined;
        return result;
    }
    for (const std::uint64_t holder : {0x270, 0x290, 0x2b0, 0x2d0, 0x2f0}) {
        if (u64(model + holder) != 0 || u64(model + holder + 8) != 0) {
            result.status = ReadIssuerStatus::NativeScopeDeclined;
            return result;
        }
    }
    const auto begin = u64(request + 0x178);
    const auto end = u64(request + 0x180);
    const auto capacity = u64(request + 0x188);
    if (begin == 0 || end <= begin || capacity < end ||
        begin % 4 != 0 || end % 4 != 0 || capacity % 4 != 0 ||
        (end - begin) / 4 > capture::kContextCapacity ||
        (capacity - begin) / 4 > capture::kContextCapacity) {
        result.status = ReadIssuerStatus::InvalidVector;
        return result;
    }
    const auto suffix_count = std::min((end - begin) / 4,
                                      std::uint64_t{kMaxWindowTokens});
    const auto suffix_bytes = static_cast<std::size_t>(suffix_count * 4);
    const NativeReadSpans spans{
        native_bytes(request, capture::kRequestBytes),
        native_bytes(model, capture::kModelBytes),
        native_bytes(record, capture::kRecordBytes),
        native_bytes(outer, capture::kOuterBytes),
        native_bytes(end - suffix_bytes, suffix_bytes)};
    // Capability never escapes this lexical scope. NativeOwnerCapture makes its
    // complete bounded owned copies before any decoding. No driver/tensor buffer
    // is followed. Missing owner/ack keeps the internal handoff uninitialized.
    const NativeReadInterval interval{binding, spans, registers, &entry->tokens_, nullptr};
    result.owned = capture_.observe(&interval, nullptr, unqualified_handoff_);
    result.status = result.owned.result == ObservationResult::OwnedUnqualified
        ? ReadIssuerStatus::OwnedUnqualified : ReadIssuerStatus::DecodeRejected;
    return result;
}

} // namespace halogen_nohit::owner_capture
