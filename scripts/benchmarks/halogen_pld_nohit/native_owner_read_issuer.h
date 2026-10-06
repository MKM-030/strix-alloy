#pragma once

#include "native_owner_capture.h"

namespace halogen_nohit::owner_capture {

// Deliberately absent from this source. This separately reviewed engine-local
// connection alone may construct an entry while the REAL native owner is paused.
// It must not be implemented by halogen_nohit_frame_observer (frozen owned-view
// ABI), by a synthetic fixture, or by copy_first_register_observation() later.
class NativeOwnerReadConnection;

enum class DiskAbsenceObservation : std::uint8_t {
    PreallocationExit173c3e9,
    JoinedFailedInitialization173c3ab
};

// Engine-local capability for one synchronous no-hit call, not a publication or
// a caller assertion API. Construction requires the real separate read entry,
// pinned image/stack/token binding and native worker provenance described below.
// Its reference/image and all native spans cease to be usable when that CALL
// returns. The source-closed queue/main ownership supplies the actual hold.
class PausedNativeOwnerEntry {
public:
    PausedNativeOwnerEntry(const PausedNativeOwnerEntry&) = delete;
    PausedNativeOwnerEntry& operator=(const PausedNativeOwnerEntry&) = delete;
    PausedNativeOwnerEntry(PausedNativeOwnerEntry&&) = delete;
    PausedNativeOwnerEntry& operator=(PausedNativeOwnerEntry&&) = delete;
private:
    friend class NativeOwnerReadConnection;
    friend class NativeReadBoundary;
    // NativeOwnerReadConnection must have observed startup C/model identity at
    // the named absence site, and successful joins of any pre-serving indexed
    // dispatch. No dispatcher/other owner thread may start during this CALL.
    // Model timer completion and copy-worker completion follow the genuine
    // main->handler and ordinary no-hit stack path; nested callback entry cannot
    // construct this capability. Bounds must be an actual held stack mapping.
    // Image/hash/native-state/unwind/signal qualification belongs to that entry.
    PausedNativeOwnerEntry(const frame_relay::RegisterImage& real_registers,
                          std::uint64_t image_base,
                          std::uint64_t stack_low, std::uint64_t stack_high,
                          std::uint64_t startup_model, std::uint64_t startup_cache,
                          DiskAbsenceObservation disk_absence,
                          std::uint64_t owner_issued_namespace,
                          const TokenDefinitions& immutable_tokens) noexcept
        : registers_(real_registers), image_base_(image_base),
          stack_low_(stack_low), stack_high_(stack_high),
          startup_model_(startup_model), startup_cache_(startup_cache),
          disk_absence_(disk_absence), namespace_(owner_issued_namespace),
          tokens_(immutable_tokens) {}
    const frame_relay::RegisterImage& registers_;
    const std::uint64_t image_base_, stack_low_, stack_high_;
    const std::uint64_t startup_model_, startup_cache_;
    const DiskAbsenceObservation disk_absence_;
    const std::uint64_t namespace_;
    const TokenDefinitions& tokens_;
};

enum class ReadIssuerStatus : std::uint8_t {
    Disabled, UpstreamConnectionUnavailable, UnsupportedPlatform,
    ReentrantOrExhausted, EntryBindingMismatch, CallerFrameMismatch,
    QueueOwnerMismatch, NativeScopeDeclined, InvalidVector, DecodeRejected,
    OwnedUnqualified
};

// Value-only result: no native origins, register image, spans or capabilities.
struct ReadIssuerObservation {
    ReadIssuerStatus status = ReadIssuerStatus::Disabled;
    OwnedObservation owned{};
};

// Definition of the existing NativeReadInterval friend. Preallocate once per
// exclusively owned native handler. Public enable requests observation only;
// without the independently constructed entry they cause NO native reads.
// This first issuer ALWAYS passes acknowledgement=nullptr and observed_owner=
// nullptr. It cannot initialize/adopt/consume a qualified handoff or proposal.
class NativeReadBoundary {
public:
    explicit NativeReadBoundary(bool enable = false) noexcept : enabled_(enable) {}
    NativeReadBoundary(const NativeReadBoundary&) = delete;
    NativeReadBoundary& operator=(const NativeReadBoundary&) = delete;
    NativeReadBoundary(NativeReadBoundary&&) = delete;
    NativeReadBoundary& operator=(NativeReadBoundary&&) = delete;

    // Call ONLY inside the separate trusted native read entry. Exclusive owner
    // serialization and the capability's native lifetime cover this whole call.
    // No allocation/probe/lock/wait/callback/full-prefix hash; no native writes.
    ReadIssuerObservation observe_nohit(const PausedNativeOwnerEntry* entry) noexcept;
private:
    const bool enabled_;
    bool reading_ = false;
    std::uint64_t namespace_ = 0, sequence_ = 0;
    NativeOwnerCapture capture_{true};
    handoff::NativeOutcomeHandoff unqualified_handoff_{};
};

} // namespace halogen_nohit::owner_capture
