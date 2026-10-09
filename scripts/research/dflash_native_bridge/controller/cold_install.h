#pragma once
#include "retained_relay.h"
namespace hgn_dflash::cold {
enum class Result:u32 {Off,Installed,AlreadyInstalled,BadArguments,NotSingleThread,ImageRejected,CpuRejected,IslandRejected,MapFailed};
struct Arguments {
    u32 enable{};                 // Explicit startup call only; zero has no effects.
    u32 abi_version{1};
    u32 isolated_slot_cache_off{}; // Root must establish actual bounded native scope.
    u32 optional_provider{};
    Lane* lane{};                 // Retained for process lifetime, configured later.
    const Configuration* provider{};
    u64 callback_and_signal_budget{}; // >=81920 if optional provider enabled.
};
// No constructor, environment arming, thread creation, server/API or device call.
// Call only from trusted cold startup before any native engine execution/thread.
// Once installed the containing DSO/Lane/config must remain through process exit.
}
extern "C" {
hgn_dflash::cold::Result hgn_dflash_install_cold(const hgn_dflash::cold::Arguments*)noexcept;
bool hgn_dflash_register_current_stack(hgn_dflash::u64 mapped_low,hgn_dflash::u64 mapped_high)noexcept;
void hgn_dflash_disable_optional()noexcept;
bool hgn_dflash_optional_drained()noexcept;
}
