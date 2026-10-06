# Independent source review: native stock-observer installer

Review date: 2026-10-06. Reviewer: `/root/handoff_peer_review`. Scope: final new installer source, its explicit link arrangement, and the unchanged relay/config contracts needed to assess that arrangement. No compiler, linker, WSL, test, runtime, hardware, installer invocation, service action or model download was performed by this reviewer. No implementation or previous review was edited.

## Verdict and boundary

No remaining source blocker was identified in the bounded, default-off, startup-only **stock register-observer installation core** at the pins below. This is preparation for a real installation. It does not establish that installation occurred or that a pilot is ready.

The core has an explicit `install_before_handler` API and supplies no enabled constructor/bootstrap caller. The actual guarded preload caller is a required separate source connection. It must establish execution before any handler entry, retain the DSO/island/frame records until process exit, supply actual owner stack bounds and reviewed callback/signal budgets, and qualify all admitted entries. In particular, the frozen relay saves its first 264 bytes below original RSP **before** its configured lower-bound/bypass checks; checking the startup RSP and a stack mapping does not prove that unconditional save is safe for every future entry.

Root owns the emitted-object inspection and all execution. Source approval here is conditional on the stated caller/entry prerequisites and inspection of this exact linked object's displacements, relocations, page layout and full copied unwind rows. Neither the preceding limited relay harness nor root's new compile/link receipt is live installation, native capture, signal-unwind, active CET or serving evidence.

## Frozen reviewed inputs

| File | SHA256 |
|---|---|
| `native_frame_install.h` | `68a51e37e92b28cc1caa27c7ce50c4ff33f57c1728da13175fecac08b0a516cf` |
| `native_frame_install.cpp` | `61122012a598f39318b7d5fd6506b60d239dfc3059dc239cdb49ef74f82fd572` |
| `native_frame_install_link.S` | `83c23db12b3d7246f0fe5cb9765689921d436de9061d4eff746292094bdc0b98` |
| `native_frame_install.ld` | `373befb7549a998d15868488319bde10030cfb0aedae1c6e39dac5cda4b7e840` |
| `NATIVE_FRAME_INSTALL.md` | `b98121a8187eb33f3850bfa54b30c273522e4bc4070d0eba108b08019b9214e4` |

The corrected `.cpp` supersedes earlier source pin `b60118c12090edfefa3bb7e8a5b27c44e00612d02d59158024b23311f90cdc64`. The existing relay/configuration remain frozen; this review does not reopen their earlier qualification or owner/packet reviews.

## Source findings

1. **Default-off authority and exact target.** The API requires both `StartupRequest.enable` and exact `HALOGEN_NOHIT_FRAME_INSTALL=register-stock-v1`. The preliminary non-serving route remains disabled. For an enabled serving request, `serving_process` checks `flash_serve` and first argument `--ck`. `verify_engine` checks the exact 26,052,768-byte x86-64 little-endian PIE ELF, full SHA256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`, stat consistency, main RX PT_LOAD/file mapping, the expected seam file offset, and an exact 32-byte file/live window. The displaced seven-byte `48 8d 85 e8 01 00 00` LEA at RVA `0x172d3bd` is checked again immediately before publication. Guard failure exits instead of returning to serving with incomplete installation. These checks identify this target; they do not provide owner/read authority.

2. **Concrete startup exclusion.** The implementation blocks all catchable signals through the Linux x86-64 kernel `rt_sigprocmask` interface, including libc-reserved catchable signals. It requires actual main TID and exactly one `/proc/self/task` entry, and rechecks task count before patching. SIGKILL/STOP remain unblockable. The mask is restored only after final bytes, RX protection and publication. This is a concrete exclusion during startup; it is not a policy or proof for later serving signals. Current startup RSP must be inside the supplied wholly RW mapped owner-stack interval. The independent caller must still establish that this is the real startup point and prove future entry/headroom requirements.

3. **Copied code has a specific closed layout.** The GNU linker fragment extracts exact-basename `native_frame_relay.o` and `native_frame_install_link.o` code/frame sections, the relay MXCSR constant, `native_frame_config.o` data/BSS, and the link object's observation storage. It asserts page contiguity and key symbol placement. Ordinary installer/config-function EH tables remain in the DSO rather than the copied frame set. Its copied RX cross-reference exclusions cover ordinary `.text`, PLT and GOT output sections. `original_island` checks boundaries, a maximum 16-page island, expected ENDBR/pad bytes, MXCSR value, empty observation, readable/source permissions and module membership. Dynamic RELA destinations inside the island are refused; REL/RELR and text relocations are deliberately unsupported. This arrangement still requires root's same-object inspection of every emitted reference; the linker rules are not a general proof for arbitrarily changed future inputs.

4. **Near placement and stock path stay direct.** The finite 256-candidate alternating ±2 MiB search uses `MAP_FIXED_NOREPLACE`, verifies the exact returned address and RW mapping, and checks both rel32 branches. Moving the whole island preserves its internal RIP-relative references, observer direct call and PC-relative frame references. Only the copied stock pad's rel32 sentinel is changed, pointing to seam+7=`0x172d3c4`. The unchanged relay restores its real state, replays the LEA, and directly jumps to the pad. The pad's only onward branch is direct E9. There is no FF25 far wrapper, indirect native continuation, fabricated return or success-join route.

5. **Permissions and complete instruction publication.** After filling the copied configuration and pad displacement, publication changes the four copied ranges from RW to RX/R/R/RW, verifies each mapping, and registers frames before changing native text. The native page changes RX→RW→RX, without an RWX phase. Under the startup exclusion, one seven-byte write replaces the entire native LEA with E9 rel32 and two NOPs. The source checks final bytes and RX permissions; partial failure is fatal. This is neither a concurrent hot patch nor a rollback/uninstall design.

6. **Unwind records are preserved and retained.** `verify_frames` accepts the bounded simple GNU CIE prefix with pcrel/sdata4 initial-location encoding, checks CIE references, bounded nonzero code ranges and zero FDE augmentation length, requires three FDEs covering relay/observer/pad, and requires the final zero terminator. `__register_frame` registers the copied range; `_Unwind_Find_FDE` must return a record in that copied range with the expected function start for each entry. The ordinary observer has normal CALL/RET CFA rules; the stock pad restores the native `RSP+0x2680` CFA and saved-caller offsets. The parser checks record envelopes and ranges, **not every CFI instruction's semantic row**. Root must inspect full rows in the emitted DSO; lookup membership alone is not executed signal/unwind qualification. The island and registration have permanent process lifetime.

7. **Observed register copy remains within the frozen ABI.** The assembly leaf uses only the owned `NativeFrameView.registers` pointer. An aligned one-shot lock-CMPXCHG changes state 0→1; it copies exactly 17 qwords into owned storage, then publishes state 2. The immutable image consists of 16 GPR values and ordinary flags. It does not follow address values, read native objects, export XSAVE, mutate the view, call allocators or reenter serving. The relay's direct normal call and balanced return preserve the existing observer contract. `copy_first_register_observation` waits for installed/ready publication and returns this immutable engine-local copy; its values confer no dereference permission and must not be sent to a proposer.

8. **CET and architectural state stay scoped.** The installer refuses an observed active shadow stack. An unsupported status query is explicitly not CET qualification. Configuration discovery still accepts only its recognized architectural user-state scope and refuses literal physical x87 metadata on every vendor. AMD save canonicalization, CPU migration, later signals, debug/privileged flags and the prior noninitial AVX512/PKRU gaps remain unchanged qualification boundaries. Source numeric budgets do not close them.

## Concrete FDE correction included

Root's first emitted-object inspection reported an observer FDE with payload length 16 (total length 20) rejected by the initial parser's redundant `length < 17` test. The final source removes that test. The existing global minimum payload length 13 guarantees total length at least 17, so reads through `bytes[16]` are bounded. CIE-prefix and returned-FDE `span(...,17,...)` checks describe total byte extents and remain valid. The corrected source therefore accepts the reported ordinary leaf record without weakening the required fields or adding a runtime claim.

Root separately reported one repair compile/relink using unchanged pinned objects, with final DSO SHA256 `55ce07fb50ac3a38c6c4025e8b601c4086a5e3553d308b62585a2cabeb07336b` under `_artifacts/20261006-095656-native-installer-fde-repair-1a136793`. The DSO was not loaded. This reviewer did not rebuild, load it, parse its binary, or independently certify that receipt.

## Remaining required connection and honest outcome

The actual startup caller and admitted native entries remain required. Root must also finish the exact emitted reference/CFI inspection before any controlled pilot and qualify the live stack, signal, CPU and kernel/loader/CET conditions applicable to that pilot. An independent future native-read/outcome entry would need its own source-reviewed ownership/lifetime/full-prefix and host-output authority; this observer does not implement one.

This change performs CPU startup work and CPU register capture and adds overhead. It leaves the target on its stock continuation, adds no token proposer, and supplies no acceptance or performance improvement. Capture cost, GPU/NPU placement/readiness, native capture qualification, Prefill, Decode, authoritative committed-token rate and serving gain all remain **null / unmeasured**.
