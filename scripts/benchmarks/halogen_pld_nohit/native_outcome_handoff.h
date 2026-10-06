#pragma once

#include "seam_contract.h"

namespace halogen_nohit::handoff {

using Id = std::array<std::uint8_t, 16>;
using Fingerprint = std::array<std::uint8_t, 32>;
inline constexpr std::size_t kMaxOutputs = 4;
inline constexpr std::size_t kEventBudget = 64;

// Value-only ABI. These are opaque identities, never encoded native addresses.
struct OwnerIdentity {
    Id seed_id{};
    Id birth_nonce{};
    Id key_id{};
    Fingerprint model{};
    Fingerprint tokenizer{};
    std::uint64_t native_epoch{};
    std::uint64_t owner_generation{};
    std::uint64_t model_slot_generation{};
    bool operator==(const OwnerIdentity&) const = default;
};

struct Frontier {
    OwnerIdentity owner{};
    Id frontier_id{};
    Id window_id{};
    std::uint64_t prefix_length{};
    std::uint64_t target_position{};
    std::int32_t current_id{};
    std::uint64_t window_origin{};
    std::size_t window_count{};
    std::array<std::int32_t, kMaxWindowTokens> window_ids{};
    // Unused window slots must be zero for complete value identity comparison.
    Fingerprint full_prefix_fingerprint{};
    bool operator==(const Frontier&) const = default;
};

struct RoundReservation {
    Frontier frontier{};
    Id round_id{};
    std::uint64_t generation{};
    bool operator==(const RoundReservation&) const = default;
};

// Assertions about an independently proved native boundary, not a mechanism
// establishing engine truth. The synthetic harness only assumes these facts.
// All operations require exclusive caller ownership and immutable input copies.
struct Qualification {
    bool native_capture = false;
    bool reset_excluded = false;
    bool serial_owner = false;
    bool lifetime_held = false;
    bool token_definitions = false;
    bool exact_full_prefix_verified = false; // Computed/verified outside hook.
};

struct SeedCopy {
    Frontier canonical{};
    Id first_round_id{};
    TokenDefinitions tokens{};
    Qualification qualification{};
};

enum class ExternalUse : std::uint8_t { None, OpeningRejected, Verified };
enum class Route : std::uint8_t { OuterPld, NestedController, Scalar };
struct OutcomeCopy {
    RoundReservation from{};
    std::uint64_t outcome_sequence{};
    Id next_round_id{};
    std::uint64_t target_position_after{};
    std::uint8_t count{};
    std::uint8_t native_matched_count{};
    std::array<std::int32_t, kMaxOutputs> output_ids{};
    ExternalUse external_use = ExternalUse::None;
    Qualification qualification{};
};

// Distinct copied-fact types prevent confusing the outer output block with the
// nested controller frame or the verifier input block [current, proposals...].
struct OuterPldCopy { OutcomeCopy outcome{}; }; // post-return 0x172d80f, outer +0x1980
struct NestedControllerCopy { OutcomeCopy outcome{}; }; // 0x173b769, controller +0x30
struct ScalarCopy { OutcomeCopy outcome{}; }; // selected ID after constraint validation

enum class SealDisposition : std::uint8_t { Continue, Retire };
struct SealCopy {
    RoundReservation from{};
    std::uint64_t outcome_sequence{};
    Frontier actual_next{}; // Exact native vector suffix/current ID/position.
    std::uint8_t emitted_count{};
    SealDisposition disposition = SealDisposition::Retire;
    Qualification qualification{};
};

struct RecordedExternalProposal {
    bool selected = false;
    std::uint8_t count{};
    std::array<std::int32_t, kMaxIds> ids{};
};

struct AuthoritativeOutcome {
    RoundReservation from{};
    RoundReservation next{};
    Route route{};
    std::uint64_t outcome_sequence{};
    std::uint8_t count{};
    std::uint8_t native_matched_count{};
    std::array<std::int32_t, kMaxOutputs> output_ids{};
    ExternalUse external_use{};
    RecordedExternalProposal external{};
    // No fabricated custom accepted count: resolution uses exact owned IDs.
};

struct PreviewEvent {
    RoundReservation from{};
    Id next_round_id{};
    std::uint64_t reserved_generation{};
    Route route{};
    std::uint64_t outcome_sequence{};
    std::uint64_t target_position_after{};
    std::uint8_t count{};
    std::uint8_t native_matched_count{};
    std::array<std::int32_t, kMaxOutputs> output_ids{};
    ExternalUse external_use{};
    RecordedExternalProposal external{};
};

// Sticky, one-shot notice revokes every private completion for this owner. The
// optional provisional identity lets an already-drained preview be cancelled.
struct RetirementNotice {
    RoundReservation last_sealed{};
    bool provisional_revoked = false;
    std::uint64_t revoked_outcome_sequence{};
    Id revoked_next_round_id{};
    std::uint64_t revoked_generation{};
};

struct PreparedPacket {
    RoundReservation reservation{}; // Binds seed/window/full identity off wire.
    TrustedAuthenticatedFrame authenticated{};
};

// Local seam-only copied facts. RBP/RSP are saved-frame identities; they never
// enter the event ABI or PreparedPacket. Capture/reset proof is external.
struct SeamCapture {
    Frontier actual_current{};
    Qualification qualification{};
    std::uint64_t request_rbp{};
    std::uint64_t original_outer_rsp{};
    bool positive_pld_policy = false;
    bool no_sampler = false;
    bool no_suppression = false;
    bool positive_width = false;
    bool sufficient_context = false;
    bool no_constraints = false;
    bool opening_gate_eligible = false; // Independently copied native MTP gate scope.
    std::int32_t native_allowance{};
};

enum class Status : std::uint8_t { Disabled, Sealed, Active, Preview, Retired };

class NativeOutcomeHandoff {
public:
    NativeOutcomeHandoff() = default;
    NativeOutcomeHandoff(const NativeOutcomeHandoff&) = delete;
    NativeOutcomeHandoff& operator=(const NativeOutcomeHandoff&) = delete;
    NativeOutcomeHandoff(NativeOutcomeHandoff&&) = delete;
    NativeOutcomeHandoff& operator=(NativeOutcomeHandoff&&) = delete;
    bool initialize(bool enabled, const SeedCopy& seed) noexcept;
    bool adopt_round(const Frontier& actual, const Qualification& qualification) noexcept;
    bool preview(const OuterPldCopy& copy) noexcept;
    bool preview(const NestedControllerCopy& copy) noexcept;
    bool preview(const ScalarCopy& copy) noexcept;
    bool seal(const SealCopy& copy) noexcept;
    void retire() noexcept;
    bool pop_preview(PreviewEvent& out) noexcept;
    bool pop_retirement(RetirementNotice& out) noexcept;
    bool pop_authoritative(AuthoritativeOutcome& out) noexcept;
    Decision consume_at_seam(const SeamCapture& capture, const PreparedPacket* packet,
                             SavedFrame& frame) noexcept;
    const RoundReservation& reservation() const noexcept { return current_; }
    Status status() const noexcept { return status_; }
    std::size_t queued() const noexcept { return event_used_ - event_read_; }
    std::size_t consumed_rounds() const noexcept { return ledger_.used; }
private:
    bool preview_impl(const OutcomeCopy& copy, Route route) noexcept;
    Status status_ = Status::Disabled;
    bool initialized_ = false;
    bool seam_seen_ = false;
    RoundReservation current_{};
    TokenDefinitions tokens_{};
    OutcomeCopy pending_{};
    Route pending_route_{};
    RecordedExternalProposal external_{};
    PreviewEvent preview_event_{};
    bool preview_unread_ = false;
    RetirementNotice retirement_{};
    bool retirement_unread_ = false;
    std::uint64_t next_sequence_ = 1;
    std::array<Id, kMaxRounds + 1> reserved_ids_{};
    std::size_t reservation_used_{};
    std::array<Id, kMaxRounds + 1> frontier_ids_{};
    std::array<Id, kMaxRounds + 1> window_ids_{};
    std::array<AuthoritativeOutcome, kEventBudget> events_{};
    std::size_t event_used_{};
    std::size_t event_read_{};
    OneShotLedger ledger_{};
};

} // namespace halogen_nohit::handoff
