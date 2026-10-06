#pragma once

// Shared C++ / preprocessed GNU assembly layout. Linux x86-64 / SysV only.
#define HGN_RELAY_NATIVE_CFA 0x2680
#define HGN_RELAY_RED_ZONE 128
#define HGN_RELAY_CAPTURE_BYTES 136
#define HGN_RELAY_ENTRY_RESERVE 264
#define HGN_RELAY_CAPTURE_CFA 0x2788
#define HGN_RELAY_CFG_ENABLED 0
#define HGN_RELAY_CFG_XSAVE_BYTES 4
#define HGN_RELAY_CFG_XCR0 8
#define HGN_RELAY_CFG_STACK_LOW 16
#define HGN_RELAY_CFG_STACK_HIGH 24
#define HGN_RELAY_CFG_REQUIRED_STACK 32
#define HGN_RELAY_CFG_SCOPE 40
#define HGN_RELAY_VIEW_BYTES 64
#define HGN_RELAY_ALLOC_PAD 128

#ifndef __ASSEMBLER__
#include <array>
#include <cstddef>
#include <cstdint>

namespace halogen_nohit::frame_relay {

inline constexpr std::uint32_t kMaximumXsaveBytes = 65536;
inline constexpr std::uint64_t kRecognizedUserMask = 0x2e7; // x87/SSE/AVX/AVX512/PKRU
inline constexpr std::uint64_t kMaximumCallbackStack = 1024 * 1024;
inline constexpr std::uint64_t kMaximumSignalReserve = 1024 * 1024;

// Same register order as seam_contract.h, but REAL saved registers on this
// invocation's stack. No native pointer is dereferenced by the relay callback API.
struct RegisterImage {
    std::array<std::uint64_t, 16> gpr{}; // RAX,RBX,RCX,RDX,RSI,RDI,RBP,RSP,R8..R15
    std::uint64_t ordinary_rflags{}; // PUSHFQ image; RF/VM/privileged/debug scope excluded.
};

enum class XsaveScope : std::uint64_t {
    ArchitecturalUserState = 1,
    LiteralPhysicalX87Metadata = 2 // Refused for every vendor in this first core.
};

struct NativeFrameView {
    const RegisterImage* registers{};
    const void* standard_xsave_area{};
    std::uint64_t xcr0_mask{};
    std::uint64_t xsave_bytes{};
    std::uint64_t original_rsp{};
    XsaveScope scope{};
};

enum class Vendor : std::uint32_t { Unknown, Intel, Amd };
struct ComponentExtent {
    std::uint32_t bytes{};
    std::uint32_t standard_offset{};
    std::uint32_t flags{};
};

// No lazy initialization. An owner may publish an immutable validated candidate
// ONLY while no thread can enter the relay. This source has no installer and no
// mechanism that proves stack mappings, signal policy or CPU migration safety.
struct RelayConfiguration {
    std::uint32_t enabled{};
    std::uint32_t xsave_bytes{};
    std::uint64_t xcr0_mask{};
    std::uint64_t registered_stack_low{};
    std::uint64_t registered_stack_high{};
    std::uint64_t required_stack_below_original_rsp{};
    XsaveScope scope = XsaveScope::ArchitecturalUserState;
    Vendor vendor{};
    std::uint32_t family{};
    std::uint32_t model{};
    std::uint32_t stepping{};
    std::uint64_t supported_user_mask{};
    std::uint32_t cpuid_d1_eax{};
    std::uint32_t amd_cpuid_80000008_ebx{};
    std::array<ComponentExtent, 64> components{};
};

struct StartupRequest {
    bool enable = false;
    XsaveScope scope = XsaveScope::ArchitecturalUserState;
    std::uint64_t registered_stack_low{};
    std::uint64_t registered_stack_high{};
    // Complete observer call tree + its red zone/return frames; source-reviewed.
    std::uint64_t callback_stack_budget{};
    // Actual Linux signal-frame/handler headroom, supplied by startup owner.
    std::uint64_t signal_reserve{};
};

enum class ConfigurationResult : std::uint8_t {
    Disabled, ArchitecturalCandidate, UnsupportedPlatform, UnsupportedVendor,
    XsaveUnavailable, InvalidXcr0, UnsupportedComponent, InvalidComponentExtent,
    InvalidAreaSize, AmdErrorPointersUnsupported, LiteralMetadataUnsupported,
    InvalidScope, InvalidStackBudget
};

// Source-only CPUID/XGETBV discovery, no syscall/allocator/lock/runtime. Returned
// candidate is not a native qualification or proof of its supplied stack bounds.
ConfigurationResult discover_configuration(const StartupRequest& request,
                                           RelayConfiguration& candidate) noexcept;

static_assert(sizeof(RegisterImage) == HGN_RELAY_CAPTURE_BYTES);
static_assert(offsetof(RegisterImage, ordinary_rflags) == 128);
static_assert(sizeof(NativeFrameView) <= HGN_RELAY_VIEW_BYTES);
static_assert(offsetof(RelayConfiguration, enabled) == HGN_RELAY_CFG_ENABLED);
static_assert(offsetof(RelayConfiguration, xsave_bytes) == HGN_RELAY_CFG_XSAVE_BYTES);
static_assert(offsetof(RelayConfiguration, xcr0_mask) == HGN_RELAY_CFG_XCR0);
static_assert(offsetof(RelayConfiguration, registered_stack_low) == HGN_RELAY_CFG_STACK_LOW);
static_assert(offsetof(RelayConfiguration, registered_stack_high) == HGN_RELAY_CFG_STACK_HIGH);
static_assert(offsetof(RelayConfiguration, required_stack_below_original_rsp) == HGN_RELAY_CFG_REQUIRED_STACK);
static_assert(offsetof(RelayConfiguration, scope) == HGN_RELAY_CFG_SCOPE);
} // namespace halogen_nohit::frame_relay

extern "C" {
extern halogen_nohit::frame_relay::RelayConfiguration halogen_nohit_relay_configuration;
// JMP entry, NEVER a normal function call; original native body CFA is required.
void halogen_nohit_native_frame_relay();
// Required hidden, directly linked C/SysV observer, balanced normal CALL/RET.
// It may inspect only the owned image/view, must not mutate them or native
// objects, change FS/GS/process state, reenter serving or exit nonlocally.
void halogen_nohit_frame_observer(const halogen_nohit::frame_relay::NativeFrameView*) noexcept;
// Required hidden link-time direct continuation symbol. Future near-engine
// placement must resolve it to stock RVA0x172d3c4, or an ENDBR pad whose only
// onward branch is direct. No absolute/indirect interior-jump fallback exists.
void halogen_nohit_native_stock_resume();
}
#endif
