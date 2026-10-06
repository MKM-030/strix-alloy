#include "seam_contract.h"

namespace halogen_nohit {
namespace {

static_assert(kHeaderBytes + 4 * kMaxIds + kDigestBytes == kMaxPacketBytes);
static_assert(kSeamRva + kDisplacedLea.size() == kStockResumeRva);
static_assert(kProposalOffset + 4 * kMaxIds <= SavedFrame{}.outer_stack.size());

std::uint32_t read32(const std::uint8_t* bytes) noexcept {
    std::uint32_t value = 0;
    for (std::size_t i = 0; i < 4; ++i) {
        value |= static_cast<std::uint32_t>(bytes[i]) << (8 * i);
    }
    return value;
}

std::uint64_t read64(const std::uint8_t* bytes) noexcept {
    std::uint64_t value = 0;
    for (std::size_t i = 0; i < 8; ++i) {
        value |= static_cast<std::uint64_t>(bytes[i]) << (8 * i);
    }
    return value;
}

template <std::size_t N>
bool nonzero(const std::array<std::uint8_t, N>& value) noexcept {
    std::uint8_t any = 0;
    for (const auto byte : value) { any |= byte; }
    return any != 0;
}

template <std::size_t N>
bool matches(const std::uint8_t* bytes,
             const std::array<std::uint8_t, N>& value) noexcept {
    for (std::size_t i = 0; i < N; ++i) {
        if (bytes[i] != value[i]) { return false; }
    }
    return true;
}

bool valid_binding(const Binding& b) noexcept {
    return nonzero(b.key_id) && nonzero(b.model) && nonzero(b.tokenizer) &&
        nonzero(b.birth_nonce) && nonzero(b.round_id) && nonzero(b.prefix_fingerprint) &&
        b.prefix_length > 0 && b.target_position > 0 && b.current_id >= 0 &&
        b.window_origin < b.prefix_length &&
        b.prefix_length - b.window_origin <= kMaxWindowTokens;
}

bool defined(const TokenDefinitions& tokens, std::uint32_t id) noexcept {
    return id < tokens.id_limit &&
        (tokens.defined_bits[id / 8] & (1U << (id % 8))) != 0;
}

Decision decline(SavedFrame& frame, Reason reason) noexcept {
    // LEA is 64-bit modular addition and leaves every flag unchanged.
    frame.gpr[Rax] = frame.gpr[Rbp] + 0x1e8;
    return {kStockResumeRva, reason, 0, false};
}

} // namespace

Decision consume(const CallerTruth& current,
                 const TrustedAuthenticatedFrame* packet,
                 OneShotLedger& ledger, SavedFrame& frame) noexcept {
    if (!current.enabled) { return decline(frame, Reason::Disabled); }
    if (packet == nullptr) { return decline(frame, Reason::Absent); }
    if (!current.ownership_qualified || !current.birth_reset_qualified ||
        !current.context_current || current.context_epoch == 0 ||
        current.request_rbp == 0 || current.original_outer_rsp == 0 ||
        current.request_rbp != frame.gpr[Rbp] ||
        current.original_outer_rsp != frame.gpr[Rsp] ||
        !valid_binding(current.binding) || current.tokens.id_limit == 0 ||
        current.tokens.id_limit > kMaxTokenIds) {
        return decline(frame, Reason::CallerTruthUnavailable);
    }
    if (!current.positive_pld_policy || !current.no_sampler ||
        !current.no_suppression || !current.positive_width ||
        !current.sufficient_context || !current.no_constraints ||
        current.native_allowance <= 0) {
        return decline(frame, Reason::NativeGateDeclined);
    }
    if (!packet->ready || !packet->authentication_qualified || !packet->immutable_owned) {
        return decline(frame, Reason::PublicationUnqualified);
    }
    if (packet->context_epoch != current.context_epoch) {
        return decline(frame, Reason::StaleEpoch);
    }
    if (packet->length < kHeaderBytes + 4 + kDigestBytes ||
        packet->length > kMaxPacketBytes) {
        return decline(frame, Reason::MalformedPacket);
    }
    const auto* bytes = packet->bytes.data();
    constexpr std::array<std::uint8_t, 8> magic{'H','G','N','P','L','D','P','1'};
    const auto count = read32(bytes + 12);
    if (!matches(bytes, magic) || read32(bytes + 8) != 1 ||
        count == 0 || count > kMaxIds ||
        packet->length != kHeaderBytes + 4 * count + kDigestBytes) {
        return decline(frame, Reason::MalformedPacket);
    }
    const auto& b = current.binding;
    if (!matches(bytes + 16, b.key_id) || !matches(bytes + 32, b.model) ||
        !matches(bytes + 64, b.tokenizer) || !matches(bytes + 96, b.birth_nonce) ||
        !matches(bytes + 112, b.round_id) || !matches(bytes + 128, b.prefix_fingerprint) ||
        read64(bytes + 160) != b.prefix_length || read64(bytes + 168) != b.target_position ||
        read32(bytes + 176) != static_cast<std::uint32_t>(b.current_id) ||
        read64(bytes + 180) != b.window_origin) {
        return decline(frame, Reason::BindingMismatch);
    }
    if (read32(bytes + 188) != b.prefix_length - b.window_origin) {
        return decline(frame, Reason::MalformedPacket);
    }
    // Authentication of the trailing 32 bytes belongs to the trusted boundary.
    // All fields and all IDs are still independently checked before mutation.
    if (!defined(current.tokens, static_cast<std::uint32_t>(b.current_id))) {
        return decline(frame, Reason::UndefinedToken);
    }
    std::array<std::uint32_t, kMaxIds> ids{};
    for (std::size_t i = 0; i < count; ++i) {
        ids[i] = read32(bytes + kHeaderBytes + 4 * i);
        // id_limit <= 248070 makes every negative int32 encoding out of range.
        if (!defined(current.tokens, ids[i])) {
            return decline(frame, Reason::UndefinedToken);
        }
    }
    const auto allowance = static_cast<std::uint32_t>(current.native_allowance);
    const auto cap = allowance < kMaxIds ? allowance : kMaxIds;
    if (count > cap) { return decline(frame, Reason::CountExceedsAllowance); }
    if (ledger.used > kMaxRounds) { return decline(frame, Reason::LedgerExhausted); }
    for (std::size_t i = 0; i < ledger.used; ++i) {
        const auto& used = ledger.rounds[i];
        if (used.birth_nonce == b.birth_nonce && used.context_epoch == current.context_epoch &&
            used.round_id == b.round_id) {
            return decline(frame, Reason::RoundUsed);
        }
    }
    if (ledger.used == kMaxRounds) { return decline(frame, Reason::LedgerExhausted); }

    // Commit only after the final validation. Fixed owned storage and exclusive
    // caller ownership make these writes nonthrowing; no callback can intervene.
    ledger.rounds[ledger.used] = {b.birth_nonce, current.context_epoch, b.round_id};
    ++ledger.used;
    for (std::size_t i = 0; i < count; ++i) {
        for (std::size_t byte = 0; byte < 4; ++byte) {
            frame.outer_stack[kProposalOffset + 4 * i + byte] =
                static_cast<std::uint8_t>(ids[i] >> (8 * byte));
        }
    }
    frame.gpr[Rbx] = count;
    return {kProposalJoinRva, Reason::Selected, static_cast<std::uint8_t>(count), true};
}

} // namespace halogen_nohit
