#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "native_frame_relay.h"

#include <cstdio>
#include <pthread.h>

using namespace halogen_nohit::frame_relay;

extern "C" {
alignas(64) std::array<std::uint8_t, kMaximumXsaveBytes> halogen_probe_before_xsave{};
alignas(64) std::array<std::uint8_t, kMaximumXsaveBytes> halogen_probe_after_xsave{};
alignas(64) std::array<std::uint8_t, kMaximumXsaveBytes> halogen_probe_caller_xsave{};
alignas(64) std::array<std::uint8_t, kMaximumXsaveBytes> halogen_probe_init_xsave{};
RegisterImage halogen_probe_before_registers{};
RegisterImage halogen_probe_after_registers{};
RegisterImage halogen_probe_observer_registers{};
std::array<std::uint64_t, 16> halogen_probe_register_pattern{};
std::array<std::uint64_t, 16> halogen_probe_red_zone_after{};
std::uint64_t halogen_probe_observer_count{};
std::uint32_t halogen_probe_noninit{};
void halogen_nohit_mock_handler() noexcept;
}

namespace {
constexpr std::uint64_t kOrdinaryFlags = 0xcd5; // CF/PF/AF/ZF/SF/DF/OF only.
constexpr std::uint64_t kCanary = 0x1122334455667788ULL;
int failures = 0;
int checks = 0;
void check(bool value, const char* message) {
    ++checks;
    if (!value) { ++failures; std::printf("FAIL: %s\n", message); }
}
std::uint64_t read(const std::uint8_t* bytes, std::size_t count) {
    std::uint64_t value = 0;
    for (std::size_t i = 0; i < count; ++i) { value |= static_cast<std::uint64_t>(bytes[i]) << (8 * i); }
    return value;
}
bool architectural_xstate_equal(const RelayConfiguration& config) {
    const auto* before = halogen_probe_before_xsave.data();
    const auto* after = halogen_probe_after_xsave.data();
    const auto before_bv = read(before + 512, 8);
    const auto after_bv = read(after + 512, 8);
    if (((before_bv | after_bv) & ~config.xcr0_mask) != 0 ||
        read(before + 520, 8) != 0 || read(after + 520, 8) != 0) { return false; }
    const auto x87_field = [](const std::uint8_t* image, std::uint64_t bv, std::size_t offset,
                              std::size_t count, std::uint64_t initial) {
        return (bv & 1) != 0 ? read(image + offset, count) : initial;
    };
    const auto before_control = x87_field(before, before_bv, 0, 2, 0x37f);
    const auto after_control = x87_field(after, after_bv, 0, 2, 0x37f);
    const auto before_status = x87_field(before, before_bv, 2, 2, 0);
    const auto after_status = x87_field(after, after_bv, 2, 2, 0);
    const auto before_tag = x87_field(before, before_bv, 4, 1, 0);
    const auto after_tag = x87_field(after, after_bv, 4, 1, 0);
    if (before_control != after_control || before_status != after_status || before_tag != after_tag) { return false; }
    const auto top = (before_status >> 11) & 7;
    for (std::size_t logical = 0; logical < 8; ++logical) {
        if ((before_tag & (1ULL << ((top + logical) & 7))) == 0) { continue; }
        for (std::size_t byte = 0; byte < 10; ++byte) {
            if (before[32 + 16 * logical + byte] != after[32 + 16 * logical + byte]) { return false; }
        }
    }
    // Deliberately exclude FOP/FIP/FDP and undefined empty/reserved slots. AMD
    // architectural save semantics cannot prove literal physical-pointer parity.
    // MXCSR belongs to SSE/AVX; this test seeds its documented initial0x1f80.
    if (read(before + 24, 4) != read(after + 24, 4)) { return false; }
    for (std::size_t byte = 0; byte < 256; ++byte) {
        const auto a = (before_bv & 2) != 0 ? before[160 + byte] : 0;
        const auto b = (after_bv & 2) != 0 ? after[160 + byte] : 0;
        if (a != b) { return false; }
    }
    for (std::uint32_t bit = 2; bit < 64; ++bit) {
        if ((config.xcr0_mask & (1ULL << bit)) == 0) { continue; }
        const auto& extent = config.components[bit];
        // PKRU occupies4architectural bytes; its remaining4bytes are reserved.
        const auto meaningful = bit == 9 ? 4U : extent.bytes;
        for (std::uint32_t byte = 0; byte < meaningful; ++byte) {
            const auto a = (before_bv & (1ULL << bit)) != 0 ? before[extent.standard_offset + byte] : 0;
            const auto b = (after_bv & (1ULL << bit)) != 0 ? after[extent.standard_offset + byte] : 0;
            if (a != b) { return false; }
        }
    }
    return true;
}

void run_case(const RelayConfiguration& discovered, bool enabled, bool noninit) {
    halogen_nohit_relay_configuration = discovered; // No thread/relay is running.
    halogen_nohit_relay_configuration.enabled = enabled ? 1U : 0U;
    halogen_probe_noninit = noninit ? 1U : 0U;
    halogen_probe_observer_count = 0;
    halogen_probe_before_xsave.fill(0);
    halogen_probe_after_xsave.fill(0);
    halogen_probe_caller_xsave.fill(0);
    halogen_probe_init_xsave.fill(0);
    halogen_probe_init_xsave[24] = 0x80;
    halogen_probe_init_xsave[25] = 0x1f;
    halogen_probe_before_registers = {};
    halogen_probe_after_registers = {};
    halogen_probe_observer_registers = {};
    halogen_probe_red_zone_after.fill(0);
    for (std::size_t i = 0; i < 16; ++i) {
        halogen_probe_register_pattern[i] = 0x1020304050607080ULL + i * 0x0101010101010101ULL;
    }
    halogen_nohit_mock_handler();
    const auto& before = halogen_probe_before_registers;
    const auto& after = halogen_probe_after_registers;
    bool seed_ok = before.gpr[7] != 0;
    bool gprs_ok = true;
    for (std::size_t i = 0; i < 16; ++i) {
        if (i != 7) { seed_ok = seed_ok && before.gpr[i] == halogen_probe_register_pattern[i]; }
        const auto expected = i == 0 ? before.gpr[6] + 0x1e8 : before.gpr[i];
        gprs_ok = gprs_ok && after.gpr[i] == expected;
    }
    check(seed_ok && gprs_ok, "actual GPRs/originalRSP preserved with stock-only RAX LEA");
    check((before.ordinary_rflags & kOrdinaryFlags) == kOrdinaryFlags &&
        (after.ordinary_rflags & kOrdinaryFlags) == (before.ordinary_rflags & kOrdinaryFlags),
        "actual arithmetic and DF flags survive observer/relay");
    bool canaries_ok = true;
    for (const auto value : halogen_probe_red_zone_after) { canaries_ok = canaries_ok && value == kCanary; }
    check(canaries_ok, "all128original red-zone bytes survive real relay stack movement");
    check(halogen_probe_observer_count == (enabled ? 1U : 0U), "enabled observer called exactly once; disabled never calls");
    if (enabled) {
        check(halogen_probe_observer_registers.gpr == before.gpr &&
            (halogen_probe_observer_registers.ordinary_rflags & kOrdinaryFlags) == kOrdinaryFlags,
            "observer sees complete real captured frame before displaced LEA");
    }
    check(architectural_xstate_equal(discovered), "real XSAVE architectural user-state survives x87/SSE/AVX clobber");
    if (!noninit) {
        const auto init_mask = 3ULL | (discovered.xcr0_mask & 4);
        check((read(halogen_probe_before_xsave.data() + 512, 8) & init_mask) == 0,
            "init-state components begin absent from XSTATE_BV and restore after observer creates state");
    }
    std::printf("case enabled=%u noninit=%u complete\n", enabled ? 1U : 0U, noninit ? 1U : 0U);
}
} // namespace

int main() {
    // Standalone startup only, never relay/observer: query actual thread mapping.
    pthread_attr_t attributes;
    if (pthread_getattr_np(pthread_self(), &attributes) != 0) { return 2; }
    void* stack = nullptr;
    std::size_t stack_bytes = 0;
    const int stack_result = pthread_attr_getstack(&attributes, &stack, &stack_bytes);
    const int destroy_result = pthread_attr_destroy(&attributes);
    if (stack_result != 0 || destroy_result != 0) { return 2; }
    StartupRequest request{};
    request.enable = true;
    request.registered_stack_low = reinterpret_cast<std::uint64_t>(stack);
    request.registered_stack_high = request.registered_stack_low + stack_bytes;
    request.callback_stack_budget = 4096; // Leaf assembly observer; no native calls.
    request.signal_reserve = 64 * 1024; // No handlers/reentry tested or qualified.
    RelayConfiguration discovered{};
    const auto result = discover_configuration(request, discovered);
    if (result != ConfigurationResult::ArchitecturalCandidate) {
        std::printf("DECLINED configuration=%u; no relay qualifier executed\n", static_cast<unsigned>(result));
        return 77;
    }
    std::printf("vendor=%u family=%u model=%u stepping=%u XCR0=%llx XSAVE=%u scope=architectural\n",
        static_cast<unsigned>(discovered.vendor), discovered.family, discovered.model, discovered.stepping,
        static_cast<unsigned long long>(discovered.xcr0_mask), discovered.xsave_bytes);
    run_case(discovered, false, true);
    run_case(discovered, true, true);
    run_case(discovered, true, false);
    std::printf("three real-register cases: %s (%d failed checks, %d checks); physical x87 metadata, signals, CET and native installation unqualified\n",
        failures == 0 ? "PASS" : "FAIL", failures, checks);
    return failures == 0 ? 0 : 1;
}
