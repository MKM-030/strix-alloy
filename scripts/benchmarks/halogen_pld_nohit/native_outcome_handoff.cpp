#include "native_outcome_handoff.h"

#include <limits>

namespace halogen_nohit::handoff {
namespace {
template<std::size_t N> bool nonzero(const std::array<std::uint8_t, N>& value) noexcept {
    std::uint8_t any = 0;
    for (const auto byte : value) { any |= byte; }
    return any != 0;
}
bool qualified(const Qualification& q) noexcept {
    return q.native_capture && q.reset_excluded && q.serial_owner && q.lifetime_held &&
        q.token_definitions && q.exact_full_prefix_verified;
}
bool defined(const TokenDefinitions& tokens, std::int32_t id) noexcept {
    if (id < 0 || tokens.id_limit == 0 || tokens.id_limit > kMaxTokenIds ||
        static_cast<std::uint32_t>(id) >= tokens.id_limit) { return false; }
    const auto value = static_cast<std::uint32_t>(id);
    return (tokens.defined_bits[value / 8] & (1U << (value % 8))) != 0;
}
bool valid_owner(const OwnerIdentity& o) noexcept {
    return nonzero(o.seed_id) && nonzero(o.birth_nonce) && nonzero(o.key_id) &&
        nonzero(o.model) && nonzero(o.tokenizer) && o.native_epoch != 0 &&
        o.owner_generation != 0 && o.model_slot_generation != 0;
}
bool valid_frontier(const Frontier& f, const TokenDefinitions& tokens) noexcept {
    if (!valid_owner(f.owner) || !nonzero(f.frontier_id) || !nonzero(f.window_id) ||
        !nonzero(f.full_prefix_fingerprint) || f.prefix_length == 0 || f.target_position == 0 ||
        f.window_count == 0 || f.window_count > kMaxWindowTokens ||
        f.window_origin >= f.prefix_length || f.prefix_length - f.window_origin != f.window_count ||
        !defined(tokens, f.current_id) || f.window_ids[f.window_count - 1] != f.current_id) { return false; }
    for (std::size_t i = 0; i < f.window_count; ++i) {
        if (!defined(tokens, f.window_ids[i])) { return false; }
    }
    for (std::size_t i = f.window_count; i < kMaxWindowTokens; ++i) {
        if (f.window_ids[i] != 0) { return false; }
    }
    return true;
}
Binding binding(const RoundReservation& r) noexcept {
    Binding b{};
    const auto& f = r.frontier;
    b.key_id = f.owner.key_id;
    b.model = f.owner.model;
    b.tokenizer = f.owner.tokenizer;
    b.birth_nonce = f.owner.birth_nonce;
    b.round_id = r.round_id;
    b.prefix_fingerprint = f.full_prefix_fingerprint;
    b.prefix_length = f.prefix_length;
    b.target_position = f.target_position;
    b.current_id = f.current_id;
    b.window_origin = f.window_origin;
    return b;
}
std::uint32_t read32(const std::uint8_t* bytes) noexcept {
    std::uint32_t out = 0;
    for (std::size_t i = 0; i < 4; ++i) { out |= static_cast<std::uint32_t>(bytes[i]) << (i * 8); }
    return out;
}
} // namespace

bool NativeOutcomeHandoff::initialize(bool enabled, const SeedCopy& seed) noexcept {
    if (!enabled) { return false; }
    if (initialized_ || status_ == Status::Retired) { retire(); return false; }
    initialized_ = true;
    if (!qualified(seed.qualification) || !valid_frontier(seed.canonical, seed.tokens) ||
        !nonzero(seed.first_round_id)) { retire(); return false; }
    current_ = {seed.canonical, seed.first_round_id, 1};
    tokens_ = seed.tokens;
    reserved_ids_[0] = seed.first_round_id;
    frontier_ids_[0] = seed.canonical.frontier_id;
    window_ids_[0] = seed.canonical.window_id;
    reservation_used_ = 1;
    status_ = Status::Sealed;
    return true;
}

bool NativeOutcomeHandoff::adopt_round(const Frontier& actual, const Qualification& q) noexcept {
    if (status_ != Status::Sealed || !qualified(q) || actual != current_.frontier ||
        event_used_ >= events_.size() || reservation_used_ >= reserved_ids_.size() || preview_unread_) {
        retire(); return false;
    }
    seam_seen_ = false;
    external_ = {};
    status_ = Status::Active;
    return true;
}

bool NativeOutcomeHandoff::preview(const OuterPldCopy& copy) noexcept {
    return preview_impl(copy.outcome, Route::OuterPld);
}
bool NativeOutcomeHandoff::preview(const NestedControllerCopy& copy) noexcept {
    return preview_impl(copy.outcome, Route::NestedController);
}
bool NativeOutcomeHandoff::preview(const ScalarCopy& copy) noexcept {
    return preview_impl(copy.outcome, Route::Scalar);
}

bool NativeOutcomeHandoff::preview_impl(const OutcomeCopy& copy, Route route) noexcept {
    if (status_ != Status::Active || preview_unread_ || copy.from != current_ || !qualified(copy.qualification) ||
        copy.outcome_sequence != next_sequence_ || copy.count == 0 || copy.count > kMaxOutputs ||
        copy.native_matched_count != copy.count - 1 || !nonzero(copy.next_round_id) ||
        reservation_used_ >= reserved_ids_.size() || event_used_ >= events_.size() ||
        current_.frontier.prefix_length > std::numeric_limits<std::uint64_t>::max() - copy.count ||
        current_.frontier.target_position > std::numeric_limits<std::uint64_t>::max() - copy.count ||
        copy.target_position_after != current_.frontier.target_position + copy.count ||
        (route == Route::Scalar && (copy.count != 1 || copy.native_matched_count != 0)) ||
        (copy.external_use != ExternalUse::None && copy.external_use != ExternalUse::OpeningRejected &&
         copy.external_use != ExternalUse::Verified) ||
        (copy.external_use != ExternalUse::None && !external_.selected) ||
        (copy.external_use == ExternalUse::Verified && route != Route::OuterPld) ||
        (copy.external_use == ExternalUse::OpeningRejected && route == Route::OuterPld)) {
        retire(); return false;
    }
    for (std::size_t i = 0; i < reservation_used_; ++i) {
        if (copy.next_round_id == reserved_ids_[i]) { retire(); return false; }
    }
    for (std::size_t i = 0; i < copy.count; ++i) {
        if (!defined(tokens_, copy.output_ids[i])) { retire(); return false; }
    }
    if (copy.external_use == ExternalUse::Verified) {
        if (copy.native_matched_count > external_.count) { retire(); return false; }
        for (std::size_t i = 0; i < copy.native_matched_count; ++i) {
            if (copy.output_ids[i] != external_.ids[i]) { retire(); return false; }
        }
    }
    pending_ = copy;
    pending_route_ = route;
    preview_event_ = {current_, copy.next_round_id, current_.generation + 1, route,
        copy.outcome_sequence, copy.target_position_after, copy.count, copy.native_matched_count,
        copy.output_ids, copy.external_use, external_};
    preview_unread_ = true;
    reserved_ids_[reservation_used_++] = copy.next_round_id;
    status_ = Status::Preview;
    return true;
}

bool NativeOutcomeHandoff::seal(const SealCopy& copy) noexcept {
    if (status_ != Status::Preview || copy.disposition != SealDisposition::Continue ||
        !qualified(copy.qualification) || copy.from != current_ ||
        copy.outcome_sequence != pending_.outcome_sequence || copy.emitted_count != pending_.count ||
        !valid_frontier(copy.actual_next, tokens_) ||
        copy.actual_next.owner != current_.frontier.owner ||
        copy.actual_next.prefix_length != current_.frontier.prefix_length + pending_.count ||
        copy.actual_next.target_position != pending_.target_position_after ||
        copy.actual_next.current_id != pending_.output_ids[pending_.count - 1]) {
        retire(); return false;
    }
    for (std::size_t i = 0; i + 1 < reservation_used_; ++i) {
        if (copy.actual_next.frontier_id == frontier_ids_[i] ||
            copy.actual_next.window_id == window_ids_[i]) { retire(); return false; }
    }
    const auto combined_count = current_.frontier.window_count + pending_.count;
    const auto next_count = combined_count < kMaxWindowTokens ? combined_count : kMaxWindowTokens;
    const auto discard = combined_count - next_count;
    if (copy.actual_next.window_count != next_count ||
        copy.actual_next.window_origin != copy.actual_next.prefix_length - next_count) {
        retire(); return false;
    }
    // Bound work to the suffix + <=4 outputs. The qualified caller computes and
    // verifies the exact full-prefix fingerprint outside the interior hook.
    for (std::size_t i = 0; i < next_count; ++i) {
        const auto index = i + discard;
        const auto expected = index < current_.frontier.window_count
            ? current_.frontier.window_ids[index]
            : pending_.output_ids[index - current_.frontier.window_count];
        if (copy.actual_next.window_ids[i] != expected) { retire(); return false; }
    }
    const RoundReservation next{copy.actual_next, pending_.next_round_id, current_.generation + 1};
    events_[event_used_] = {current_, next, pending_route_, pending_.outcome_sequence,
        pending_.count, pending_.native_matched_count, pending_.output_ids,
        pending_.external_use, external_};
    ++event_used_;
    frontier_ids_[reservation_used_ - 1] = copy.actual_next.frontier_id;
    window_ids_[reservation_used_ - 1] = copy.actual_next.window_id;
    current_ = next;
    ++next_sequence_;
    seam_seen_ = false;
    external_ = {};
    pending_ = {};
    status_ = Status::Sealed;
    return true;
}

void NativeOutcomeHandoff::retire() noexcept {
    if (status_ == Status::Retired) { return; }
    retirement_ = {current_, status_ == Status::Preview, pending_.outcome_sequence,
        pending_.next_round_id, status_ == Status::Preview ? current_.generation + 1 : current_.generation};
    retirement_unread_ = true;
    status_ = Status::Retired;
    seam_seen_ = true;
    preview_unread_ = false;
    // Preserve sealed events and all finite ledgers; provisional work is revoked.
    pending_ = {};
    external_ = {};
}

bool NativeOutcomeHandoff::pop_authoritative(AuthoritativeOutcome& out) noexcept {
    if (event_read_ >= event_used_) { return false; }
    out = events_[event_read_++];
    return true;
}

bool NativeOutcomeHandoff::pop_preview(PreviewEvent& out) noexcept {
    if (!preview_unread_) { return false; }
    out = preview_event_;
    preview_unread_ = false;
    return true;
}
bool NativeOutcomeHandoff::pop_retirement(RetirementNotice& out) noexcept {
    if (!retirement_unread_) { return false; }
    out = retirement_;
    retirement_unread_ = false;
    return true;
}

Decision NativeOutcomeHandoff::consume_at_seam(const SeamCapture& capture,
                                              const PreparedPacket* packet,
                                              SavedFrame& frame) noexcept {
    CallerTruth truth{};
    truth.enabled = initialized_;
    const TrustedAuthenticatedFrame* publication = nullptr;
    if (status_ == Status::Active && !seam_seen_) {
        // Expire reply eligibility, preserving all ordinary stock outcome work.
        seam_seen_ = true;
        if (event_used_ >= events_.size() || reservation_used_ >= reserved_ids_.size() || preview_unread_ ||
            !qualified(capture.qualification) || capture.actual_current != current_.frontier ||
            capture.request_rbp == 0 || capture.original_outer_rsp == 0 ||
            capture.request_rbp != frame.gpr[Rbp] || capture.original_outer_rsp != frame.gpr[Rsp]) {
            retire();
        } else if (capture.opening_gate_eligible) {
            // Only an adopted, previously SEALED native frontier supplies truth.
            truth.ownership_qualified = true;
            truth.birth_reset_qualified = true;
            truth.context_current = true;
            truth.positive_pld_policy = capture.positive_pld_policy;
            truth.no_sampler = capture.no_sampler;
            truth.no_suppression = capture.no_suppression;
            truth.positive_width = capture.positive_width;
            truth.sufficient_context = capture.sufficient_context;
            truth.no_constraints = capture.no_constraints;
            truth.native_allowance = capture.native_allowance;
            truth.context_epoch = current_.frontier.owner.native_epoch;
            truth.request_rbp = capture.request_rbp;
            truth.original_outer_rsp = capture.original_outer_rsp;
            truth.binding = binding(current_);
            truth.tokens = tokens_;
            if (packet != nullptr && packet->reservation == current_) { publication = &packet->authenticated; }
        }
    }
    const auto result = consume(truth, publication, ledger_, frame);
    if (result.selected && publication != nullptr) {
        external_.selected = true;
        external_.count = result.count;
        for (std::size_t i = 0; i < result.count; ++i) {
            external_.ids[i] = static_cast<std::int32_t>(read32(publication->bytes.data() + kHeaderBytes + i * 4));
        }
    }
    return result;
}
} // namespace halogen_nohit::handoff
