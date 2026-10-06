#include "seam_contract.h"

#include <cstdio>

using namespace halogen_nohit;

namespace {
int failures = 0;

void check(bool value, const char* explanation) {
    if (!value) {
        std::printf("FAIL: %s\n", explanation);
        ++failures;
    }
}

template <std::size_t N>
void fill_tag(std::array<std::uint8_t, N>& tag, std::uint8_t seed) {
    for (std::size_t i = 0; i < N; ++i) {
        tag[i] = static_cast<std::uint8_t>(seed + i);
    }
}

void write32(std::uint8_t* out, std::uint32_t value) {
    for (std::size_t i = 0; i < 4; ++i) {
        out[i] = static_cast<std::uint8_t>(value >> (8 * i));
    }
}

void write64(std::uint8_t* out, std::uint64_t value) {
    for (std::size_t i = 0; i < 8; ++i) {
        out[i] = static_cast<std::uint8_t>(value >> (8 * i));
    }
}

template <std::size_t N>
void write_tag(std::uint8_t* out, const std::array<std::uint8_t, N>& tag) {
    for (std::size_t i = 0; i < N; ++i) {
        out[i] = tag[i];
    }
}

SavedFrame initial_frame() {
    SavedFrame frame{};
    for (std::size_t i = 0; i < frame.gpr.size(); ++i) {
        frame.gpr[i] = 0x1020304050607080ULL + i * 0x111111111111111ULL;
    }
    frame.gpr[Rbp] = 0x0000000102030400ULL;
    frame.gpr[Rsp] = 0x0000000203040500ULL;
    frame.rflags = 0x2ed7;
    for (std::size_t i = 0; i < frame.outer_stack.size(); ++i) {
        frame.outer_stack[i] = static_cast<std::uint8_t>(i * 17 + 13);
    }
    for (std::size_t i = 0; i < frame.opaque_extended_state.size(); ++i) {
        frame.opaque_extended_state[i] = static_cast<std::uint8_t>(i * 11 + 91);
    }
    return frame;
}

CallerTruth qualified_truth(const SavedFrame& frame) {
    CallerTruth current{};
    current.enabled = true;
    current.ownership_qualified = true;
    current.birth_reset_qualified = true;
    current.context_current = true;
    current.positive_pld_policy = true;
    current.no_sampler = true;
    current.no_suppression = true;
    current.positive_width = true;
    current.sufficient_context = true;
    current.no_constraints = true;
    current.native_allowance = 3;
    current.context_epoch = 17;
    current.request_rbp = frame.gpr[Rbp];
    current.original_outer_rsp = frame.gpr[Rsp];
    auto& binding = current.binding;
    fill_tag(binding.key_id, 1);
    fill_tag(binding.model, 21);
    fill_tag(binding.tokenizer, 61);
    fill_tag(binding.birth_nonce, 111);
    fill_tag(binding.round_id, 131);
    fill_tag(binding.prefix_fingerprint, 151);
    binding.prefix_length = 293;
    binding.target_position = 294;
    binding.current_id = 42;
    binding.window_origin = 37;
    current.tokens.id_limit = 512;
    current.tokens.defined_bits.fill(0xff);
    return current;
}

TrustedAuthenticatedFrame trusted_packet(const CallerTruth& current) {
    TrustedAuthenticatedFrame packet{};
    // Synthetic trust assumption: these digest bytes are not a valid HMAC.
    // The native consumer MUST NOT claim it authenticated this fixture.
    packet.bytes.fill(0xa5);
    const std::array<std::uint8_t, 8> magic{'H','G','N','P','L','D','P','1'};
    write_tag(packet.bytes.data(), magic);
    write32(packet.bytes.data() + 8, 1);
    write32(packet.bytes.data() + 12, 3);
    const auto& b = current.binding;
    write_tag(packet.bytes.data() + 16, b.key_id);
    write_tag(packet.bytes.data() + 32, b.model);
    write_tag(packet.bytes.data() + 64, b.tokenizer);
    write_tag(packet.bytes.data() + 96, b.birth_nonce);
    write_tag(packet.bytes.data() + 112, b.round_id);
    write_tag(packet.bytes.data() + 128, b.prefix_fingerprint);
    write64(packet.bytes.data() + 160, b.prefix_length);
    write64(packet.bytes.data() + 168, b.target_position);
    write32(packet.bytes.data() + 176, static_cast<std::uint32_t>(b.current_id));
    write64(packet.bytes.data() + 180, b.window_origin);
    write32(packet.bytes.data() + 188,
            static_cast<std::uint32_t>(b.prefix_length - b.window_origin));
    write32(packet.bytes.data() + 192, 43);
    write32(packet.bytes.data() + 196, 300);
    write32(packet.bytes.data() + 200, 511);
    packet.length = 236;
    packet.context_epoch = current.context_epoch;
    packet.ready = true;
    packet.authentication_qualified = true;
    packet.immutable_owned = true;
    return packet;
}

bool same_frame(const SavedFrame& a, const SavedFrame& b) {
    return a.gpr == b.gpr && a.rflags == b.rflags &&
        a.outer_stack == b.outer_stack &&
        a.opaque_extended_state == b.opaque_extended_state;
}

bool same_ledger(const OneShotLedger& a, const OneShotLedger& b) {
    if (a.used != b.used) { return false; }
    for (std::size_t i = 0; i < kMaxRounds; ++i) {
        if (a.rounds[i].birth_nonce != b.rounds[i].birth_nonce ||
            a.rounds[i].context_epoch != b.rounds[i].context_epoch ||
            a.rounds[i].round_id != b.rounds[i].round_id) { return false; }
    }
    return true;
}

// Independent byte-level oracle for retained 48 8d 85 e8 01 00 00.
SavedFrame stock_lea(const SavedFrame& before) {
    const std::array<std::uint8_t, 7> retained{0x48,0x8d,0x85,0xe8,0x01,0x00,0x00};
    std::uint32_t displacement = 0;
    for (std::size_t i = 0; i < 4; ++i) {
        displacement |= static_cast<std::uint32_t>(retained[i + 3]) << (8 * i);
    }
    auto after = before;
    after.gpr[Rax] = before.gpr[Rbp] + displacement;
    return after;
}

std::uint32_t continue_stock(SavedFrame& frame) {
    // MOV [RSP+38],RAX; XOR R13D,R13D; MOV R12D,R13D;
    // TEST R13D,R13D; JLE 172d5ca. Ignore architecturally undefined AF.
    write64(frame.outer_stack.data() + 0x38, frame.gpr[Rax]);
    frame.gpr[R13] = 0;
    frame.gpr[R12] = 0;
    constexpr std::uint64_t defined = (1ULL << 0) | (1ULL << 2) |
        (1ULL << 6) | (1ULL << 7) | (1ULL << 11);
    frame.rflags = (frame.rflags & ~defined) | (1ULL << 2) | (1ULL << 6);
    return 0x172d5ca;
}

void require_decline(const CallerTruth& current,
                     const TrustedAuthenticatedFrame* packet,
                     Reason reason, const char* explanation,
                     OneShotLedger* existing = nullptr) {
    OneShotLedger local{};
    auto& ledger = existing == nullptr ? local : *existing;
    const auto before_ledger = ledger;
    auto frame = initial_frame();
    const auto before = frame;
    const auto result = consume(current, packet, ledger, frame);
    check(!result.selected && result.count == 0 && result.reason == reason &&
          result.resume_rva == 0x172d3c4, explanation);
    check(same_frame(frame, stock_lea(before)), "decline changes only the displaced LEA RAX");
    check(same_ledger(ledger, before_ledger), "decline does not consume or alter any ledger entry");
}

void stock_cases() {
    auto frame = initial_frame();
    auto truth = qualified_truth(frame);
    const auto packet = trusted_packet(truth);
    CallerTruth default_truth{};
    require_decline(default_truth, &packet, Reason::Disabled, "mode defaults off");
    require_decline(truth, nullptr, Reason::Absent, "absent packet resumes stock");
    truth.enabled = false;
    require_decline(truth, &packet, Reason::Disabled, "disabled ready packet resumes stock");
    OneShotLedger ledger{};
    auto independent = stock_lea(frame);
    (void)consume(truth, &packet, ledger, frame);
    check(continue_stock(frame) == 0x172d5ca &&
          continue_stock(independent) == 0x172d5ca && same_frame(frame, independent),
          "decline preserves the stock store/zero-count/TEST branch continuation");
    frame = initial_frame();
    frame.gpr[Rbp] = 0xfffffffffffffff0ULL;
    (void)consume(default_truth, nullptr, ledger, frame);
    check(frame.gpr[Rax] == 0x1d8, "LEA follows native unsigned 64-bit wrap");
}

void validation_cases() {
    const auto frame = initial_frame();
    const auto truth = qualified_truth(frame);
    const auto valid = trusted_packet(truth);
    auto packet = valid;
    write32(packet.bytes.data() + 188, 255);
    require_decline(truth, &packet, Reason::MalformedPacket, "last header field is validated before writes");
    packet = valid;
    write32(packet.bytes.data() + 200, 0xffffffffU);
    require_decline(truth, &packet, Reason::UndefinedToken, "negative last ID causes no partial write");
    packet = valid;
    write32(packet.bytes.data() + 200, 512);
    require_decline(truth, &packet, Reason::UndefinedToken, "last ID must be below caller token limit");
    auto current = truth;
    current.tokens.defined_bits[511 / 8] &= static_cast<std::uint8_t>(~(1U << (511 % 8)));
    require_decline(current, &valid, Reason::UndefinedToken, "last ID requires explicit token definition");
    packet = valid;
    packet.length = 235;
    require_decline(truth, &packet, Reason::MalformedPacket, "exact length forbids truncated digest extent");
    packet = valid;
    write32(packet.bytes.data() + 12, 4);
    require_decline(truth, &packet, Reason::MalformedPacket, "count four is rejected without truncation");
    for (const std::size_t offset : {16U, 32U, 64U, 96U, 112U, 128U, 160U, 168U, 176U, 180U}) {
        packet = valid;
        packet.bytes[offset] ^= 1;
        require_decline(truth, &packet, Reason::BindingMismatch, "every key/model/birth/round/prefix binding matches caller");
    }
    packet = valid;
    packet.authentication_qualified = false;
    require_decline(truth, &packet, Reason::PublicationUnqualified, "authentication cannot be inferred from frame bytes");
    packet = valid;
    packet.ready = false;
    require_decline(truth, &packet, Reason::PublicationUnqualified, "incomplete publication resumes immediately");
    packet = valid;
    packet.immutable_owned = false;
    require_decline(truth, &packet, Reason::PublicationUnqualified, "mutable publication is declined");
    current = truth;
    current.native_allowance = 0;
    require_decline(current, &valid, Reason::NativeGateDeclined, "zero B declines");
    current.native_allowance = -1;
    require_decline(current, &valid, Reason::NativeGateDeclined, "negative B declines");
    for (bool CallerTruth::* flag : {&CallerTruth::positive_pld_policy, &CallerTruth::no_sampler,
            &CallerTruth::no_suppression, &CallerTruth::positive_width,
            &CallerTruth::sufficient_context, &CallerTruth::no_constraints}) {
        current = truth;
        current.*flag = false;
        require_decline(current, &valid, Reason::NativeGateDeclined, "all native policy/context/constraint facts are explicit");
    }
    for (bool CallerTruth::* flag : {&CallerTruth::ownership_qualified,
            &CallerTruth::birth_reset_qualified, &CallerTruth::context_current}) {
        current = truth;
        current.*flag = false;
        require_decline(current, &valid, Reason::CallerTruthUnavailable, "unknown ownership/reset/currentness declines");
    }
    current = truth;
    ++current.original_outer_rsp;
    require_decline(current, &valid, Reason::CallerTruthUnavailable, "destination binds to original outer RSP");
    current = truth;
    ++current.request_rbp;
    require_decline(current, &valid, Reason::CallerTruthUnavailable, "request binds to saved RBP");
}

void successful_cases() {
    const auto before = initial_frame();
    auto current = qualified_truth(before);
    auto packet = trusted_packet(current);
    OneShotLedger ledger{};
    auto frame = before;
    const auto result = consume(current, &packet, ledger, frame);
    auto expected = before;
    expected.gpr[Rbx] = 3;
    const std::array<std::uint8_t, 12> expected_ids{43,0,0,0,44,1,0,0,255,1,0,0};
    for (std::size_t i = 0; i < expected_ids.size(); ++i) {
        expected.outer_stack[0x360 + i] = expected_ids[i];
    }
    check(result.selected && result.reason == Reason::Selected && result.count == 3 &&
          result.resume_rva == 0x172e95f, "valid three-ID packet reaches existing proposal join");
    check(same_frame(frame, expected), "success writes exactly 12 ID bytes and RBX, preserving canaries and all other state");
    check(ledger.used == 1 && ledger.rounds[0].birth_nonce == current.binding.birth_nonce &&
          ledger.rounds[0].context_epoch == 17 && ledger.rounds[0].round_id == current.binding.round_id,
          "success records the birth/epoch/round exactly once");
    current.native_allowance = 2;
    require_decline(current, &packet, Reason::CountExceedsAllowance, "count is capped by min(3,B)");
    current.native_allowance = 1;
    write32(packet.bytes.data() + 12, 1);
    packet.length = 228;
    frame = before;
    ledger = {};
    const auto one = consume(current, &packet, ledger, frame);
    expected = before;
    expected.gpr[Rbx] = 1;
    for (std::size_t i = 0; i < 4; ++i) { expected.outer_stack[0x360 + i] = expected_ids[i]; }
    check(one.selected && one.count == 1 && same_frame(frame, expected),
          "one-ID packet changes only four bytes even with adjacent nonzero data");
}

void epoch_and_one_shot_cases() {
    const auto before = initial_frame();
    auto current = qualified_truth(before);
    const auto packet = trusted_packet(current);
    auto stale = packet;
    --stale.context_epoch;
    require_decline(current, &stale, Reason::StaleEpoch, "old envelope epoch is declined");
    current.context_epoch = 0;
    require_decline(current, &packet, Reason::CallerTruthUnavailable, "unknown current epoch is declined");
    current = qualified_truth(before);
    OneShotLedger ledger{};
    auto frame = before;
    (void)consume(current, &packet, ledger, frame);
    require_decline(current, &packet, Reason::RoundUsed, "successful packet cannot be used twice", &ledger);
    ledger = {};
    ledger.used = kMaxRounds;
    require_decline(current, &packet, Reason::LedgerExhausted, "finite ledger exhaustion declines without eviction", &ledger);
}
} // namespace

int main() {
    stock_cases();
    validation_cases();
    successful_cases();
    epoch_and_one_shot_cases();
    std::printf("four contract groups: %s (%d failed checks)\n", failures == 0 ? "PASS" : "FAIL", failures);
    return failures == 0 ? 0 : 1;
}
