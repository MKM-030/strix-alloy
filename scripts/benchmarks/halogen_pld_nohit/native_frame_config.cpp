#include "native_frame_relay.h"

#if !defined(__linux__) || !defined(__x86_64__) || !(defined(__GNUC__) || defined(__clang__))
#error "native frame configuration requires Linux x86-64 GCC/Clang"
#endif

extern "C" {
__attribute__((visibility("hidden")))
halogen_nohit::frame_relay::RelayConfiguration halogen_nohit_relay_configuration{};
}

namespace halogen_nohit::frame_relay {
namespace {
struct Cpuid { std::uint32_t a, b, c, d; };
Cpuid cpuid(std::uint32_t leaf, std::uint32_t subleaf = 0) noexcept {
    Cpuid result{};
    __asm__ volatile("cpuid" : "=a"(result.a), "=b"(result.b), "=c"(result.c), "=d"(result.d)
                     : "a"(leaf), "c"(subleaf));
    return result;
}
std::uint64_t xgetbv0() noexcept {
    std::uint32_t low = 0, high = 0;
    __asm__ volatile("xgetbv" : "=a"(low), "=d"(high) : "c"(0));
    return low | (static_cast<std::uint64_t>(high) << 32);
}
bool overlap(const ComponentExtent& a, const ComponentExtent& b) noexcept {
    return a.standard_offset < b.standard_offset + b.bytes &&
        b.standard_offset < a.standard_offset + a.bytes;
}
} // namespace

ConfigurationResult discover_configuration(const StartupRequest& request,
                                           RelayConfiguration& candidate) noexcept {
    candidate = {};
    if (!request.enable) { return ConfigurationResult::Disabled; }
    if (request.scope == XsaveScope::LiteralPhysicalX87Metadata) {
        return ConfigurationResult::LiteralMetadataUnsupported;
    }
    if (request.scope != XsaveScope::ArchitecturalUserState) { return ConfigurationResult::InvalidScope; }
    const auto base = cpuid(0);
    if (base.a < 0xd) { return ConfigurationResult::XsaveUnavailable; }
    if (base.b == 0x68747541 && base.d == 0x69746e65 && base.c == 0x444d4163) {
        candidate.vendor = Vendor::Amd;
    } else if (base.b == 0x756e6547 && base.d == 0x49656e69 && base.c == 0x6c65746e) {
        candidate.vendor = Vendor::Intel;
    } else { return ConfigurationResult::UnsupportedVendor; }
    const auto features = cpuid(1);
    const auto base_family = (features.a >> 8) & 0xf;
    candidate.family = base_family + (base_family == 0xf ? ((features.a >> 20) & 0xff) : 0);
    candidate.model = (features.a >> 4) & 0xf;
    if (base_family == 0x6 || base_family == 0xf) { candidate.model |= ((features.a >> 16) & 0xf) << 4; }
    candidate.stepping = features.a & 0xf;
    constexpr std::uint32_t required = (1U << 26) | (1U << 27); // XSAVE + OSXSAVE
    if ((features.c & required) != required) { return ConfigurationResult::XsaveUnavailable; }
    // XGETBV executes only after CPUID proves the OS has enabled its instruction.
    candidate.xcr0_mask = xgetbv0();
    const auto area = cpuid(0xd, 0);
    candidate.supported_user_mask = area.a | (static_cast<std::uint64_t>(area.d) << 32);
    if ((candidate.xcr0_mask & 3) != 3 || (candidate.xcr0_mask & ~candidate.supported_user_mask) != 0) {
        return ConfigurationResult::InvalidXcr0;
    }
    // Reject AMX/XFD, APX extra GPRs, MPX and unknown user state rather than
    // assuming their process permissions, C ABI or mutation behavior is safe.
    if ((candidate.xcr0_mask & ~kRecognizedUserMask) != 0) { return ConfigurationResult::UnsupportedComponent; }
    constexpr std::uint64_t avx512 = (1ULL << 5) | (1ULL << 6) | (1ULL << 7);
    if ((candidate.xcr0_mask & avx512) != 0 &&
        ((candidate.xcr0_mask & avx512) != avx512 || (candidate.xcr0_mask & (1ULL << 2)) == 0)) {
        return ConfigurationResult::InvalidXcr0;
    }
    candidate.xsave_bytes = area.b; // Enabled XCR0 standard-format extent.
    if (area.b < 576 || area.b > kMaximumXsaveBytes || area.b > area.c) {
        return ConfigurationResult::InvalidAreaSize;
    }
    candidate.cpuid_d1_eax = cpuid(0xd, 1).a;
    for (std::uint32_t bit = 2; bit < 64; ++bit) {
        if ((candidate.xcr0_mask & (1ULL << bit)) == 0) { continue; }
        const auto component = cpuid(0xd, bit);
        // ECX0=supervisor; ECX2=XFD capable. Neither is admitted in this relay.
        if ((component.c & 5) != 0) { return ConfigurationResult::UnsupportedComponent; }
        if (component.a == 0 || component.b < 576 || component.b > area.b || component.a > area.b - component.b) {
            return ConfigurationResult::InvalidComponentExtent;
        }
        candidate.components[bit] = {component.a, component.b, component.c};
        for (std::uint32_t prior = 2; prior < bit; ++prior) {
            if (candidate.components[prior].bytes != 0 && overlap(candidate.components[prior], candidate.components[bit])) {
                return ConfigurationResult::InvalidComponentExtent;
            }
        }
    }
    if (candidate.vendor == Vendor::Amd) {
        if (cpuid(0x80000000).a < 0x80000008) { return ConfigurationResult::AmdErrorPointersUnsupported; }
        candidate.amd_cpuid_80000008_ebx = cpuid(0x80000008).b;
        // XSaveErPtr=1 provides AMD's documented architectural pointer semantics;
        // it does NOT promise literal physical FIP/FDP/FOP when #MF is not pending.
        if ((candidate.amd_cpuid_80000008_ebx & (1U << 2)) == 0) {
            return ConfigurationResult::AmdErrorPointersUnsupported;
        }
    }
    if (request.registered_stack_low == 0 || request.registered_stack_low >= request.registered_stack_high ||
        request.callback_stack_budget < 256 || request.callback_stack_budget > kMaximumCallbackStack ||
        request.signal_reserve == 0 || request.signal_reserve > kMaximumSignalReserve) {
        return ConfigurationResult::InvalidStackBudget;
    }
    // Worst alignment loss63. CALL/callback red-zone budget is explicit, not
    // borrowed from the native decoder's frame or the historical synthetic image.
    const auto needed = static_cast<std::uint64_t>(candidate.xsave_bytes) + HGN_RELAY_ENTRY_RESERVE +
        HGN_RELAY_ALLOC_PAD + 63 + request.callback_stack_budget + request.signal_reserve;
    if (request.registered_stack_high - request.registered_stack_low < needed) {
        return ConfigurationResult::InvalidStackBudget;
    }
    candidate.registered_stack_low = request.registered_stack_low;
    candidate.registered_stack_high = request.registered_stack_high;
    candidate.required_stack_below_original_rsp = needed;
    candidate.scope = request.scope;
    candidate.enabled = 1; // Candidate only: caller has not installed/published it.
    return ConfigurationResult::ArchitecturalCandidate;
}
} // namespace halogen_nohit::frame_relay
