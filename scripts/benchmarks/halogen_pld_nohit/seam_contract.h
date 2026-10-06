#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace halogen_nohit {

inline constexpr std::size_t kHeaderBytes = 192;
inline constexpr std::size_t kDigestBytes = 32;
inline constexpr std::size_t kMaxIds = 3;
inline constexpr std::size_t kMaxPacketBytes = 236;
inline constexpr std::size_t kMaxRounds = 64;
inline constexpr std::size_t kMaxWindowTokens = 512;
inline constexpr std::uint32_t kMaxTokenIds = 248070;
inline constexpr std::size_t kProposalOffset = 0x360;
inline constexpr std::uint32_t kSeamRva = 0x172d3bd;
inline constexpr std::uint32_t kStockResumeRva = 0x172d3c4;
inline constexpr std::uint32_t kProposalJoinRva = 0x172e95f;
inline constexpr std::array<std::uint8_t, 7> kDisplacedLea{
    0x48, 0x8d, 0x85, 0xe8, 0x01, 0x00, 0x00};

enum Register : std::size_t {
    Rax, Rbx, Rcx, Rdx, Rsi, Rdi, Rbp, Rsp,
    R8, R9, R10, R11, R12, R13, R14, R15
};

// A synthetic saved frame, never an engine pointer or an XSAVE qualification.
struct SavedFrame {
    std::array<std::uint64_t, 16> gpr{};
    std::uint64_t rflags{};
    std::array<std::uint8_t, 0x380> outer_stack{};
    std::array<std::uint8_t, 1024> opaque_extended_state{};
};

struct Binding {
    std::array<std::uint8_t, 16> key_id{};
    std::array<std::uint8_t, 32> model{};
    std::array<std::uint8_t, 32> tokenizer{};
    std::array<std::uint8_t, 16> birth_nonce{};
    std::array<std::uint8_t, 16> round_id{};
    std::array<std::uint8_t, 32> prefix_fingerprint{};
    std::uint64_t prefix_length{};
    std::uint64_t target_position{};
    std::int32_t current_id{};
    std::uint64_t window_origin{};
};

struct TokenDefinitions {
    std::uint32_t id_limit{}; // Exclusive, from the trusted tokenizer mapping.
    std::array<std::uint8_t, (kMaxTokenIds + 7) / 8> defined_bits{};
};

// Every fact is authoritative caller truth, immutable during consume().
// The caller owns serialization, reset exclusion and all supplied lifetimes.
struct CallerTruth {
    bool enabled = false;
    bool ownership_qualified = false;
    bool birth_reset_qualified = false;
    bool context_current = false;
    bool positive_pld_policy = false;
    bool no_sampler = false;
    bool no_suppression = false;
    bool positive_width = false;
    bool sufficient_context = false;
    bool no_constraints = false;
    std::int32_t native_allowance{}; // Checked B from the native gate.
    std::uint64_t context_epoch{};
    std::uint64_t request_rbp{};
    std::uint64_t original_outer_rsp{};
    Binding binding{};
    TokenDefinitions tokens{};
};

// Upstream MUST authenticate the complete header + IDs against the trailing
// HMAC, validate key trust and provide an owned immutable publication. This
// consumer does not perform cryptography. Epoch is an authenticated/trusted
// envelope fact; it is deliberately absent from the existing wire header.
struct TrustedAuthenticatedFrame {
    std::array<std::uint8_t, kMaxPacketBytes> bytes{};
    std::size_t length{};
    std::uint64_t context_epoch{};
    bool ready = false;
    bool authentication_qualified = false;
    bool immutable_owned = false;
};

struct UsedRound {
    std::array<std::uint8_t, 16> birth_nonce{};
    std::uint64_t context_epoch{};
    std::array<std::uint8_t, 16> round_id{};
};

// Exclusive caller ownership is required. Never evict an entry to admit a
// replay; a new ledger requires retirement of every packet from the old birth.
struct OneShotLedger {
    std::array<UsedRound, kMaxRounds> rounds{};
    std::size_t used{};
};

enum class Reason : std::uint8_t {
    Selected, Disabled, Absent, CallerTruthUnavailable, NativeGateDeclined,
    PublicationUnqualified, StaleEpoch, MalformedPacket, BindingMismatch,
    UndefinedToken, CountExceedsAllowance, RoundUsed, LedgerExhausted
};

struct Decision {
    std::uint32_t resume_rva{};
    Reason reason{};
    std::uint8_t count{};
    bool selected{};
};

// Fixed storage, no callbacks, allocator, lock, wait, runtime or transport.
// Every decline replays LEA RAX,[RBP+0x1e8] and changes nothing else.
// Success changes only stack[0x360..0x360+4*n) and saved RBX, after all checks.
Decision consume(const CallerTruth& current,
                 const TrustedAuthenticatedFrame* packet,
                 OneShotLedger& ledger, SavedFrame& frame) noexcept;

} // namespace halogen_nohit
