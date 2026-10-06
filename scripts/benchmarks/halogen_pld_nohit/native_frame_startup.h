#pragma once

#include "native_frame_install.h"

#include <array>

namespace halogen_nohit::frame_startup {

// Owned startup diagnostics, never a native-read or state-preservation permit.
// The only installer caller is this object's guarded preload constructor.
struct StartupObservation {
    frame_install::InstallResult result = frame_install::InstallResult::Disabled;
    std::uint64_t main_tid{};
    std::uint64_t constructor_rsp{};
    std::uint64_t stack_low{}, stack_high{};
    std::uint64_t kernel_minimum_signal_stack{};
    std::uint64_t signal_reserve{};
    std::uint32_t startup_cpu{};
    std::uint32_t allowed_cpu_count{};
    // Linux CPU IDs 0..1023, least-significant bit first. This is an observation
    // of the main task's allowed set; the caller does not alter its affinity.
    std::array<std::uint64_t, 16> allowed_cpus{};
};

// False when disabled or before successful installation. The immutable result
// describes this constructor only, not subsequent native frames or CPUs.
bool copy_startup_observation(StartupObservation& out) noexcept;

// Default off: absent HALOGEN_NOHIT_FRAME_INSTALL performs no startup work.
// The exact register-stock-v1 value admits only flash_serve with first argument
// --ck. This source never calls the observer or reads a captured native address.
// Main native request parsing source-proves the relay's initial 264 stack bytes;
// the relay's later check covers the complete registered callback/xstate budget.
// Native register/xstate, future signals/unwinds, loader/CET and migration remain
// unqualified until root's ordinary lifecycle validation of the same built DSO.
} // namespace halogen_nohit::frame_startup
