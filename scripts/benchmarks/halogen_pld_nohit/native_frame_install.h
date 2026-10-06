#pragma once

#define HGN_INSTALL_OBSERVATION_STATE 0
#define HGN_INSTALL_OBSERVATION_REGISTERS 8
#define HGN_INSTALL_OBSERVATION_BYTES 144

#ifndef __ASSEMBLER__
#include "native_frame_relay.h"

namespace halogen_nohit::frame_install {

enum class InstallResult : std::uint8_t { Disabled, AlreadyInstalled, InstalledStockObserver };

// STARTUP ONLY, before any handler entry, from a separately reviewed preload
// caller. No enabled constructor is supplied by this core. Both request.enable
// and HALOGEN_NOHIT_FRAME_INSTALL=register-stock-v1 are required; default is off.
// Requested guard failures terminate before serving, like the existing guarded
// preload patches. Retain this DSO, copied island and registered frame records
// until process exit. There is no hot install, rollback, uninstall or destructor.
//
// Caller supplies the real owner stack mapping and source-reviewed complete
// callback/signal budgets. The assembly-only leaf observer has no stack use
// beyond its normal CALL return; use >=256 for the existing relay budget API.
// Numeric bounds, ELF/hash/relocation/FDE checks and startup signal exclusion do
// not qualify native state, CPU migration, future signal handling, debug/CET,
// native object lifetime, ownership, full-prefix continuity or acceptance.
InstallResult install_before_handler(const frame_relay::StartupRequest& request) noexcept;

// Engine-local only. First successful owned-register observation is immutable.
// Register values may contain native addresses; never publish this to a proposer
// or interpret them as dereference permission. No XSAVE or native object copy is
// exposed. The frozen observer ABI remains owned view/image inspection only.
bool copy_first_register_observation(frame_relay::RegisterImage& out) noexcept;

// Build arrangement (root alone builds/reviews/runs): compile the exact basename
// objects native_frame_relay.o, native_frame_config.o, native_frame_install.o,
// native_frame_install_link.o with -fPIC; link a shared DSO with
// -Wl,-T,native_frame_install.ld,-z,max-page-size=4096,-z,separate-code,-z,now,-z,relro
// -Wl,--no-undefined and -ldl -lcrypto -lgcc_s. Do not pack relative relocations.
// Keep normal compiler EH tables for installer/config functions. Root must
// inspect emitted relocations, direct branches and all three copied FDEs in this
// SAME linked object, plus the actual startup caller, before a controlled pilot.
// The island moves as one block: RX code; R MXCSR/PC-relative frames; R immutable
// configuration; RW first-observation storage. Internal offsets cannot change.
//
// CPU executes startup checks and register capture; this adds CPU overhead and
// has no measured Prefill/Decode/acceptance/serving benefit. GPU/NPU proposal/state
// work remains future work; readiness, placement and every serving metric=null.
} // namespace halogen_nohit::frame_install
#endif
