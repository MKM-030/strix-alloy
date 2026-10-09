#pragma once

// Source-only Linux x86-64 SysV relay templates. These templates are inert:
// every copied branch displacement and configuration must be fixed and checked
// by the exact-image startup installer before any native entry is published.
#define HGN_SHADOW_RED_ZONE 128
#define HGN_SHADOW_FRAME_BYTES 136
#define HGN_SHADOW_CAPTURE_RESERVE 264
#define HGN_SHADOW_XSAVE_PAD 128
#define HGN_SHADOW_CFG_ENABLED 0
#define HGN_SHADOW_CFG_XSAVE_BYTES 4
#define HGN_SHADOW_CFG_XCR0 8
#define HGN_SHADOW_CFG_REQUIRED_STACK 16
#define HGN_SHADOW_CFG_STACK_TLS_OFFSET 24
#define HGN_SHADOW_CFG_CALLBACK 32
#define HGN_SHADOW_CFG_LOSS_COUNTER 40
#define HGN_SHADOW_CFG_RUNTIME_ENABLED 48
#define HGN_SHADOW_CFG_IN_FLIGHT 56
#define HGN_SHADOW_CFG_BYTES 64
#define HGN_SHADOW_TLS_STACK_LOW 0
#define HGN_SHADOW_TLS_STACK_HIGH 8
#define HGN_SHADOW_TLS_STACK_BYTES 16
#define HGN_SHADOW_REPLAY_BYTES 16
#define HGN_SHADOW_REL32_SENTINEL 0x5a17c0de
#define HGN_SHADOW_HANDLER_CFA 0x1a40
#define HGN_SHADOW_ENTRY_CFA 8

#ifndef __ASSEMBLER__
#include <array>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace halogen_shadow::relay {

enum class Site : std::uint32_t {
    BirthA = 0, BirthB = 1, NeuralBegin = 2, PldBegin = 3,
    Outcome = 4, RequestDestructor = 5, Bind = 6, Reset = 7, Release = 8
};
inline constexpr std::size_t kSiteCount = 9;

struct Frame {
    // RAX,RBX,RCX,RDX,RSI,RDI,RBP,original RSP,R8,R9,R10,R11,R12,R13,R14,R15.
    std::array<std::uint64_t, 16> gpr{};
    std::uint64_t ordinary_rflags{}; // PUSHFQ scope; no RF/VM/debug-state promise.
};

// The installer owns initial-exec TLS registration. The relay reads this
// current thread's record through FS + stack_tls_offset after integer capture.
// Registration must finish before the thread can enter a patched site; missing
// or insufficient stack bounds record producer loss while collection is enabled
// and still replay stock code. Disabled collection bypasses without recording loss.
struct StackBounds {
    std::uint64_t low{};
    std::uint64_t high{};
};

using Callback = void (*)(std::uint32_t site, const Frame* frame) noexcept;
struct Configuration {
    std::uint32_t enabled{};
    std::uint32_t xsave_bytes{};
    std::uint64_t xcr0_mask{};
    std::uint64_t required_stack_below_original_rsp{};
    std::int64_t stack_tls_offset{};
    Callback callback{};
    std::uint64_t* loss_counter{};    // Retained native-owned atomic<uint64_t> storage.
    const unsigned char* runtime_enabled{}; // Retained native-owned atomic<bool> storage.
    std::uint64_t* in_flight_counter{}; // Retained native-owned atomic<uint64_t> storage.
};

// Before publication the installer must validate the full enabled standard
// XSAVE mask/extent, the actual retained callback's ENDBR64 entry and ABI, and
// required_stack >= xsave_bytes + 264 + 128 + 63 + complete callback/signal
// budgets. The first 264-byte integer/red-zone reservation is unconditional;
// source admission must establish that minimum headroom for every hook entry.
// No CPUID, lazy TLS lookup, allocator, registration, or errno access occurs in
// copied code. The callback wrapper must save errno before collector work and
// restore it before returning. It must preserve FS/GS, return normally, avoid
// exceptions/nonlocal exit, and retain the DSO and its initial-exec TLS until
// process exit. The Frame and all native borrows expire at callback return.
// A real indirect CALL/RET is balanced for the shadow stack; native onward
// branches are direct rel32 and never use a fabricated return or indirect JMP.
// The installer must establish all three atomic pointers' lifetime, alignment
// and non-null addresses, plus sizeof(atomic<uint64_t>)==8, sizeof(atomic<bool>)==1
// and both types always lock-free. The relay reads enabled with an x86 byte load
// and records stack-admission loss with LOCK INCQ on the eight-byte counter;
// the collector drains this counter into its explicit producer-loss gap state.
// After its first enable read, the relay increments in_flight and rechecks
// enabled before admission or owned updates; every active path decrements it
// after its final owned update. Qualified close must disable the collector,
// wait for in_flight==0, then drain and close. A relay delayed before increment
// must see disabled at its recheck and perform no observation or loss update.

static_assert(std::is_standard_layout_v<Frame> && sizeof(Frame) == HGN_SHADOW_FRAME_BYTES);
static_assert(offsetof(Frame, ordinary_rflags) == 128);
static_assert(sizeof(StackBounds) == HGN_SHADOW_TLS_STACK_BYTES);
static_assert(offsetof(StackBounds, low) == HGN_SHADOW_TLS_STACK_LOW);
static_assert(offsetof(StackBounds, high) == HGN_SHADOW_TLS_STACK_HIGH);
static_assert(std::is_standard_layout_v<Configuration> && sizeof(Configuration) == HGN_SHADOW_CFG_BYTES);
static_assert(offsetof(Configuration, enabled) == HGN_SHADOW_CFG_ENABLED);
static_assert(offsetof(Configuration, xsave_bytes) == HGN_SHADOW_CFG_XSAVE_BYTES);
static_assert(offsetof(Configuration, xcr0_mask) == HGN_SHADOW_CFG_XCR0);
static_assert(offsetof(Configuration, required_stack_below_original_rsp) == HGN_SHADOW_CFG_REQUIRED_STACK);
static_assert(offsetof(Configuration, stack_tls_offset) == HGN_SHADOW_CFG_STACK_TLS_OFFSET);
static_assert(offsetof(Configuration, callback) == HGN_SHADOW_CFG_CALLBACK);
static_assert(offsetof(Configuration, loss_counter) == HGN_SHADOW_CFG_LOSS_COUNTER);
static_assert(offsetof(Configuration, runtime_enabled) == HGN_SHADOW_CFG_RUNTIME_ENABLED);
static_assert(offsetof(Configuration, in_flight_counter) == HGN_SHADOW_CFG_IN_FLIGHT);

} // namespace halogen_shadow::relay

// All nine code/config templates occupy .hgn_shadow_relay_templates and move
// together. Collect .eh_frame from exact shadow_relay.o into the SAME copied
// island; its PC-relative CIE/FDE/code references must retain their offsets.
// The installer locates one FDE by each begin..code_end range, registers the
// entire copied frame envelope, and checks the registered FDE at each relay PC.
// begin..end includes 16-byte replay, final E9, config and masked-MXCSR literal.
// config becomes immutable before entry patch publication. replay_end==resume;
// resume_delta is the E9 disp32 field; branch_delta exists only at sites 4/8.
extern "C" {
extern const unsigned char hgn_shadow_templates_begin[];
extern const unsigned char hgn_shadow_templates_end[];
#define HGN_SHADOW_DECLARE_SITE(n) \
    void hgn_shadow_relay_##n##_begin(); \
    extern const unsigned char hgn_shadow_relay_##n##_code_end[]; \
    extern const unsigned char hgn_shadow_relay_##n##_end[]; \
    extern const halogen_shadow::relay::Configuration hgn_shadow_relay_##n##_config; \
    extern const unsigned char hgn_shadow_relay_##n##_replay[]; \
    extern const unsigned char hgn_shadow_relay_##n##_replay_end[]; \
    extern const unsigned char hgn_shadow_relay_##n##_resume[]; \
    extern const unsigned char hgn_shadow_relay_##n##_resume_delta[];
HGN_SHADOW_DECLARE_SITE(0)
HGN_SHADOW_DECLARE_SITE(1)
HGN_SHADOW_DECLARE_SITE(2)
HGN_SHADOW_DECLARE_SITE(3)
HGN_SHADOW_DECLARE_SITE(4)
HGN_SHADOW_DECLARE_SITE(5)
HGN_SHADOW_DECLARE_SITE(6)
HGN_SHADOW_DECLARE_SITE(7)
HGN_SHADOW_DECLARE_SITE(8)
#undef HGN_SHADOW_DECLARE_SITE
extern const unsigned char hgn_shadow_relay_4_branch_delta[];
extern const unsigned char hgn_shadow_relay_8_branch_delta[];
}
#endif
