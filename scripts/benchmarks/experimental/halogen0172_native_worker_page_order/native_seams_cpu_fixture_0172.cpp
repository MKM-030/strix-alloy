// CPU-only fixture: no engine image, server, GPU, model or runtime attachment.
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

struct FixtureInput {
    std::uintptr_t target;
    std::uint64_t alignment;
    std::uint64_t edit;
    std::uint64_t compare;
    std::uint64_t compare_value;
    std::uint64_t seam;
};

struct alignas(16) FixtureOutput {
    std::uint64_t registers[15];
    std::uint64_t flags;
    std::uintptr_t rsp;
    std::uintptr_t callback_frame;
    std::uintptr_t callback_block;
    std::uintptr_t callback_entry_rsp;
    std::uint64_t callback_flags;
    std::uint64_t chosen_resume;
    std::uint64_t branch;
    std::uint64_t callback_count;
    std::uint64_t expected_flags;
    alignas(16) unsigned char expected_fx[512];
    alignas(16) unsigned char actual_fx[512];
};

static_assert(offsetof(FixtureInput, compare_value) == 32);
static_assert(offsetof(FixtureOutput, flags) == 120);
static_assert(offsetof(FixtureOutput, rsp) == 128);
static_assert(offsetof(FixtureOutput, expected_fx) == 208);
static_assert(offsetof(FixtureOutput, actual_fx) == 720);

extern "C" {
void ple0172_native_launch_seam();
void ple0172_native_copy_seam();
void ple0172_native_complete_seam();
void ple0172_native_consumer_seam();
void ple0172_fixture_run(const FixtureInput*, FixtureOutput*);
void ple0172_fixture_resume();
void ple0172_fixture_alternate_resume();
void ple0172_fixture_cmp_replay();

const FixtureInput* ple0172_fixture_input = nullptr;
FixtureOutput* ple0172_fixture_output = nullptr;
std::uintptr_t ple0172_fixture_native_rsp = 0;
std::uintptr_t ple0172_fixture_host_rsp = 0;
std::uintptr_t ple0172_fixture_target = 0;
std::uint64_t ple0172_fixture_expected_flags = 0;
std::uint64_t ple0172_fixture_chosen_resume = 0;
std::uint64_t ple0172_fixture_branch = 0;
}

namespace {
constexpr std::uint64_t seed[15] = {
    0x1111111111111111, 0x2222222222222222, 0x3333333333333333,
    0x4444444444444444, 0x5555555555555555, 0x6666666666666666,
    0x7777777777777777, 0x8888888888888888, 0x9999999999999999,
    0xaaaaaaaaaaaaaaaa, 0xbbbbbbbbbbbbbbbb, 0xcccccccccccccccc,
    0xdddddddddddddddd, 0xeeeeeeeeeeeeeeee, 0xffffffffffffffff
};
constexpr std::uint64_t edited_rbp = 0xfedcba9876543210;
constexpr std::uint64_t edited_rcx = 0x1020304050607080;

[[noreturn]] void fail(const char* message) {
    std::fprintf(stderr, "native seam CPU fixture failed: %s\n", message);
    std::exit(1);
}
void require(bool condition, const char* message) {
    if (!condition) fail(message);
}
template<class T> T load(const unsigned char* bytes, std::size_t offset) {
    T value;
    std::memcpy(&value, bytes + offset, sizeof value);
    return value;
}

void check_fx(const FixtureOutput& out) {
    require(load<std::uint16_t>(out.expected_fx, 0) == 0x077f, "fixture x87 control seed");
    require(load<std::uint32_t>(out.expected_fx, 24) == 0x5f80, "fixture MXCSR seed");
    require(out.expected_fx[4] != 0, "fixture x87 stack seed");
    // Defined FXSAVE64 fields: control/status/tag, opcode and x87 pointers,
    // MXCSR/mask, ten bytes of each x87 slot, and all sixteen XMM registers.
    require(!std::memcmp(out.expected_fx, out.actual_fx, 5), "x87 control/status/tag");
    require(!std::memcmp(out.expected_fx + 6, out.actual_fx + 6, 26), "x87 opcode/pointers/MXCSR");
    for (unsigned i = 0; i < 8; ++i)
        require(!std::memcmp(out.expected_fx + 32 + i * 16,
                             out.actual_fx + 32 + i * 16, 10), "x87 stack value");
    for (unsigned i = 0; i < 256; ++i) {
        require(out.expected_fx[160 + i] == static_cast<unsigned char>(i), "fixture XMM seed");
        require(out.actual_fx[160 + i] == static_cast<unsigned char>(i), "XMM0..15 restoration");
    }
}

void run(unsigned seam, unsigned alignment, bool edit, bool compare, std::uint64_t operand) {
    const std::uintptr_t targets[4] = {
        reinterpret_cast<std::uintptr_t>(&ple0172_native_launch_seam),
        reinterpret_cast<std::uintptr_t>(&ple0172_native_copy_seam),
        reinterpret_cast<std::uintptr_t>(&ple0172_native_complete_seam),
        reinterpret_cast<std::uintptr_t>(&ple0172_native_consumer_seam)
    };
    FixtureInput input{targets[seam], alignment, std::uint64_t(edit),
                       std::uint64_t(compare), operand, seam};
    FixtureOutput output{};
    ple0172_fixture_chosen_resume = 0;
    ple0172_fixture_branch = 0;
    ple0172_fixture_run(&input, &output);
    output.expected_flags = ple0172_fixture_expected_flags;
    output.chosen_resume = ple0172_fixture_chosen_resume;
    output.branch = ple0172_fixture_branch;
    require(output.callback_count == 1, "exactly one callback");
    require(output.rsp == ple0172_fixture_native_rsp, "original RSP restoration");
    require((output.rsp & 15) == alignment, "requested native RSP alignment");
    require(output.callback_frame == output.rsp, "callback original RSP argument");
    require(output.callback_block + 128 == output.rsp, "callback GPR block argument");
    require((output.callback_entry_rsp & 15) == 8, "SysV callback entry alignment");
    require(!(output.callback_flags & 0x400), "callback direction flag cleared");
    for (unsigned i = 0; i < 15; ++i) {
        const auto expected = edit && i == 6 ? edited_rbp : edit && i == 2 ? edited_rcx : seed[i];
        require(output.registers[i] == expected, "all fifteen GPRs and intentional edits");
    }
    if (compare) {
        constexpr std::uint64_t arithmetic_flags = 0x8d5; // CF/PF/AF/ZF/SF/OF
        const auto expected = (output.expected_flags & ~arithmetic_flags) |
                              (operand == 0 ? 0x44 : 0); // 0 or 7 compared with zero
        require(output.flags == expected, "CMP replay arithmetic and retained flags");
        require(output.chosen_resume == 3, "completion replay destination");
        require(output.branch == (operand == 0 ? 1U : 2U), "native conditional after CMP replay");
    } else {
        require(output.flags == output.expected_flags, "RFLAGS restoration including DF");
        require(output.chosen_resume == (edit ? 2U : 1U), "dispatcher-selected destination");
        require(output.branch == 0, "ordinary destination did not execute CMP replay");
    }
    check_fx(output);
}
} // namespace

extern "C" std::uintptr_t ple0172_fixture_callback(void* frame, std::uint64_t* registers,
                                                   unsigned seam, std::uintptr_t entry_rsp) noexcept {
    auto& out = *ple0172_fixture_output;
    const auto& input = *ple0172_fixture_input;
    std::uint64_t flags;
    __asm__ volatile("pushfq; popq %0" : "=r"(flags));
    require(seam == input.seam, "correct wrapper dispatcher");
    require(reinterpret_cast<std::uintptr_t>(frame) == ple0172_fixture_native_rsp,
            "callback frame before return");
    require(reinterpret_cast<std::uintptr_t>(registers) + 128 == ple0172_fixture_native_rsp,
            "callback block before return");
    require((entry_rsp & 15) == 8, "callback stack before return");
    require(!(flags & 0x400), "callback DF before return");
    for (unsigned i = 0; i < 15; ++i)
        require(registers[i] == seed[i], "incoming GPR block order and values");
    out.callback_frame = reinterpret_cast<std::uintptr_t>(frame);
    out.callback_block = reinterpret_cast<std::uintptr_t>(registers);
    out.callback_entry_rsp = entry_rsp;
    out.callback_flags = flags;
    ++out.callback_count;
    if (input.edit) {
        require(seam == 1, "only copy callback intentionally edits GPRs");
        registers[6] = edited_rbp;
        registers[2] = edited_rcx;
        return reinterpret_cast<std::uintptr_t>(&ple0172_fixture_alternate_resume);
    }
    if (input.compare) {
        require(seam == 2, "only completion callback selects CMP replay");
        return reinterpret_cast<std::uintptr_t>(&ple0172_fixture_cmp_replay);
    }
    return reinterpret_cast<std::uintptr_t>(&ple0172_fixture_resume);
}

int main() {
    for (unsigned seam = 0; seam < 4; ++seam)
        for (unsigned alignment : {0U, 8U}) run(seam, alignment, false, false, 0);
    for (unsigned alignment : {0U, 8U}) run(1, alignment, true, false, 0);
    for (unsigned alignment : {0U, 8U})
        for (std::uint64_t operand : {std::uint64_t(0), std::uint64_t(7)})
            run(2, alignment, false, true, operand);
    std::puts("native seam CPU fixture passed: 14 cases; 4 seams, both RSP alignments, "
              "GPR edits, RFLAGS, x87/MXCSR/XMM0..15 and completion CMP branches");
}
