#include "native_owner_capture.h"

#include <bit>
#include <cstring>
#include <limits>

namespace halogen_nohit::owner_capture {
namespace {
static_assert(sizeof(std::uintptr_t) == sizeof(std::uint64_t));
static_assert(std::endian::native == std::endian::little);

template<std::size_t N>
bool nonzero(const std::array<std::uint8_t, N>& value) noexcept {
    std::uint8_t any = 0;
    for (const auto byte : value) { any |= byte; }
    return any != 0;
}
std::uint64_t origin(std::span<const std::uint8_t> bytes) noexcept {
    return static_cast<std::uint64_t>(reinterpret_cast<std::uintptr_t>(bytes.data()));
}
bool exact_span(std::span<const std::uint8_t> bytes, std::size_t size) noexcept {
    return bytes.size() == size && bytes.data() != nullptr &&
        origin(bytes) <= std::numeric_limits<std::uint64_t>::max() - size;
}
std::uint64_t u64(std::span<const std::uint8_t> bytes, std::size_t at) noexcept {
    std::uint64_t value = 0;
    for (std::size_t i = 0; i < 8; ++i) { value |= std::uint64_t{bytes[at + i]} << (8 * i); }
    return value;
}
bool valid_owner(const handoff::OwnerIdentity& o) noexcept {
    return nonzero(o.seed_id) && nonzero(o.birth_nonce) && nonzero(o.key_id) &&
        nonzero(o.model) && nonzero(o.tokenizer) && o.native_epoch != 0 &&
        o.owner_generation != 0 && o.model_slot_generation != 0;
}
void retire_live(handoff::NativeOutcomeHandoff& state) noexcept {
    if (state.status() != handoff::Status::Disabled &&
        state.status() != handoff::Status::Retired) { state.retire(); }
}
bool matches_facts(const handoff::Frontier& f, const capture::NoHitFacts& facts) noexcept {
    return f.prefix_length == facts.prefix_length && f.target_position == facts.target_position &&
        f.current_id == facts.current_id && f.window_origin == facts.window_origin &&
        f.window_count == facts.window_count && f.window_ids == facts.window_ids;
}
}

OwnedObservation NativeOwnerCapture::observe(
    const NativeReadInterval* read, const PriorPrefixAcknowledgement* acknowledged,
    handoff::NativeOutcomeHandoff& state) noexcept {
    observation_.result = ObservationResult::Disabled;
    observation_.decode_result = capture::DecodeResult::MissingCopy;
    observation_.facts_available = false;
    observation_.facts = {};
    observation_.handoff_consumed = false;
    observation_.stock_decision = {kStockResumeRva, Reason::Disabled, 0, false};
    if (!enabled_) { return observation_; }
    if (read == nullptr || !nonzero(read->binding_.interval_id) ||
        read->binding_.invocation_sequence == 0) {
        observation_.result = ObservationResult::ReadIntervalUnavailable;
        retire_live(state);
        return observation_;
    }

    // All checks here inspect descriptors / the owned real register image only.
    // They establish layout consistency, never native mapping/lifetime safety.
    const auto& native = read->spans_;
    const auto& registers = read->registers_;
    if (!exact_span(native.request, capture::kRequestBytes) ||
        !exact_span(native.model, capture::kModelBytes) ||
        !exact_span(native.record, capture::kRecordBytes) ||
        !exact_span(native.outer, capture::kOuterBytes) ||
        native.suffix.empty() || native.suffix.size() > sizeof(suffix_) ||
        native.suffix.size() % sizeof(std::int32_t) != 0 ||
        !exact_span(native.suffix, native.suffix.size()) || read->definitions_ == nullptr ||
        origin(native.request) != registers.gpr[Rbp] ||
        origin(native.record) != registers.gpr[R15] || origin(native.outer) != registers.gpr[Rsp]) {
        observation_.result = ObservationResult::InvalidReadSpans;
        retire_live(state);
        return observation_;
    }

    // The ONLY native reads in this adapter, under the upstream held interval.
    // No pointer from the copied request/model/record is followed or probed.
    std::memcpy(request_.data(), native.request.data(), request_.size());
    std::memcpy(model_.data(), native.model.data(), model_.size());
    std::memcpy(record_.data(), native.record.data(), record_.size());
    std::memcpy(outer_.data(), native.outer.data(), outer_.size());
    suffix_.fill(0);
    std::memcpy(suffix_.data(), native.suffix.data(), native.suffix.size());
    const auto suffix_count = native.suffix.size() / sizeof(std::int32_t);
    const capture::NoHitCopies copies{
        {origin(native.request), request_}, {origin(native.model), model_},
        {origin(native.record), record_}, {origin(native.outer), outer_},
        registers.gpr, origin(native.suffix),
        std::span<const std::int32_t>{suffix_.data(), suffix_count}, read->definitions_};
    // These const spans are immutable for the entire synchronous decoder call.
    observation_.decode_result = capture::decode_nohit(copies, observation_.facts);
    if (observation_.decode_result != capture::DecodeResult::Captured) {
        observation_.result = ObservationResult::DecodeRejected;
        retire_live(state);
        return observation_;
    }
    observation_.facts_available = true;
    if (acknowledged == nullptr || read->observed_owner_ == nullptr) {
        observation_.result = ObservationResult::OwnedUnqualified;
        retire_live(state);
        return observation_;
    }

    const auto& prior = acknowledged->binding_;
    // Bounded seam comparisons only. Full-ID verification / fingerprinting and
    // continuity were ALREADY established by the acknowledgement authority.
    // These equality checks cannot supply an omitted-prefix proof themselves.
    if (prior.read_interval != read->binding_ || prior.definitions != read->definitions_ ||
        !valid_owner(*read->observed_owner_) || prior.canonical.owner != *read->observed_owner_ ||
        !nonzero(prior.canonical.frontier_id) || !nonzero(prior.canonical.window_id) ||
        !nonzero(prior.canonical.full_prefix_fingerprint) || prior.canonical.target_position == 0 ||
        !matches_facts(prior.canonical, observation_.facts) ||
        prior.native_slot != observation_.facts.slot ||
        prior.complete_owned_prefix.data() == nullptr ||
        prior.complete_owned_prefix.size() != observation_.facts.prefix_length ||
        prior.request_origin != origin(native.request) || prior.model_origin != origin(native.model) ||
        prior.record_origin != origin(native.record) || prior.outer_origin != origin(native.outer) ||
        prior.vector_begin != u64(request_, 0x178) || prior.vector_end != u64(request_, 0x180) ||
        prior.vector_capacity != u64(request_, 0x188)) {
        observation_.result = ObservationResult::PrefixBindingMismatch;
        retire_live(state);
        return observation_;
    }

    // Translate the two independently issued capabilities into the unchanged
    // legacy assertion API. No qualification comes from decode/gates/equalities.
    constexpr handoff::Qualification qualification{true, true, true, true, true, true};
    if (state.status() == handoff::Status::Disabled) {
        if (!nonzero(prior.first_round_id)) {
            observation_.result = ObservationResult::HandoffUnavailable;
            return observation_;
        }
        seed_.canonical = prior.canonical;
        seed_.first_round_id = prior.first_round_id;
        seed_.tokens = *read->definitions_;
        seed_.qualification = qualification;
        if (!state.initialize(true, seed_)) {
            observation_.result = ObservationResult::HandoffUnavailable;
            return observation_;
        }
    }
    if (state.status() != handoff::Status::Sealed ||
        state.reservation().frontier != prior.canonical) {
        observation_.result = ObservationResult::HandoffUnavailable;
        retire_live(state);
        return observation_;
    }
    if (!state.adopt_round(prior.canonical, qualification)) {
        observation_.result = ObservationResult::HandoffUnavailable;
        return observation_;
    }

    seam_.actual_current = prior.canonical;
    seam_.qualification = qualification;
    seam_.request_rbp = registers.gpr[Rbp];
    seam_.original_outer_rsp = registers.gpr[Rsp];
    const auto& facts = observation_.facts;
    seam_.positive_pld_policy = facts.positive_pld_policy;
    seam_.no_sampler = facts.no_sampler;
    seam_.no_suppression = facts.no_suppression;
    seam_.positive_width = facts.positive_width;
    seam_.sufficient_context = facts.sufficient_context;
    seam_.no_constraints = facts.no_constraints;
    seam_.opening_gate_eligible = facts.opening_gate_eligible;
    seam_.native_allowance = facts.native_allowance;
    projected_.gpr = registers.gpr;
    projected_.rflags = registers.ordinary_rflags;
    projected_.outer_stack.fill(0);
    projected_.opaque_extended_state.fill(0);
    observation_.stock_decision = state.consume_at_seam(seam_, nullptr, projected_);
    observation_.handoff_consumed = true;
    observation_.result = ObservationResult::ObservedStock;
    // Deliberately discard the projected LEA change. The real relay restores its
    // own image, replays the actual LEA and resumes the direct stock continuation.
    return observation_;
}

} // namespace halogen_nohit::owner_capture
